"""Pure geometry helpers (no I/O, no third-party dependencies).

All coordinates are ``[lon, lat]`` pairs in EPSG:4326, matching GeoJSON. Metric
calculations (areas, distances to edges, simplification tolerances) use a local
equirectangular projection centred on the data, which is accurate to well under
0.1 % at the scale of a city district.

Geometries are plain GeoJSON geometry dicts, e.g.
``{"type": "Polygon", "coordinates": [[[lon, lat], ...], ...]}``.
"""

from __future__ import annotations

import math
import re
from typing import Iterable, Sequence

EARTH_RADIUS_M = 6_371_008.8  # mean Earth radius (IUGG)

Coord = Sequence[float]
Ring = list[list[float]]
BBox = list[float]  # [min_lon, min_lat, max_lon, max_lat]

__all__ = [
    "parse_wkt",
    "polygons_of",
    "lines_of",
    "all_coords",
    "area_m2",
    "centroid",
    "weighted_centroid",
    "bbox",
    "bbox_union",
    "point_in_polygon",
    "haversine_m",
    "distance_to_polygon_m",
    "round_geometry",
    "douglas_peucker",
    "simplify_line",
    "simplify_geometry",
    "assemble_rings",
    "rings_to_geometry",
    "lines_inside",
    "midpoint_along",
    "closest_approach",
]


# --------------------------------------------------------------------------- WKT

_SRID_RE = re.compile(r"^\s*SRID=(\d+)\s*;\s*", re.IGNORECASE)
_WKT_TYPE_RE = re.compile(r"^\s*([A-Za-z]+?)\s*(?:ZM|Z|M)?\s*(\(.*|EMPTY)$", re.DOTALL | re.IGNORECASE)

_WKT_TO_GEOJSON = {
    "POINT": "Point",
    "LINESTRING": "LineString",
    "POLYGON": "Polygon",
    "MULTIPOINT": "MultiPoint",
    "MULTILINESTRING": "MultiLineString",
    "MULTIPOLYGON": "MultiPolygon",
}

# Nesting depth of the coordinate array for each GeoJSON type.
_DEPTH = {
    "Point": 0,
    "LineString": 1,
    "MultiPoint": 1,
    "Polygon": 2,
    "MultiLineString": 2,
    "MultiPolygon": 3,
}


