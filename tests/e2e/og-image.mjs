/**
 * Render the Open Graph preview image site/img/og.png (1200×630) from the current data:
 * district + neighbourhood outlines (site/data/areas.geojson), every located building permit / notification
 * (permits.json, when present) as a small faint triangle and every located planning record on top.
 * Uses the system Google Chrome via playwright-core.   Usage: npm run og
 */
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const ROOT = resolve(fileURLToPath(new URL('../..', import.meta.url)));
const rec = JSON.parse(readFileSync(`${ROOT}/site/data/records.json`, 'utf8'));
const areas = JSON.parse(readFileSync(`${ROOT}/site/data/areas.geojson`, 'utf8'));
const permitsPath = `${ROOT}/site/data/permits.json`;
const permits = existsSync(permitsPath) ? (JSON.parse(readFileSync(permitsPath, 'utf8')).records || []) : [];
const W = 460, H = 440;
const all = [];
for (const f of areas.features) for (const ring of f.geometry.type === 'Polygon' ? f.geometry.coordinates : f.geometry.coordinates.flat()) all.push(...ring);
const lons = all.map((p) => p[0]); const lats = all.map((p) => p[1]);
const minX = Math.min(...lons), maxX = Math.max(...lons), minY = Math.min(...lats), maxY = Math.max(...lats);
const kx = Math.cos((52.24 * Math.PI) / 180);
const sx = (W - 40) / ((maxX - minX) * kx), sy = (H - 40) / (maxY - minY), s = Math.min(sx, sy);
const ox = (W - (maxX - minX) * kx * s) / 2, oy = (H - (maxY - minY) * s) / 2;
const P = ([x, y]) => [ox + (x - minX) * kx * s, oy + (maxY - y) * s];
const path = (rings) => rings.map((r) => 'M' + r.map((p) => P(p).map((v) => v.toFixed(1)).join(',')).join('L') + 'Z').join('');
let svg = '';
const ringsOf = (f) => (f.geometry.type === 'Polygon' ? f.geometry.coordinates : f.geometry.coordinates.flat());
const district = areas.features.find((f) => f.properties.slug === '_district');
svg += `<path d="${path(ringsOf(district))}" fill="#ffffff"/>`;
for (const f of areas.features) {
  if (f.properties.slug !== '_district') svg += `<path d="${path(ringsOf(f))}" fill="none" stroke="#d6d0c4" stroke-width="1.2" stroke-dasharray="4 4"/>`;
}
svg += `<path d="${path(ringsOf(district))}" fill="none" stroke="#1b1d22" stroke-width="2.5" stroke-linejoin="round"/>`;
const col = { wz: '#4f46e5', cp: '#0d9488', ws: '#d97706', pb: '#86198f', zg: '#116611' };
// Permits first, small and faint: they show where building happens without hiding the planning records.
for (const r of permits) {
  if (r.geo?.lat == null) continue;
  const [x, y] = P([r.geo.lon, r.geo.lat]);
  const c = col[r.kind] || '#6b7280';
  const d = r.kind === 'zg' ? -1 : 1; // pozwolenie ▲, zgłoszenie ▼ (as on the map)
  svg += `<path d="M${x.toFixed(1)},${(y - 3.2 * d).toFixed(1)}L${(x + 3).toFixed(1)},${(y + 2.2 * d).toFixed(1)}L${(x - 3).toFixed(1)},${(y + 2.2 * d).toFixed(1)}Z" fill="${c}" fill-opacity="0.38"/>`;
}
for (const r of rec.records) {
  if (r.geo?.lat == null) continue;
  const [x, y] = P([r.geo.lon, r.geo.lat]);
  const c = col[r.kind] || '#6b7280';
  if (r.kind === 'cp') svg += `<rect x="${(x - 4).toFixed(1)}" y="${(y - 4).toFixed(1)}" width="8" height="8" rx="1.5" transform="rotate(45 ${x.toFixed(1)} ${y.toFixed(1)})" fill="${c}" stroke="#fff" stroke-width="1.5"/>`;
  else if (r.kind === 'ws') svg += `<rect x="${(x - 4).toFixed(1)}" y="${(y - 4).toFixed(1)}" width="8" height="8" rx="1.5" fill="${c}" stroke="#fff" stroke-width="1.5"/>`;
  else svg += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4.5" fill="${c}" stroke="#fff" stroke-width="1.5"/>`;
}
const n = rec.records.length;
const m = permits.length;
/** Polish plural: [one, few (2–4, not 12–14), many]. */
const pl = (k, [one, few, many]) => (k === 1 ? one : k % 10 >= 2 && k % 10 <= 4 && !(k % 100 >= 12 && k % 100 <= 14) ? few : many);
const lead = m
  ? `${n} ${pl(n, ['decyzja', 'decyzje', 'decyzji'])} i ${pl(n, ['wszczęcie', 'wszczęcia', 'wszczęć'])} (WZ, cel publiczny) oraz ${m} ${pl(m, ['pozwolenie', 'pozwolenia', 'pozwoleń'])} na budowę i ${pl(m, ['zgłoszenie', 'zgłoszenia', 'zgłoszeń'])} – z mapą, filtrami i linkiem do źródła.`
  : `${n} ${pl(n, ['wpis', 'wpisy', 'wpisów'])}: decyzje o warunkach zabudowy, lokalizacje celu publicznego i wszczęte postępowania – z mapą, filtrami i linkiem do pliku źródłowego.`;
