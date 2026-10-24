/**
 * Minimal static server for development and e2e tests (no dependencies).
 *
 *   node tests/e2e/server.mjs [--port=8000] [--data=site|fixture] [--base=/sub/path/]
 *
 * --data=fixture  serve /data/* from tests/fixtures/site-data/ (tests never depend on real data)
 * --data=site     serve site/data/ as is (default)
 * --base          mount the site under a sub-path, like GitHub Pages project sites (/repo/)
 * Archive copies (/sources/<file_id>.xlsx) fall back to data/raw/ when site/sources/ is absent; with
 * --data=fixture, /sources/* is served from tests/fixtures/site-data/sources/ first (BAiPP + RWDZ copies).
 */
import http from 'node:http';
import { createReadStream, existsSync, statSync } from 'node:fs';
import { extname, join, normalize, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(fileURLToPath(new URL('../..', import.meta.url)));
const SITE = join(ROOT, 'site');
const FIXTURE = join(ROOT, 'tests', 'fixtures', 'site-data');
const RAW = join(ROOT, 'data', 'raw');

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.geojson': 'application/geo+json; charset=utf-8',
  '.csv': 'text/csv; charset=utf-8',
  '.xml': 'application/xml; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.ico': 'image/x-icon',
  '.map': 'application/json; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
  '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
};

function within(base, p) {
  const r = resolve(p);
  return r === base || r.startsWith(base + sep);
}

/** Resolve a URL path to a file on disk (or null). */
export function resolveFile(urlPath, { data = 'site' } = {}) {
  let p;
  try {
    p = decodeURIComponent(urlPath.split('?')[0]);
  } catch {
    return null; // malformed percent-encoding (e.g. "/%E0%A4%A"): answered with 404, never a crash
  }
  if (p.endsWith('/')) p += 'index.html';
  p = normalize(p).replace(/^([/\\])+/, '');
  const candidates = [];
  if (data === 'fixture' && p.startsWith('data/')) candidates.push([FIXTURE, join(FIXTURE, p.slice(5))]);
  else {
    // The fixture carries its own mirrored files (BAiPP workbooks, reduced RWDZ extracts) under sources/.
    if (data === 'fixture' && p.startsWith('sources/')) candidates.push([FIXTURE, join(FIXTURE, p)]);
    candidates.push([SITE, join(SITE, p)]);
  }
  if (p.startsWith('sources/') && p.endsWith('.xlsx')) candidates.push([RAW, join(RAW, p.slice(8))]);
  for (const [base, file] of candidates) {
    if (!within(base, file)) continue;
    if (existsSync(file) && statSync(file).isFile()) return file;
  }
  return null;
}

/**
 * Start the server.
 * @returns {Promise<{url: string, close: () => Promise<void>}>}
 */
export function startServer({ port = 0, data = 'site', base = '/', quiet = true } = {}) {
  const prefix = base.endsWith('/') ? base : `${base}/`;
  const server = http.createServer((req, res) => {
    let url;
    try {
      url = new URL(req.url, 'http://localhost');
    } catch {
      res.writeHead(400, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end('Bad request');
      return;
    }
    if (!url.pathname.startsWith(prefix)) {
      if (url.pathname === prefix.slice(0, -1)) { res.writeHead(301, { Location: prefix }); res.end(); return; }
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end('Not found');
      return;
    }
    const file = resolveFile(`/${url.pathname.slice(prefix.length)}`, { data });
    if (!quiet) console.log(req.method, url.pathname, file ? 200 : 404);
    if (!file) {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end('Not found');
      return;
    }
    const type = TYPES[extname(file).toLowerCase()] || 'application/octet-stream';
    res.writeHead(200, { 'Content-Type': type, 'Cache-Control': 'no-cache', 'Content-Length': statSync(file).size });
    if (req.method === 'HEAD') { res.end(); return; }
    const stream = createReadStream(file);
    stream.on('error', () => {
      if (!res.headersSent) res.writeHead(500);
      res.end();
    });
    stream.pipe(res);
  });
  return new Promise((ok) => {
    server.listen(port, '127.0.0.1', () => {
      const { port: p } = server.address();
      ok({
        url: `http://127.0.0.1:${p}${prefix}`,
        close: () => new Promise((done) => { server.close(() => done()); server.closeIdleConnections?.(); }),
      });
    });
  });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = Object.fromEntries(process.argv.slice(2).map((a) => a.replace(/^--/, '').split('=')));
  const { url } = await startServer({
    port: Number(args.port || 8000), data: args.data || 'site', base: args.base || '/', quiet: !('verbose' in args),
  });
  console.log(`wzSearch: ${url}  (dane: ${args.data || 'site'})  – Ctrl+C, aby zakończyć`);
}