def parse_wkt(text: str) -> dict:
    """Parse a (E)WKT string into a GeoJSON geometry dict.

    Supports POINT, LINESTRING, POLYGON, MULTIPOINT, MULTILINESTRING and
    MULTIPOLYGON with an optional ``SRID=4326;`` prefix (as returned by GUGiK
    ULDK) and optional Z/M ordinates (dropped). Coordinates are kept in the
    order they appear (x y → [x, y]), so request ``srid=4326`` from services
    whose 4326 output is ``lon lat``.

    Raises ``ValueError`` for empty, unsupported or malformed input.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty WKT")
    body = _SRID_RE.sub("", text.strip(), count=1)
    m = _WKT_TYPE_RE.match(body)
    if not m:
        raise ValueError(f"malformed WKT: {text[:60]!r}")
    wkt_type, rest = m.group(1).upper(), m.group(2).strip()
    gj_type = _WKT_TO_GEOJSON.get(wkt_type)
    if gj_type is None:
        raise ValueError(f"unsupported WKT type {wkt_type!r}")
    if rest.upper() == "EMPTY":
        raise ValueError(f"empty {wkt_type}")
    nested = _parse_nested(rest)
    coords = _shape(nested, gj_type)
    return {"type": gj_type, "coordinates": coords}


def _parse_nested(s: str) -> list:
    """Turn ``((1 2,3 4),(5 6))`` into nested lists of coordinate strings."""
    stack: list[list] = []
    root: list | None = None
    token = []
    for ch in s:
        if ch == "(":
            new: list = []
            if stack:
                stack[-1].append(new)
            else:
                if root is not None:
                    raise ValueError("trailing data after WKT")
                root = new
            stack.append(new)
        elif ch in ",)":
            tok = "".join(token).strip()
            token = []
            if tok:
                if not stack:
                    raise ValueError("unbalanced WKT")
                stack[-1].append(_parse_point(tok))
            if ch == ")":
                if not stack:
                    raise ValueError("unbalanced WKT parentheses")
                stack.pop()
        else:
            token.append(ch)
    if stack or root is None:
        raise ValueError("unbalanced WKT parentheses")
    if "".join(token).strip():
        raise ValueError("trailing data after WKT")
    return root


def _parse_point(tok: str) -> list[float]:
    parts = tok.split()
    if len(parts) < 2:
        raise ValueError(f"bad WKT coordinate {tok!r}")
    try:
        x, y = float(parts[0]), float(parts[1])
    except ValueError as exc:
        raise ValueError(f"bad WKT coordinate {tok!r}") from exc
    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValueError(f"non-finite WKT coordinate {tok!r}")
    return [x, y]


def _is_coord(x) -> bool:
    return isinstance(x, list) and len(x) == 2 and all(isinstance(v, float) for v in x)


def _shape(nested: list, gj_type: str):
    """Validate/normalise the parsed nesting for ``gj_type``."""
    if gj_type == "Point":
        if len(nested) != 1 or not _is_coord(nested[0]):
            raise ValueError("bad POINT")
        return nested[0]
    if gj_type == "MultiPoint":
        # Both MULTIPOINT(1 2, 3 4) and MULTIPOINT((1 2),(3 4)) are valid WKT.
        out = []
        for item in nested:
            if _is_coord(item):
                out.append(item)
            elif isinstance(item, list) and len(item) == 1 and _is_coord(item[0]):
                out.append(item[0])
            else:
                raise ValueError("bad MULTIPOINT")
        return out

    def check(node, depth):
        if depth == 0:
            if not _is_coord(node):
                raise ValueError(f"bad {gj_type} nesting")
            return
        if not isinstance(node, list) or not node:
            raise ValueError(f"bad {gj_type} nesting")
        for child in node:
            check(child, depth - 1)

    check(nested, _DEPTH[gj_type])
    if gj_type in ("Polygon", "MultiPolygon"):
        for poly in polygons_of({"type": gj_type, "coordinates": nested}):
            for ring in poly:
                if len(ring) < 4:
                    raise ValueError("polygon ring needs >= 4 positions")
                if ring[0] != ring[-1]:
                    ring.append(list(ring[0]))
    return nested


# ------------------------------------------------------------------- accessors


def polygons_of(geom: dict) -> list[list[Ring]]:
    """Return the polygons of a Polygon/MultiPolygon as a list of ring lists."""
    t = geom.get("type")
    if t == "Polygon":
        return [geom["coordinates"]]
    if t == "MultiPolygon":
        return list(geom["coordinates"])
    if t == "GeometryCollection":
        return [p for g in geom.get("geometries", []) for p in polygons_of(g)]
    return []


def lines_of(geom: dict) -> list[list[list[float]]]:
    """Return the line strings of a LineString/MultiLineString (else ``[]``)."""
    t = geom.get("type")
    if t == "LineString":
        return [geom["coordinates"]]
    if t == "MultiLineString":
        return list(geom["coordinates"])
    if t == "GeometryCollection":
        return [ln for g in geom.get("geometries", []) for ln in lines_of(g)]
    return []


def all_coords(geom: dict) -> Iterable[list[float]]:
    """Yield every position of a geometry (any type)."""
    t = geom.get("type")
    if t == "GeometryCollection":
        for g in geom.get("geometries", []):
            yield from all_coords(g)
        return
    depth = _DEPTH.get(t)
    if depth is None:
        raise ValueError(f"unsupported geometry type {t!r}")

    def walk(node, d):
        if d == 0:
            yield node
        else:
            for child in node:
                yield from walk(child, d - 1)

    yield from walk(geom["coordinates"], depth)


# ------------------------------------------------------------------ projection


class _LocalProjection:
    """Equirectangular projection around a reference latitude (metres)."""

    def __init__(self, lat0: float):
        self.kx = math.radians(1) * EARTH_RADIUS_M * math.cos(math.radians(lat0))
        self.ky = math.radians(1) * EARTH_RADIUS_M

    def fwd(self, c: Coord) -> tuple[float, float]:
        return c[0] * self.kx, c[1] * self.ky

    def inv(self, x: float, y: float) -> list[float]:
        return [x / self.kx, y / self.ky]


def _projection_for(coords: Iterable[Coord]) -> _LocalProjection:
    lats = [c[1] for c in coords]
    if not lats:
        return _LocalProjection(0.0)
    return _LocalProjection((min(lats) + max(lats)) / 2)


def _ring_area_centroid(ring: Ring, proj: _LocalProjection) -> tuple[float, float, float]:
    """Absolute area (m²) and centroid (projected x, y) of a closed ring."""
    pts = [proj.fwd(c) for c in ring]
    if len(pts) < 3:
        return 0.0, 0.0, 0.0
    # Shift to the first vertex for numerical stability.
    ox, oy = pts[0]
    a2 = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        x1 -= ox
        y1 -= oy
        x2 -= ox
        y2 -= oy
        cross = x1 * y2 - x2 * y1
        a2 += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if a2 == 0:
        return 0.0, 0.0, 0.0
    return abs(a2) / 2, cx / (3 * a2) + ox, cy / (3 * a2) + oy


# -------------------------------------------------------------- measurements


def area_m2(geom: dict) -> float:
    """Approximate area in m² of a Polygon/MultiPolygon (holes subtracted)."""
    polys = polygons_of(geom)
    if not polys:
        return 0.0
    proj = _projection_for(c for p in polys for r in p for c in r)
    total = 0.0
    for poly in polys:
        outer = _ring_area_centroid(poly[0], proj)[0]
        holes = sum(_ring_area_centroid(h, proj)[0] for h in poly[1:])
        total += max(outer - holes, 0.0)
    return total


def centroid(geom: dict) -> list[float]:
    """Centroid as ``[lon, lat]``.

    Polygons: area-weighted (holes subtracted, multipolygon parts weighted by
    area). Lines: length-weighted midpoint of segments. Points: mean. Falls
    back to the vertex mean for degenerate (zero-area / zero-length) input.
    """
    t = geom.get("type")
    coords = list(all_coords(geom))
    if not coords:
        raise ValueError("empty geometry")
    proj = _projection_for(coords)
    if t in ("Polygon", "MultiPolygon"):
        sa = sx = sy = 0.0
        for poly in polygons_of(geom):
            for i, ring in enumerate(poly):
                a, x, y = _ring_area_centroid(ring, proj)
                sign = 1.0 if i == 0 else -1.0
                sa += sign * a
                sx += sign * a * x
                sy += sign * a * y
        if sa > 0:
            return proj.inv(sx / sa, sy / sa)
    elif t in ("LineString", "MultiLineString"):
        sl = sx = sy = 0.0
        for line in lines_of(geom):
            pts = [proj.fwd(c) for c in line]
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                seg = math.hypot(x2 - x1, y2 - y1)
                sl += seg
                sx += seg * (x1 + x2) / 2
                sy += seg * (y1 + y2) / 2
        if sl > 0:
            return proj.inv(sx / sl, sy / sl)
    pts = [proj.fwd(c) for c in coords]
    return proj.inv(sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def weighted_centroid(items: Iterable[tuple[Coord, float]]) -> list[float]:
    """Weighted mean of ``(point, weight)`` pairs (plain mean if all weights 0)."""
    items = list(items)
    if not items:
        raise ValueError("no points")
    w = sum(max(wt, 0.0) for _, wt in items)
    if w <= 0:
        return [
            sum(p[0] for p, _ in items) / len(items),
            sum(p[1] for p, _ in items) / len(items),
        ]
    return [
        sum(p[0] * max(wt, 0.0) for p, wt in items) / w,
        sum(p[1] * max(wt, 0.0) for p, wt in items) / w,
    ]


def bbox(geom: dict) -> BBox:
    """``[min_lon, min_lat, max_lon, max_lat]`` of any geometry."""
    xs, ys = [], []
    for c in all_coords(geom):
        xs.append(c[0])
        ys.append(c[1])
    if not xs:
        raise ValueError("empty geometry")
    return [min(xs), min(ys), max(xs), max(ys)]


def bbox_union(boxes: Iterable[BBox | None]) -> BBox | None:
    """Union of bounding boxes; ``None`` entries are ignored, ``None`` if empty."""
    out: BBox | None = None
    for b in boxes:
        if not b:
            continue
        if out is None:
            out = list(b)
        else:
            out = [min(out[0], b[0]), min(out[1], b[1]), max(out[2], b[2]), max(out[3], b[3])]
    return out


def _point_in_ring(x: float, y: float, ring: Ring) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y):
            x_cross = xi + (y - yi) * (xj - xi) / (yj - yi)
            if x < x_cross:
                inside = not inside
        j = i
    return inside


def point_in_polygon(pt: Coord, geom: dict) -> bool:
    """True if ``pt`` lies inside a Polygon/MultiPolygon (holes excluded).

    Points exactly on an edge may be classified either way.
    """
    x, y = pt[0], pt[1]
    for poly in polygons_of(geom):
        if not poly:
            continue
        if not _point_in_ring(x, y, poly[0]):
            continue
        if any(_point_in_ring(x, y, hole) for hole in poly[1:]):
            continue
        return True
    return False


def haversine_m(a: Coord, b: Coord) -> float:
    """Great-circle distance in metres between two ``[lon, lat]`` points."""
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def _point_segment_dist(px, py, ax, ay, bx, by) -> tuple[float, float, float]:
    """Distance from P to segment AB, plus the closest point (projected units)."""
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    t = 0.0 if seg2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy), cx, cy


def distance_to_polygon_m(pt: Coord, geom: dict) -> float:
    """0 if ``pt`` is inside the (multi)polygon, else metres to its nearest edge."""
    if point_in_polygon(pt, geom):
        return 0.0
    proj = _LocalProjection(pt[1])
    px, py = proj.fwd(pt)
    best = math.inf
    for poly in polygons_of(geom):
        for ring in poly:
            pts = [proj.fwd(c) for c in ring]
            for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                d = _point_segment_dist(px, py, ax, ay, bx, by)[0]
                if d < best:
                    best = d
    return best


# ----------------------------------------------------------------- rounding


def round_geometry(geom: dict, ndigits: int = 6) -> dict:
    """Return a copy of ``geom`` with coordinates rounded to ``ndigits``.

    Consecutive duplicate positions created by rounding are dropped (rings
    keep at least 4 positions and stay closed).
    """
    t = geom.get("type")
    if t == "GeometryCollection":
        return {"type": t, "geometries": [round_geometry(g, ndigits) for g in geom["geometries"]]}
    depth = _DEPTH.get(t)
    if depth is None:
        raise ValueError(f"unsupported geometry type {t!r}")
    is_ring_level = t in ("Polygon", "MultiPolygon")

    def rnd(c):
        return [round(c[0], ndigits), round(c[1], ndigits)]

    def dedupe(seq, min_len):
        out = []
        for c in seq:
            if not out or out[-1] != c:
                out.append(c)
        return out if len(out) >= min_len else seq

    def walk(node, d):
        if d == 0:
            return rnd(node)
        if d == 1:
            seq = [rnd(c) for c in node]
            if t == "MultiPoint":
                return seq
            return dedupe(seq, 4 if is_ring_level else 2)
        return [walk(child, d - 1) for child in node]

    return {"type": t, "coordinates": walk(geom["coordinates"], depth)}


# ------------------------------------------------------------- simplification


def douglas_peucker(points: Sequence[Sequence[float]], tolerance: float) -> list:
    """Douglas–Peucker simplification of a polyline in planar units.

    The first and last points are always kept. Iterative (no recursion limit).
    """
    n = len(points)
    if n <= 2 or tolerance <= 0:
        return [list(p) for p in points]
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        ax, ay = points[i][0], points[i][1]
        bx, by = points[j][0], points[j][1]
        best, idx = -1.0, -1
        for k in range(i + 1, j):
            d = _point_segment_dist(points[k][0], points[k][1], ax, ay, bx, by)[0]
            if d > best:
                best, idx = d, k
        if idx != -1 and best > tolerance:
            keep[idx] = True
            stack.append((i, idx))
            stack.append((idx, j))
    return [list(points[k]) for k in range(n) if keep[k]]


def simplify_line(line: Sequence[Coord], tolerance_m: float) -> list[list[float]]:
    """Douglas–Peucker on a lon/lat polyline with a tolerance in metres.

    Endpoints are preserved exactly, so lines that share endpoints (e.g. OSM
    ways forming a shared border) stay topologically connected.
    """
    if len(line) <= 2 or tolerance_m <= 0:
        return [list(c) for c in line]
    proj = _projection_for(line)
    projected = [list(proj.fwd(c)) + [k] for k, c in enumerate(line)]
    kept = douglas_peucker(projected, tolerance_m)
    return [list(line[int(p[2])]) for p in kept]


def _simplify_ring(ring: Ring, tolerance_m: float) -> Ring:
    """Simplify a closed ring, keeping it closed and with >= 4 positions."""
    if len(ring) <= 4:
        return [list(c) for c in ring]
    open_ring = ring[:-1] if ring[0] == ring[-1] else ring
    proj = _projection_for(open_ring)
    p0 = proj.fwd(open_ring[0])
    # Split at the vertex farthest from the first one: two open chains.
    far = max(range(len(open_ring)), key=lambda k: math.dist(p0, proj.fwd(open_ring[k])))
    if far == 0:
        return [list(c) for c in ring]
    a = simplify_line(open_ring[: far + 1], tolerance_m)
    b = simplify_line(open_ring[far:] + [open_ring[0]], tolerance_m)
    out = a + b[1:]
    if len(out) < 4:
        return [list(c) for c in ring]
    return out


def simplify_geometry(geom: dict, tolerance_m: float) -> dict:
    """Simplify every line/ring of a geometry (tolerance in metres)."""
    t = geom.get("type")
    if t == "LineString":
        return {"type": t, "coordinates": simplify_line(geom["coordinates"], tolerance_m)}
    if t == "MultiLineString":
        return {"type": t, "coordinates": [simplify_line(ln, tolerance_m) for ln in geom["coordinates"]]}
    if t == "Polygon":
        return {"type": t, "coordinates": [_simplify_ring(r, tolerance_m) for r in geom["coordinates"]]}
    if t == "MultiPolygon":
        return {
            "type": t,
            "coordinates": [[_simplify_ring(r, tolerance_m) for r in p] for p in geom["coordinates"]],
        }
    return geom


# ------------------------------------------------------------ ring assembly


def assemble_rings(ways: Iterable[Sequence[Coord]]) -> list[Ring]:
    """Stitch open polylines (e.g. OSM relation member ways) into closed rings.

    Ways are joined where endpoints coincide exactly, reversing as needed.
    Raises ``ValueError`` if some ways cannot be closed into a ring.
    """
    pending = [[list(c) for c in w] for w in ways if len(w) >= 2]
    rings: list[Ring] = []
    while pending:
        ring = pending.pop(0)
        while ring[0] != ring[-1]:
            end = ring[-1]
            for k, w in enumerate(pending):
                if w[0] == end:
                    ring.extend(w[1:])
                    break
                if w[-1] == end:
                    ring.extend(list(reversed(w))[1:])
                    break
            else:
                raise ValueError(
                    f"cannot close ring: dangling end at {end} ({len(pending)} ways left)"
                )
            pending.pop(k)
        if len(ring) >= 4:
            rings.append(ring)
    return rings


def rings_to_geometry(outers: list[Ring], inners: list[Ring] | None = None) -> dict:
    """Build a Polygon/MultiPolygon from outer and inner rings.

    Each inner ring is attached to the (smallest) outer ring containing its
    first vertex; orphaned inner rings are dropped.
    """
    if not outers:
        raise ValueError("no outer rings")
    polys = [[o] for o in outers]
    areas = [area_m2({"type": "Polygon", "coordinates": [o]}) for o in outers]
    for inner in inners or []:
        hosts = [
            k
            for k, o in enumerate(outers)
            if point_in_polygon(inner[0], {"type": "Polygon", "coordinates": [o]})
        ]
        if hosts:
            polys[min(hosts, key=lambda k: areas[k])].append(inner)
    if len(polys) == 1:
        return {"type": "Polygon", "coordinates": polys[0]}
    return {"type": "MultiPolygon", "coordinates": polys}


# ---------------------------------------------------------------- line tools


def lines_inside(geom: dict, polygon: dict, buffer_m: float = 0.0) -> list[list[list[float]]]:
    """Parts of a (Multi)LineString whose vertices fall inside ``polygon``.

    A vertex counts as inside when it lies in the polygon or within
    ``buffer_m`` metres of it. Returns runs of consecutive inside vertices (a
    run may be a single vertex). This is a vertex-level approximation of
    clipping, adequate for street axes whose vertices are a few metres to
    tens of metres apart.
    """
    b = bbox(polygon)
    # Rough degree margin for the bbox prefilter (1 deg lat ~ 111 km; lon
    # degrees are shorter, so the lat-based margin is conservative for lon).
    margin = buffer_m / 111_000 / max(math.cos(math.radians((b[1] + b[3]) / 2)), 0.1)

    def inside(c) -> bool:
        if not (b[0] - margin <= c[0] <= b[2] + margin and b[1] - margin <= c[1] <= b[3] + margin):
            return False
        if point_in_polygon(c, polygon):
            return True
        return buffer_m > 0 and distance_to_polygon_m(c, polygon) <= buffer_m

    parts: list[list[list[float]]] = []
    for line in lines_of(geom):
        current: list[list[float]] = []
        for c in line:
            if inside(c):
                current.append(list(c))
            elif current:
                parts.append(current)
                current = []
        if current:
            parts.append(current)
    return parts


def midpoint_along(lines: list[Sequence[Coord]]) -> list[float] | None:
    """Point halfway along the total length of ``lines`` (``None`` if empty).

    Lines are walked in the given order; the point is guaranteed to lie on
    one of them, unlike a centroid of a curved street.
    """
    lines = [ln for ln in lines if ln]
    if not lines:
        return None
    proj = _projection_for(c for ln in lines for c in ln)
    segs = []
    total = 0.0
    for ln in lines:
        pts = [proj.fwd(c) for c in ln]
        for a, b in zip(pts, pts[1:]):
            d = math.dist(a, b)
            segs.append((a, b, d))
            total += d
    if total == 0:
        return list(lines[0][0])
    half = total / 2
    acc = 0.0
    for a, b, d in segs:
        if acc + d >= half and d > 0:
            t = (half - acc) / d
            return proj.inv(a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        acc += d
    return proj.inv(*segs[-1][1])


def _segment_intersection(a1, a2, b1, b2):
    """Intersection point of segments a1-a2 and b1-b2 (projected), or None."""
    d1x, d1y = a2[0] - a1[0], a2[1] - a1[1]
    d2x, d2y = b2[0] - b1[0], b2[1] - b1[1]
    den = d1x * d2y - d1y * d2x
    if den == 0:
        return None  # parallel / collinear: handled by the distance search
    ex, ey = b1[0] - a1[0], b1[1] - a1[1]
    t = (ex * d2y - ey * d2x) / den
    u = (ex * d1y - ey * d1x) / den
    if 0 <= t <= 1 and 0 <= u <= 1:
        return a1[0] + t * d1x, a1[1] + t * d1y
    return None


def closest_approach(a: dict, b: dict) -> tuple[list[float], float] | None:
    """Closest pair of points between two line geometries.

    Returns ``(point, distance_m)``: the crossing point with distance 0 when
    the lines intersect, else the midpoint of the closest pair of points.
    ``None`` if either input has no lines. Used to locate street
    intersections ("A / B" addresses).
    """
    la, lb = lines_of(a), lines_of(b)
    if not la or not lb:
        return None
    proj = _projection_for([c for ln in la + lb for c in ln])
    sa = [(p, q) for ln in la for p, q in zip(map(proj.fwd, ln), map(proj.fwd, ln[1:]))]
    sb = [(p, q) for ln in lb for p, q in zip(map(proj.fwd, ln), map(proj.fwd, ln[1:]))]
    if not sa or not sb:
        return None
    best_d, best_pt = math.inf, None
    for a1, a2 in sa:
        for b1, b2 in sb:
            hit = _segment_intersection(a1, a2, b1, b2)
            if hit is not None:
                return proj.inv(*hit), 0.0
            for p, (s1, s2) in ((a1, (b1, b2)), (a2, (b1, b2)), (b1, (a1, a2)), (b2, (a1, a2))):
                d, cx, cy = _point_segment_dist(p[0], p[1], s1[0], s1[1], s2[0], s2[1])
                if d < best_d:
                    best_d, best_pt = d, ((p[0] + cx) / 2, (p[1] + cy) / 2)
    return proj.inv(*best_pt), best_d