const html = `<!doctype html><html lang="pl"><head><meta charset="utf-8"><style>
*{box-sizing:border-box;margin:0}body{width:1200px;height:630px;background:#f6f4ef;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#1b1d22;display:flex;overflow:hidden}
.l{flex:1;min-width:0;padding:64px 0 56px 72px;display:flex;flex-direction:column}
.brand{display:flex;align-items:center;gap:14px;font-size:30px;font-weight:750;letter-spacing:-.02em}
.brand small{display:block;font-size:17px;font-weight:500;color:#5d6270;letter-spacing:0}
h1{margin-top:56px;font-size:58px;line-height:1.06;font-weight:780;letter-spacing:-.035em;max-width:600px}
p{margin-top:24px;font-size:23px;line-height:1.4;color:#454a54;max-width:560px}
.foot{margin-top:auto;display:flex;gap:20px;align-items:center;font-size:17px;color:#5d6270;white-space:nowrap}
.k{display:inline-flex;align-items:center;gap:8px}.d{width:13px;height:13px;border-radius:50%;background:#4f46e5}.c{width:12px;height:12px;background:#0d9488;transform:rotate(45deg)}.s{width:12px;height:12px;background:#d97706;border-radius:2px}.t{width:0;height:0;border-left:7px solid transparent;border-right:7px solid transparent;border-bottom:12px solid #86198f}
.r{width:600px;display:grid;place-items:center;padding-right:56px}
.card{background:#efece5;border-radius:28px;padding:30px;box-shadow:inset 0 0 0 1px #e4dfd5}
.pill{position:absolute;right:76px;top:58px;background:#fff;border:1px solid #e4dfd5;border-radius:999px;padding:8px 16px;font-size:16px;font-weight:600;color:#454a54}
</style></head><body>
<div class="l"><div class="brand"><svg viewBox="0 0 32 32" width="52" height="52"><rect width="32" height="32" rx="8" fill="#1b1d22"/><path d="M8 8h7v7H8zM17 8h7v7h-7zM8 17h7v7H8z" fill="none" stroke="#f6f4ef" stroke-width="1.7"/><rect x="17" y="17" width="7" height="7" rx="1.2" fill="#e0457b"/></svg><div>wzSearch<small>Praga-Południe · Warszawa · serwis nieoficjalny</small></div></div>
<h1>Co się planuje na Pradze&#8209;Południe?</h1>
<p>${lead}</p>
<div class="foot"><span class="k"><span class="d"></span>WZ</span><span class="k"><span class="c"></span>Cel publiczny</span><span class="k"><span class="s"></span>Wszczęcie</span>${m ? '<span class="k"><span class="t"></span>Pozwolenie</span>' : ''}</div></div>
<div class="r"><div class="card"><svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${svg}</svg></div></div>
</body></html>`;
const browser = await chromium.launch({ channel: 'chrome' });
const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
await page.setContent(html);
await page.screenshot({ path: `${ROOT}/site/img/og.png` });
await browser.close();
console.log('ok', n, m);
