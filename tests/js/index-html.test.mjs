import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const SITE = resolve(fileURLToPath(new URL('../../site', import.meta.url)));
const html = readFileSync(join(SITE, 'index.html'), 'utf8');

function jsFiles(dir) {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) return jsFiles(p);
    return name.endsWith('.js') ? [relative(SITE, p).split('\\').join('/')] : [];
  });
}

test('index.html modulepreloads exactly the ES modules in site/js (no stale or missing hints)', () => {
  const hinted = [...html.matchAll(/<link rel="modulepreload" href="([^"]+)">/g)].map((m) => m[1]).sort();
  assert.deepEqual(hinted, jsFiles(join(SITE, 'js')).sort());
});

test('the data files start downloading early (inline fetch, no <link rel=preload as=fetch>) and data.js takes them over', () => {
  // <link rel=preload as=fetch> ignored fetch's cache:'no-cache' (stale data after a deploy) and WebKit fetched twice.
  assert.ok(!/<link rel="preload"[^>]*as="fetch"/.test(html), 'a data preload link is back');
  const early = /\[('data\/[^']+'(?:, 'data\/[^']+')*)\]\.forEach/.exec(html);
  assert.ok(early, 'no early fetch list in index.html');
  const files = early[1].split(', ').map((x) => x.replace(/'/g, '')).sort();
  assert.deepEqual(files, ['data/records.json', 'data/sources.json']);
  assert.match(html, /fetch\(u, \{ cache: 'no-cache' \}\)/);
  const dataJs = readFileSync(join(SITE, 'js', 'data.js'), 'utf8');
  assert.ok(dataJs.includes('__wzEarly'), 'data.js does not use the early requests');
  for (const p of files) assert.ok(dataJs.includes(p.replace('data/', '')), `${p} is not loaded by data.js`);
  assert.ok(existsSync(join(SITE, 'js', 'main.js')));
});

test('a module that fails to load shows a message instead of the skeleton forever', () => {
  assert.match(html, /<script type="module" src="js\/main\.js" onerror="window\.__wzBootFail && window\.__wzBootFail\(\)"><\/script>/);
  assert.match(html, /window\.__wzBootFail = function/);
});
