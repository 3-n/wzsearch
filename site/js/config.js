/**
 * Site configuration — the only file to edit when deploying a fork.
 * Empty strings hide the corresponding links.
 */

/** Public source-code repository, e.g. "https://github.com/<user>/wzSearch". */
export const REPO_URL = '';

/** Where people can report data/UI problems, e.g. "https://github.com/<user>/wzSearch/issues". */
export const ISSUES_URL = '';

/** Contact e-mail (optional). */
export const CONTACT_EMAIL = '';

/**
 * Geoportal link for a parcel id (TERYT format "146507_8.0124.46/4").
 * Verified 2026-10-23: the current Geoportal viewer (imapnext) zooms to the parcel and opens its
 * identification panel. The legacy viewer also works:
 * "https://mapy.geoportal.gov.pl/imap/Imgp_2.html?identifyParcel=".
 */
export const GEOPORTAL_PARCEL_URL = 'https://mapy.geoportal.gov.pl/imapnext/imap/?identifyParcel=';

/** Official index page of the source publication (fallback when data has none). */
export const SOURCE_INDEX_URL = 'https://pragapld.um.warszawa.pl/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych';

/** The city architecture office's lists (BAiPP; fallback when records.json → datasets.baipp has no url). */
export const BAIPP_URL = 'https://architektura.um.warszawa.pl/postepowania-i-decyzje';

/** Number of result cards rendered per batch. */
export const PAGE_SIZE = 50;

/** Map defaults (Praga-Południe). */
export const MAP_CENTER = [52.2385, 21.095];
export const MAP_ZOOM = 13;

/**
 * Base map tiles. OpenStreetMap's standard tiles, muted with a CSS filter (light and dark theme).
 * Note (2026-10-23): CARTO basemaps (light_all / dark_all / voyager) now answer keyless requests
 * with an "API KEY REQUIRED" tile, so they cannot be used without an account. To switch providers,
 * change `url`/`attribution` (and set `muted: false` for an already-light style).
 * OSM tile usage policy: https://operations.osmfoundation.org/policies/tiles/ (fine for low traffic).
 */
export const BASEMAP = {
  url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">autorzy OpenStreetMap</a> (ODbL)',
  maxNativeZoom: 19,
  muted: true,
};

/**
 * GUGiK WMS services (verified with GetMap in EPSG:3857 on 2026-10-23).
 * KIEG answers with an HTTP 302 to a mirror host (integracja01…), which browsers follow transparently.
 */
export const WMS = {
  ortho: {
    url: 'https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMS/StandardResolution',
    layers: 'Raster',
    format: 'image/jpeg',
    attribution: 'Ortofotomapa &copy; <a href="https://www.geoportal.gov.pl">GUGiK</a>',
  },
  parcels: {
    url: 'https://integracja.gugik.gov.pl/cgi-bin/KrajowaIntegracjaEwidencjiGruntow',
    layers: 'dzialki,numery_dzialek',
    format: 'image/png',
    minZoom: 16,
    attribution: 'Granice działek &copy; <a href="https://www.geoportal.gov.pl">GUGiK</a> (KIEG)',
  },
};
