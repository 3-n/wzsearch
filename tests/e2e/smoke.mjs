/**
 * End-to-end smoke test + screenshots, driving the SYSTEM Google Chrome via playwright-core
 * (no browser download). Serves site/ under a sub-path (like GitHub Pages) with FIXTURE data.
 *
 *   node tests/e2e/smoke.mjs                 # fixture data (tests/fixtures/site-data)
 *   node tests/e2e/smoke.mjs --data=site     # whatever is in site/data (real pipeline output)
 *   node tests/e2e/smoke.mjs --only=desktop-light     # or mobile-dark, robustness, webkit
 *
 * Screenshots: tests/e2e/output/{desktop,mobile}-{light,dark}-*.png
 */
import { chromium, webkit } from 'playwright-core';
import { existsSync, mkdirSync, readFileSync, rmSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { startServer } from './server.mjs';

const ROOT = resolve(fileURLToPath(new URL('../..', import.meta.url)));
const OUT = join(ROOT, 'tests', 'e2e', 'output');
const args = Object.fromEntries(process.argv.slice(2).map((a) => a.replace(/^--/, '').split('=')));
const DATA = args.data || 'fixture';
const ONLY = args.only || null;
const THIRD_PARTY = /openstreetmap\.org|geoportal\.gov\.pl|gugik\.gov\.pl/;
/** Optional files the About page probes or the app loads lazily (a 404 for them is expected and handled). */
const OPTIONAL = /\/(data\/records\.csv|data\/permits\.csv|data\/permits\.json|data\/parcels-permits\.geojson|feed\.xml|data\/areas\.geojson)$/;

rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });

const dataDir = DATA === 'fixture' ? join(ROOT, 'tests', 'fixtures', 'site-data') : join(ROOT, 'site', 'data');
const recordsDoc = JSON.parse(readFileSync(join(dataDir, 'records.json'), 'utf8'));
const sourcesDoc = JSON.parse(readFileSync(join(dataDir, 'sources.json'), 'utf8'));
/** v2 data: building permits (opt-in kinds pb/zg) in a lazily loaded permits.json. */
const permitsPath = join(dataDir, 'permits.json');
const permitsDoc = existsSync(permitsPath) ? JSON.parse(readFileSync(permitsPath, 'utf8')) : null;
const HAS_PERMITS = Boolean(permitsDoc?.records?.length && recordsDoc.kinds?.pb);
const allRecords = [...recordsDoc.records, ...(permitsDoc?.records || [])];
const byIdAll = new Map(allRecords.map((r) => [r.id, r]));

const results = [];
let currentGroup = '';
async function check(name, fn) {
  const label = `${currentGroup} › ${name}`;
  try {
    await fn();
    results.push({ label, ok: true });
    console.log(`  ✓ ${name}`);
  } catch (err) {
    results.push({ label, ok: false, err });
    console.log(`  ✗ ${name}\n    ${String(err?.message || err).split('\n').slice(0, 6).join('\n    ')}`);
  }
}
function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const server = await startServer({ data: DATA, base: '/wzsearch/' });
const browser = await chromium.launch({ channel: 'chrome' });

/** New page with console-error capture. */
async function newPage(opts) {
  const context = await browser.newContext({
    locale: 'pl-PL', timezoneId: 'Europe/Warsaw', acceptDownloads: true,
    permissions: ['geolocation', 'clipboard-read', 'clipboard-write'],
    geolocation: { latitude: 52.2549, longitude: 21.0762 },
    ...opts,
  });
  const page = await context.newPage();
  const errors = [];
  const external = [];
  page.on('console', (m) => {
    if (m.type() !== 'error') return;
    const loc = m.location()?.url || '';
    if (THIRD_PARTY.test(loc) || THIRD_PARTY.test(m.text())) external.push(m.text());
    else if (OPTIONAL.test(loc) && /404/.test(m.text())) external.push(`${loc} 404 (optional)`);
    else errors.push(`${m.text()} ${loc}`);
  });
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  page.on('requestfailed', (r) => {
    const why = r.failure()?.errorText || '';
    // ERR_ABORTED = request cancelled by a navigation started by the test itself, not an app error.
    if (THIRD_PARTY.test(r.url()) || r.url().startsWith('data:') || /ERR_ABORTED/.test(why)) return;
    errors.push(`requestfailed: ${r.url()} ${why}`);
  });
  return { context, page, errors, external };
}

async function waitReady(page) {
  await page.waitForSelector('body[data-ready="true"]', { timeout: 15000 });
}
async function settle(page, ms = 400) {
  await page.waitForTimeout(ms);
}
async function shot(page, name) {
  await page.waitForTimeout(900); // tiles/animations
  await page.screenshot({ path: join(OUT, `${name}.png`) });
}
const hashOf = (page) => page.evaluate(() => window.location.hash);

const kindLabel = (k) => recordsDoc.kinds?.[k]?.label || k;
const OPT_IN = /^(pb|zg)-/;

async function desktopSuite(scheme) {
  currentGroup = `desktop-${scheme}`;
  console.log(`\n${currentGroup}`);
  const { context, page, errors, external } = await newPage({ viewport: { width: 1440, height: 900 }, colorScheme: scheme });
  const url = server.url;

  await check('loads under a sub-path with relative URLs and renders cards', async () => {
    await page.goto(url);
    await waitReady(page);
    const n = await page.locator('.cards .card').count();
    assert(n > 0, 'no cards');
    const count = await page.locator('#results-count').innerText();
    assert(count.replace(/\s/g, '').includes(String(recordsDoc.records.length)), `count text "${count}"`);
    await page.waitForSelector('.leaflet-container .leaflet-marker-icon', { timeout: 10000 });
    assert(await page.locator('.leaflet-container').count() === 1, 'map not initialised');
  });
  await shot(page, `${currentGroup}-explore`);

  await check('time to interactive data (navigation → data-ready) is reported', async () => {
    const ms = await page.evaluate(() => {
      const nav = performance.getEntriesByType('navigation')[0];
      const mark = performance.getEntriesByName('wz:ready')[0];
      return mark ? Math.round(mark.startTime - (nav?.startTime || 0)) : null;
    });
    assert(ms != null, 'no wz:ready performance mark');
    console.log(`    (data ready after ${ms} ms, ${recordsDoc.records.length} records)`);
  });

  await check('every interactive element has an accessible name', async () => {
    const unnamed = await page.evaluate(() => {
      const name = (el) => (el.getAttribute('aria-label') || '').trim()
        || (el.getAttribute('aria-labelledby') || '').split(' ').map((id) => document.getElementById(id)?.textContent || '').join('').trim()
        || (el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`)?.textContent.trim())
        || el.closest('label')?.textContent.trim() || el.textContent.trim() || (el.getAttribute('title') || '').trim();
      return [...document.querySelectorAll('button, a[href], input:not([type=hidden]), select, [role=button], [tabindex="0"]')]
        .filter((el) => el.getClientRects().length && !el.closest('[hidden],[inert]') && !name(el))
        .map((el) => el.outerHTML.slice(0, 120));
    });
    assert(unnamed.length === 0, unnamed.join('\n'));
  });

  await check('"/" focuses the search box', async () => {
    await page.locator('#results-count').click();
    await page.keyboard.press('/');
    await settle(page, 150);
    assert(await page.evaluate(() => document.activeElement?.id === 'q'), 'search not focused');
  });

  await check('search "przedszkole" filters, highlights and updates the URL', async () => {
    await page.locator('#q').fill('przedszkole');
    await settle(page);
    const n = await page.locator('.cards .card').count();
    assert(n > 0 && n < recordsDoc.records.length, `unexpected count ${n}`);
    const marks = await page.locator('.cards .card mark').allInnerTexts();
    assert(marks.some((m) => /przedszkol/i.test(m)), 'no highlight');
    const texts = await page.locator('.cards .card').allInnerTexts();
    assert(texts.every((t) => /przedszkol|szkoł/i.test(t)), 'card without match');
    assert((await hashOf(page)).includes('q=przedszkole'), 'hash missing q');
    const live = await page.locator('#results-live').textContent();
    await settle(page, 800);
    assert(/Znaleziono/.test(await page.locator('#results-live').textContent() || live || ''), 'aria-live not updated');
  });
  await shot(page, `${currentGroup}-search`);

  await check('diacritics-insensitive search (drwecka = Drwęcka)', async () => {
    await page.locator('#q').fill('drwecka');
    await settle(page);
    const t = await page.locator('.cards .card').allInnerTexts();
    assert(t.length > 0 && t.every((x) => /Drw[eę]c/i.test(x)), `cards without Drwęcka: ${t.find((x) => !/Drw[eę]c/i.test(x))?.slice(0, 80)}`);
    await page.locator('#q').fill('');
    await settle(page);
  });

  await check('other word forms match ("budynek" finds "budynku") and are highlighted', async () => {
    const withForm = recordsDoc.records.filter((r) => /\bbudynku\b/i.test(r.investment || ''));
    assert(withForm.length > 0, 'test data has no "budynku"');
    await page.locator('#q').fill('budynek');
    await settle(page);
    const marks = await page.locator('.cards .card mark').allInnerTexts();
    assert(marks.some((m) => /^budynku$/i.test(m)), `no highlighted "budynku" among ${[...new Set(marks)].slice(0, 6)}`);
    const n = Number((await page.locator('#results-count strong').innerText()).replace(/\D/g, ''));
    assert(n >= withForm.length, `only ${n} results, ${withForm.length} records say "budynku"`);
  });

  await check('a parcel-number search explains the match on the card ("Działki: …")', async () => {
    const rec = recordsDoc.records.find((r) => (r.parcels || []).some((p) => /^\d+\/\d+$/.test(p.number)));
    const num = rec.parcels.find((p) => /^\d+\/\d+$/.test(p.number)).number;
    await page.locator('#q').fill(num);
    await settle(page);
    const card = page.locator(`.cards .card[data-id="${rec.id}"]`);
    assert(await card.count() === 1, `record ${rec.id} not found by parcel ${num}`);
    const ctx = await card.locator('.card__match').innerText();
    assert(/^Działki:/.test(ctx) && ctx.includes(num), `match line "${ctx}"`);
    assert((await card.locator('.card__match mark').allInnerTexts()).includes(num), 'parcel number not highlighted');
    await page.locator('#q').fill('');
    await settle(page);
  });

  await check('kind filter ("tylko" next to a kind) → only that kind, rodzaj= in URL, facet counts', async () => {
    // The planning kinds are ticked by default; "tylko" (shown on hover/focus) keeps just one.
    const row = page.locator('#filters .opt', { has: page.getByRole('checkbox', { name: new RegExp(kindLabel('wz')) }) });
    assert(await page.getByRole('checkbox', { name: new RegExp(kindLabel('wz')) }).isChecked(), 'WZ not ticked by default');
    await row.hover();
    await row.getByRole('button', { name: `Pokaż tylko: ${kindLabel('wz')}` }).click();
    await settle(page);
    const kinds = await page.locator('.cards .card').evaluateAll((els) => els.map((e) => e.dataset.kind));
    assert(kinds.length > 0 && kinds.every((k) => k === 'wz'), `kinds ${[...new Set(kinds)]}`);
    assert((await hashOf(page)).includes('rodzaj=wz'), 'hash missing rodzaj');
    const chip = await page.locator('.chips .chip').first().innerText();
    assert(/Rodzaj/.test(chip), `chip ${chip}`);
  });

  let openedId = null;
  let openedTitle = null;
  await check('open detail from a card: provenance, raw source table, permalink', async () => {
    const card = page.locator('.cards .card').first();
    openedId = await card.getAttribute('data-id');
    await card.locator('.card__link').click();
    await page.waitForSelector('#detail .detail__title');
    assert((await hashOf(page)).startsWith(`#/wpis/${encodeURIComponent(openedId)}`), 'hash not a record route');
    openedTitle = await page.locator('#detail .detail__title').innerText();
    // focus moves in the next animation frame
    await page.waitForFunction(() => document.activeElement?.id === 'detail-title', null, { timeout: 2000 }).catch(() => {});
    assert(await page.evaluate(() => document.activeElement?.id === 'detail-title'), 'focus not moved to detail title');
    const orig = page.locator('#detail a', { hasText: 'Plik XLSX (oryginał)' }).first();
    // district (pragapld…) or city architecture office (architektura…) files, both on *.um.warszawa.pl
    assert(/^https:\/\/(pragapld|architektura)\.um\.warszawa\.pl\/documents\//.test(await orig.getAttribute('href')), 'bad original link');
    const pageLink = page.locator('#detail a', { hasText: 'Strona źródłowa' }).first();
    assert(/^https:\/\/(pragapld|architektura)\.um\.warszawa\.pl\/(-\/|postepowania-i-decyzje)/.test(await pageLink.getAttribute('href')), 'bad page link');
    const arch = page.locator('#detail a', { hasText: 'Kopia archiwalna' }).first();
    assert(/^sources\/[0-9a-f]{10}\.xlsx$/.test(await arch.getAttribute('href')), 'bad archive link');
    await page.locator('#detail .prov__raw summary').first().click();
    assert(await page.locator('#detail .table--raw tbody tr').count() > 2, 'raw table empty');
  });
  await shot(page, `${currentGroup}-detail`);

  await check('archive copy is downloadable (relative URL under sub-path)', async () => {
    const href = await page.locator('#detail a', { hasText: 'Kopia archiwalna' }).first().getAttribute('href');
    const res = await page.request.get(new URL(href, server.url).href);
    assert(res.status() === 200, `status ${res.status()}`);
  });

  await check('→ / ← move to next/previous record', async () => {
    await page.locator('#detail-title').focus();
    await page.keyboard.press('ArrowRight');
    await settle(page);
    const t2 = await page.locator('#detail .detail__title').innerText();
    assert(t2 && (await hashOf(page)) !== `#/wpis/${openedId}`, 'did not move');
    await page.keyboard.press('ArrowLeft');
    await settle(page);
    assert((await page.locator('#detail .detail__title').innerText()) === openedTitle, 'did not move back');
  });

  await check('permalink opens the same record in a fresh page', async () => {
    const link = page.url();
    const p2 = await context.newPage();
    await p2.goto(link);
    await waitReady(p2);
    await p2.waitForSelector('#detail .detail__title');
    assert((await p2.locator('#detail .detail__title').innerText()) === openedTitle, 'different record');
    await p2.close();
  });

  await check('Esc closes the detail and returns focus to the originating card', async () => {
    await page.keyboard.press('Escape');
    await settle(page);
    assert(await page.locator('#detail').isHidden(), 'detail still visible');
    const focusedId = await page.evaluate(() => document.activeElement?.closest('.card')?.dataset.id);
    assert(focusedId === openedId, `focus on ${focusedId}, expected ${openedId}`);
    assert(!(await hashOf(page)).includes('/wpis/'), 'still on record route');
  });

  await check('back/forward work (closing the detail was a history step back)', async () => {
    await page.goForward();
    await settle(page);
    assert((await hashOf(page)).includes('/wpis/'), `forward did not reopen record: ${await hashOf(page)}`);
    assert(await page.locator('#detail').isVisible(), 'detail hidden after forward');
    await page.goBack();
    await settle(page);
    assert(!(await hashOf(page)).includes('/wpis/'), 'back did not close record');
    await page.goBack();
    await settle(page);
    assert(!(await hashOf(page)).includes('rodzaj=wz'), `back did not undo the kind filter: ${await hashOf(page)}`);
    assert((await page.locator('.cards .card').count()) > 0, 'no cards');
    await page.goForward();
    await settle(page);
    assert((await hashOf(page)).includes('rodzaj=wz'), 'forward did not restore the kind filter');
  });

  await check('timeline: drag selects a month range (od/do in URL)', async () => {
    await page.getByRole('button', { name: 'Wyczyść filtry' }).click().catch(() => {});
    await page.locator('.chips .chip__x').first().click().catch(() => {});
    await settle(page);
    const box = await page.locator('.timeline__chart').boundingBox();
    await page.mouse.move(box.x + box.width * 0.55, box.y + box.height * 0.5);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * 0.85, box.y + box.height * 0.5, { steps: 6 });
    await page.mouse.up();
    await settle(page);
    const h = await hashOf(page);
    assert(/od=\d{4}-\d{2}/.test(h) && /do=\d{4}-\d{2}/.test(h), `hash ${h}`);
    await page.getByRole('button', { name: 'Wyczyść okres' }).click();
    await settle(page);
    assert(!/od=/.test(await hashOf(page)), 'period not cleared');
  });

  await check('street combobox (keyboard) adds a street filter', async () => {
    const input = page.getByRole('combobox', { name: 'Ulica' });
    await input.fill('drw');
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Enter');
    await settle(page);
    assert(/ulica=drwecka/.test(await hashOf(page)), `hash ${await hashOf(page)}`);
    const t = await page.locator('.cards .card').allInnerTexts();
    assert(t.length >= 1 && t.every((x) => /Drw[eę]c/i.test(x)), 'street filter not applied');
  });

  await check('no-results state offers one-click suggestions', async () => {
    await page.locator('#q').fill('zzzqqq');
    await settle(page);
    assert(await page.locator('.empty').isVisible(), 'empty state hidden');
    const sugg = page.locator('.suggestion').first();
    assert(await sugg.count() === 1, 'no suggestion');
    await page.locator('.empty').getByRole('button', { name: /Wyczyść wszystkie filtry/ }).click();
    await settle(page);
    assert((await page.locator('.cards .card').count()) > 0, 'clear did not restore results');
    assert((await hashOf(page)) === '#/' || (await hashOf(page)) === '', `hash after clear ${await hashOf(page)}`);
  });

  await check('CSV export = filtered set, UTF-8 BOM, semicolons, source URLs, v2 columns', async () => {
    const row = page.locator('#filters .opt', { has: page.getByRole('checkbox', { name: new RegExp(kindLabel('cp')) }) });
    await row.hover();
    await row.getByRole('button', { name: `Pokaż tylko: ${kindLabel('cp')}` }).click();
    await settle(page);
    const n = Number((await page.locator('#results-count strong').innerText()).replace(/\D/g, ''));
    const [dl] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: /CSV/ }).click()]);
    const file = join(OUT, 'export.csv');
    await dl.saveAs(file);
    const text = readFileSync(file, 'utf8');
    assert(text.charCodeAt(0) === 0xfeff, 'no BOM');
    assert(text.split('\r\n')[0].startsWith('﻿id;rodzaj;'), 'bad header');
    assert(text.split('\r\n')[0].endsWith(';arkusz_wiersz;zrodlo_danych;organ;rozstrzygniecie;data_wniosku;nr_w_rejestrze;znak_sprawy_urzedu;zakres_robot;kategoria_obiektu;kubatura_m3'), 'v2 columns missing');
    const permalinks = text.match(/#\/wpis\//g) || [];
    assert(permalinks.length === n, `rows ${permalinks.length} vs cards ${n}`);
    assert(text.includes('https://pragapld.um.warszawa.pl/documents/'), 'no source file URL');
    await page.locator('.chips .chip', { hasText: 'Rodzaj' }).locator('button').click();
    await settle(page);
    assert(!(await hashOf(page)).includes('rodzaj='), 'kind chip did not restore the default');
  });

  await check('sort, relative period, tag and visible-area filters drive the URL and the results', async () => {
    await page.locator('#sort').selectOption('oldest');
    await settle(page);
    assert((await hashOf(page)).includes('sort=najstarsze'), 'sort not in URL');
    const dates = await page.locator('.cards .card time').evaluateAll((els) => els.map((e) => e.getAttribute('datetime')).filter(Boolean));
    assert(dates.length > 2 && dates.slice(0, 5).every((d, i, a) => i === 0 || a[i - 1] <= d), `not ascending: ${dates.slice(0, 5)}`);
    await page.locator('#sort').selectOption('newest');
    await page.getByRole('button', { name: 'Ostatnie 12 mies.' }).click();
    await settle(page);
    assert((await hashOf(page)).includes('okres=12m'), 'preset not in URL');
    const tagBox = page.locator('.tag-group .opt__input').first();
    await tagBox.check();
    await settle(page);
    assert(/typ=[a-z-]+/.test(await hashOf(page)), 'tag not in URL');
    const n1 = Number((await page.locator('#results-count strong').innerText()).replace(/\D/g, '') || 0);
    await page.locator('#filters').getByRole('checkbox', { name: /Tylko obszar widoczny/ }).check();
    await settle(page);
    assert(/mapa=[\d.]+,[\d.]+,[\d.]+,[\d.]+/.test(await hashOf(page)), 'visible-area bbox not in URL');
    const n2 = Number((await page.locator('#results-count strong').innerText()).replace(/\D/g, '') || 0);
    assert(n2 <= n1, 'visible-area filter widened the results');
    await page.locator('.chips__clear').click();
    await settle(page);
    assert(!/typ=|okres=|mapa=/.test(await hashOf(page)), `filters not cleared: ${await hashOf(page)}`);
  });

  await check('"W pobliżu mnie" uses geolocation, rounds the point to ~100 m and adds a radius filter', async () => {
    await page.getByRole('button', { name: /W pobliżu mnie/ }).first().click();
    await page.waitForFunction(() => window.location.hash.includes('blisko='));
    assert(/promien=500/.test(await hashOf(page)), 'radius missing');
    const point = decodeURIComponent((await hashOf(page)).match(/blisko=([^&]+)/)[1]);
    assert(/^52\.25\d?,21\.07\d?$/.test(point) && point === '52.255,21.076', `point not rounded to 3 decimals: ${point}`);
    await page.locator('.chips .chip', { hasText: 'W pobliżu' }).locator('button').click();
    await settle(page);
  });

  const districtPages = sourcesDoc.pages.filter((p) => !p.source || p.source === 'district');
  await check('sources view: district tab lists every monthly page, older years collapsed and rendered on demand', async () => {
    await page.getByRole('navigation', { name: 'Główna nawigacja' }).getByRole('link', { name: /Źródła/ }).click();
    await page.waitForSelector('.page--sources h1');
    assert(await page.evaluate(() => document.activeElement?.tagName === 'H1'), 'focus not on h1');
    const years = await page.locator('details.src-year').count();
    const closed = await page.locator('details.src-year:not([open])').count();
    assert(years >= 3 && closed === years - 2, `${closed} of ${years} years collapsed (expected all but the latest two)`);
    assert(await page.locator('details.src-year:not([open]) .src-page').count() === 0, 'collapsed years rendered eagerly');
    await page.$$eval('details.src-year', (ds) => ds.forEach((d) => { d.open = true; }));
    await settle(page, 200);
    const pages = await page.locator('.src-page').count();
    assert(pages === districtPages.length, `${pages} pages vs ${districtPages.length}`);
    await page.locator('.src-year__title').first().scrollIntoViewIfNeeded();
  });
  await shot(page, `${currentGroup}-sources`);
  await check('sources: "Pokaż N wpisów" → explore filtered by file', async () => {
    const link = page.locator('.src-file__actions a', { hasText: /Pokaż/ }).first();
    const label = await link.innerText();
    const n = Number((label.match(/\d+/) || [])[0]);
    await link.click();
    await page.waitForSelector('.cards .card');
    await settle(page);
    assert(/plik=[0-9a-f]{10}/.test(await hashOf(page)), 'no plik param');
    assert((await page.locator('.cards .card').count()) === n, 'file filter count mismatch');
  });

  await check('about view: glossary, downloads probed, unofficial disclaimer', async () => {
    await page.getByRole('navigation', { name: 'Główna nawigacja' }).getByRole('link', { name: 'O projekcie' }).click();
    await page.waitForSelector('.page--about h1');
    assert(await page.locator('.glossary__item').count() >= 3, 'glossary missing');
    await page.waitForFunction(() => !document.querySelector('.download.is-checking'));
    const ok = await page.locator('.download a', { hasText: 'Pobierz' }).count();
    assert(ok >= 2, 'records.json/sources.json downloads not offered');
    const about = await page.locator('.page--about').innerText();
    assert(/Serwis nieoficjalny/.test(about), 'disclaimer missing');
    // Planning records come from the Excel files only; GUNB's register files are counted with the permits.
    const excel = sourcesDoc.files.filter((f) => (f.source || 'district') !== 'rwdz').length;
    assert(about.replace(/\s/g, '').includes(`z${excel}plikówExcel`), `Excel file count (${excel}) not stated`);
  });
  await shot(page, `${currentGroup}-about`);

  await check('related records: short chains as steps, long chains collapsed with counts and reasons', async () => {
    // Related permits load on demand: count them only once the permits layer is in.
    const size = (r) => (r.related || []).filter((id) => byIdAll.has(id)).length + 1;
    const withRel = recordsDoc.records.filter((r) => size(r) > 1).sort((a, b) => size(b) - size(a));
    assert(withRel.length > 0, 'no related records in the data');
    const longest = withRel[0];
    await page.goto(`${url}#/wpis/${encodeURIComponent(longest.id)}`);
    await waitReady(page);
    if (HAS_PERMITS) await page.waitForSelector('body[data-permits="loaded"]', { timeout: 15000 });
    const sec = page.locator('section[aria-labelledby="d-related"]');
    await sec.waitFor();
    if (size(longest) > 6) {
      assert(/wpis/.test(await sec.locator('.chain-count').innerText()), 'no counted summary');
      // A window of 7 records around the current one; the rest behind "Wcześniejsze/Późniejsze" buttons.
      assert(await sec.locator('.chain__item:visible').count() === Math.min(7, size(longest)), 'collapsed window should show 7 records');
      if (size(longest) > 7) {
        assert(await sec.locator('.chain__gap').count() > 0, 'long chain not collapsed');
        await sec.locator('.chain__gap button').first().click();
        assert(await sec.locator('.chain__item:visible').count() === size(longest), 'expand did not show every record');
      }
    } else {
      assert(await sec.locator('.chain-summary__step').count() === size(longest), 'step summary incomplete');
    }
    assert(await sec.locator('.chain__item.is-current').count() === 1, 'current record not marked');
    const why = await sec.locator('.chain__why').allInnerTexts();
    assert(why.length > 0 && why.every((w) => /^(wspólna działka|wspólne działki|ten sam adres)/.test(w)), `reasons: ${why.slice(0, 3)}`);
  });

  if (HAS_PERMITS) await permitChecks(page, url, scheme);
  await reviewChecks(page, url);

  await check('unknown route falls back to the list', async () => {
    await page.goto(`${url}#/nie-ma-takiej-strony`);
    await waitReady(page);
    await page.waitForFunction(() => !window.location.hash.includes('nie-ma'));
    assert(await page.locator('.cards .card').count() > 0, 'no cards');
  });

  await check('no console errors', async () => {
    assert(errors.length === 0, errors.join('\n'));
  });
  if (external.length) console.log(`    (third-party map service messages ignored: ${external.length})`);
  await context.close();
}

/**
 * v2: building permits (opt-in, lazily loaded), BAiPP outcomes, sources tabs, same-spot cluster list.
 * Runs in the desktop suite when the data has a permits layer.
 */
async function permitChecks(page, url, scheme) {
  const counts = recordsDoc.counts_by_kind || {};
  const pbLabel = kindLabel('pb');
  const base = recordsDoc.records.length;
  const nPb = permitsDoc.records.filter((r) => r.kind === 'pb').length;

  await check('the idle prefetch of permits.json leaves the list alone (cards shown, keyboard focus)', async () => {
    const p = await page.context().newPage();
    let release;
    const gate = new Promise((ok) => { release = ok; });
    await p.route('**/data/permits.json', async (r) => { await gate; await r.continue(); });
    await p.goto(`${url}#/`);
    await waitReady(p);
    if (await p.locator('.more-btn').isVisible()) await p.locator('.more-btn').click();
    const shownBefore = await p.locator('.cards .card').count();
    await p.locator('.cards .card').nth(Math.min(shownBefore - 1, 55)).locator('.card__link').focus();
    const focused = await p.evaluate(() => document.activeElement?.closest('.card')?.dataset.id);
    await p.waitForSelector('body[data-permits="loading"]', { timeout: 10000 }); // desktop: fetched in idle time
    release();
    await p.waitForSelector('body[data-permits="loaded"]');
    await settle(p, 300);
    assert(await p.locator('.cards .card').count() === shownBefore, `cards ${shownBefore} → ${await p.locator('.cards .card').count()}`);
    assert(await p.evaluate(() => document.activeElement?.closest('.card')?.dataset.id) === focused, 'keyboard focus lost');
    await p.close();
  });

  await check('before permits load: pb/zg counts from counts_by_kind, promo, nothing fetched', async () => {
    // Hold permits.json until released, to observe the "not loaded yet" state deterministically.
    let release;
    const gate = new Promise((ok) => { release = ok; });
    const fetched = [];
    await page.route('**/data/permits.json', async (r) => { fetched.push(r.request().url()); await gate; await r.continue(); });
    await page.goto(`${url}#/`);
    await page.reload();
    await waitReady(page);
    const pbRow = page.locator('#filters .opt', { has: page.getByRole('checkbox', { name: new RegExp(pbLabel) }) });
    assert(!(await pbRow.getByRole('checkbox').isChecked()), 'pb ticked by default');
    assert((await pbRow.locator('.count').innerText()).replace(/\s/g, '') === String(counts.pb), 'pb count is not counts_by_kind.pb');
    assert(await pbRow.locator('.count.is-estimate').count() === 1, 'estimate not marked');
    const promo = page.locator('.promo');
    assert(await promo.isVisible(), 'promo hidden');
    // Before loading only the register total is known: it is labelled as such ("łącznie"), not as a match count.
    assert((await promo.innerText()).replace(/\s/g, ' ').includes(`(łącznie ${counts.pb})`), `promo count: ${await promo.innerText()}`);
    // "Organ" repeats "Źródło danych" for the planning kinds: shown only once permits are in.
    const organ = page.locator('#filters fieldset', { has: page.locator('legend', { hasText: 'Organ' }) });
    assert(await organ.isHidden(), 'redundant "Organ" facet shown for the planning kinds');
    // A register number is only in the permits: before they load, the empty state offers to search them too.
    await page.locator('#q').fill(permitsDoc.records[0].permit.register_id);
    await settle(page);
    assert(/Szukaj też w pozwoleniach/.test(await page.locator('.suggestion').first().innerText()), 'no "search permits too" suggestion');
    await page.locator('#q').fill('');
    await settle(page);
    // Switching permits on while the file is still on its way: a loading strip, never "no results".
    await promo.getByRole('button', { name: /Pokaż też pozwolenia na budowę/ }).click();
    await settle(page, 200);
    assert(/rodzaj=wz,cp,ws,pb/.test(await hashOf(page)), `hash ${await hashOf(page)}`);
    assert(await page.locator('.pending').isVisible(), 'no loading strip');
    assert(await page.locator('.empty').isHidden(), 'empty state while loading');
    release();
    await page.waitForSelector('body[data-permits="loaded"]');
    await page.unroute('**/data/permits.json');
    await settle(page);
    assert(fetched.length === 1, `permits.json fetched ${fetched.length}×`);
    assert(await page.locator('.pending').isHidden(), 'loading strip stays');
    const n = Number((await page.locator('#results-count strong').innerText()).replace(/\D/g, ''));
    assert(n === base + nPb, `${n} results, expected ${base} + ${nPb}`);
    assert(await page.locator('.cards .card[data-kind="pb"]').count() > 0, 'no permit cards');
    assert((await page.locator('.timeline__legend').innerText()).includes(recordsDoc.kinds.pb.short), 'timeline legend lacks permits');
    assert(await page.locator('.timeline__bar--pb').count() > 0, 'no permit bars');
    assert((await page.locator('.map-legend').textContent()).includes(pbLabel), 'map legend lacks permits');
    assert(await page.locator('.leaflet-marker-icon .mk--pb, .cl-wrap').count() > 0, 'no permit markers');
    // The map was created for the default kinds: cluster rings and their spoken mix must still show permits.
    const rings = await page.evaluate(() => [...document.querySelectorAll('.cl-wrap')].map((w) => w.innerHTML).join(' '));
    assert(!rings.includes('var(--text-3)'), 'cluster ring with a grey "unknown" segment');
    assert(rings.includes('--c-pb') || await page.locator('.mk--pb').count() > 0, 'permits missing from cluster rings');
    const labels = await page.evaluate(() => [...document.querySelectorAll('.cl-wrap .sr-only')].map((x) => x.textContent));
    const form = (n) => (n === 1 ? 'wpis' : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? 'wpisy' : 'wpisów');
    const badPlural = labels.filter((t) => { const m = t.match(/: (\d+) (wpis\S*)/); return m && m[2] !== form(Number(m[1])); });
    assert(!badPlural.length, `cluster label: ${badPlural[0]}`);
    if (rings.includes('--c-pb')) assert(labels.some((t) => t.includes(recordsDoc.kinds.pb.short)), 'spoken cluster mix lacks permits');
    assert(await page.locator('#filters fieldset', { has: page.locator('legend', { hasText: 'Organ' }) }).isVisible(), '"Organ" hidden with permits');
    // GUNB register number search
    const pbRec = permitsDoc.records.find((r) => r.kind === 'pb');
    await page.locator('#q').fill(pbRec.permit.register_id);
    await settle(page);
    assert(await page.locator(`.cards .card[data-id="${pbRec.id}"]`).count() === 1, 'register number not found');
    await page.locator('#q').fill('');
    await settle(page);
  });
  await shot(page, `${currentGroup}-permits`);

  await check('permit facets: "Zakres robót" and "Kategoria obiektu" appear with permits and filter them', async () => {
    const scope = page.locator('#filters fieldset', { has: page.locator('legend', { hasText: 'Zakres robót' }) });
    assert(await scope.isVisible(), 'scope facet hidden');
    const first = scope.locator('.opt:not([hidden]) .opt__input').first();
    await first.check();
    await settle(page);
    assert(/zakres=[a-z]+/.test(await hashOf(page)), `hash ${await hashOf(page)}`);
    const kinds = await page.locator('.cards .card').evaluateAll((els) => els.map((e) => e.dataset.kind));
    assert(kinds.length && kinds.every((k) => k === 'pb' || k === 'zg'), `non-permits with a scope filter: ${[...new Set(kinds)]}`);
    assert(await page.locator('#filters fieldset', { has: page.locator('legend', { hasText: 'Kategoria obiektu' }) }).isVisible(), 'category facet hidden');
    await first.uncheck();
    await settle(page);
  });

  // A WZ decision with a related permit and a short chain (≤ 6 records → shown step by step).
  const chainSize = (r) => (r.related || []).filter((id) => byIdAll.has(id)).length + 1;
  const story = recordsDoc.records.filter((r) => r.kind === 'wz' && (r.related || []).some((id) => byIdAll.get(id)?.kind === 'pb'))
    .sort((a, b) => (chainSize(a) <= 6 ? 0 : 1) - (chainSize(b) <= 6 ? 0 : 1) || chainSize(a) - chainSize(b))[0];
  await check('a WZ detail loads related permits on demand and tells the WZ → permit story', async () => {
    assert(story, 'fixture has no WZ with a related permit');
    const p2 = await page.context().newPage();
    await p2.route('**/data/permits.json', async (r) => { await new Promise((ok) => setTimeout(ok, 600)); await r.continue(); });
    await p2.goto(`${url}#/wpis/${encodeURIComponent(story.id)}`);
    await waitReady(p2);
    const sec = p2.locator('section[aria-labelledby="d-related"]');
    await sec.waitFor();
    assert(/Wczytywanie powiązanych pozwoleń/.test(await sec.innerText()), 'no loading note for related permits');
    await p2.waitForSelector('body[data-permits="loaded"]');
    await p2.waitForFunction(() => !document.querySelector('#d-related')?.closest('section').textContent.includes('Wczytywanie'));
    const text = await sec.innerText();
    assert(/pozwolenie na (budowę|rozbiórkę) \d{2}\.\d{4}/.test(text), `no permit step: ${text.slice(0, 200)}`);
    assert(await sec.locator('.chain__item--pb').count() > 0, 'no permit in the chain');
    assert(/(budowę|budowanie|rejestrze pozwoleń)/.test(text), 'lead does not mention permits');
    await sec.locator('.chain__item--pb a.chain__body').first().click();
    await p2.waitForFunction(() => /#\/wpis\/pb-/.test(window.location.hash));
    assert((await p2.locator('#detail .kbadge').first().innerText()).includes(pbLabel), 'permit detail not opened');
    await p2.goto(`${url}#/wpis/${encodeURIComponent(story.id)}`);
    await p2.waitForSelector('#detail .chain__item--pb');
    await p2.locator('section[aria-labelledby="d-related"]').scrollIntoViewIfNeeded();
    await shot(p2, `${currentGroup}-related`);
    await p2.close();
  });

  const permit = permitsDoc.records.find((r) => r.kind === 'pb' && r.filed_date && r.permit?.category && (r.sources?.[0]?.rows || []).length);
  await check('permit detail: register id, filed → decided with duration, scope, category, RWDZ provenance', async () => {
    await page.goto(`${url}#/wpis/${encodeURIComponent(permit.id)}`);
    await page.waitForSelector('#detail .detail__title');
    const d = page.locator('#detail');
    const t = await d.innerText();
    assert(t.includes(permit.permit.register_id), 'register id missing');
    assert(/decyzja (po \d+ (dniu|dniach)|tego samego dnia)/.test(t), 'no decision duration');
    assert(t.includes(`${permit.permit.category} – `), 'category missing');
    assert(/Zakres robót/.test(t) && /Kategoria obiektu/.test(t), 'permit facts missing');
    assert(/GUNB nie udostępnia stałych linków/.test(t), 'no honest note about per-case links');
    assert(/CC0/.test(t), 'licence missing');
    const extract = d.locator('a', { hasText: 'Wyciąg dla Pragi-Południe (CSV)' });
    const href = await extract.getAttribute('href');
    assert(/^sources\/rwdz\/[a-z0-9-]+\.csv$/.test(href), `extract href ${href}`);
    const res = await page.request.get(new URL(href, server.url).href);
    assert(res.status() === 200, `extract status ${res.status()}`);
    const zip = await d.locator('a', { hasText: 'Plik ZIP (GUNB)' }).getAttribute('href');
    assert(/^https:\/\/wyszukiwarka\.gunb\.gov\.pl\/pliki_pobranie\/.+\.zip$/.test(zip), `zip ${zip}`);
    assert(/dane\.gov\.pl/.test(await d.locator('a', { hasText: 'Zbiór na dane.gov.pl' }).getAttribute('href')), 'dataset link');
    const lines = (await d.locator('.prov__facts').innerText()).replace(/\s/g, '');
    assert(lines.includes(String(permit.sources[0].rows[0])), 'original line number missing');
    await d.locator('.prov__raw summary').first().click();
    assert(await d.locator('.table--raw tbody tr').count() > 5, 'raw table empty');
    assert(!/projektant/i.test(await d.locator('.table--raw').innerText()), 'designer columns shown');
    // the selected permit's parcels are highlighted on the map
    await page.waitForSelector('.leaflet-overlay-pane path.leaflet-interactive, .leaflet-overlay-pane path', { timeout: 5000 });
  });
  await d_scrollTop(page);
  await shot(page, `${currentGroup}-permit`);

  await check('a permit permalink opened cold shows a loading panel, then the record (never "not found")', async () => {
    const p3 = await page.context().newPage();
    await p3.route('**/data/permits.json', async (r) => { await new Promise((ok) => setTimeout(ok, 800)); await r.continue(); });
    await p3.goto(`${url}#/wpis/${encodeURIComponent(permit.id)}`);
    await waitReady(p3);
    await p3.waitForSelector('#detail .detail[aria-busy="true"]');
    assert(!/Nie znaleziono/.test(await p3.locator('#detail').innerText()), '"not found" flashed while loading');
    await p3.waitForSelector('#detail .detail__title:not(.sr-only)');
    assert((await p3.locator('#detail').innerText()).includes(permit.permit.register_id), 'record not rendered after loading');
    await p3.close();
  });

  await check('a permit opened while permits are hidden: map goes to it, legend has ▲, a note offers to show permits', async () => {
    const pb = permitsDoc.records.find((r) => r.kind === 'pb' && r.geo?.method === 'parcel');
    const p4 = await page.context().newPage();
    await p4.goto(`${url}#/wpis/${encodeURIComponent(pb.id)}`);
    await waitReady(p4);
    await p4.waitForSelector('body[data-permits="loaded"]');
    await p4.waitForSelector('#detail .detail__title:not(.sr-only)');
    await settle(p4, 1500);
    const z = await tileZoom(p4);
    assert(z == null || z >= 16, `map stayed at zoom ${z}`);
    assert((await p4.locator('.map-legend').textContent()).includes(pbLabel), 'legend lacks the permit kind');
    const note = p4.locator('#detail .detail__hidden');
    assert(await note.isVisible(), 'no "permits are hidden" note');
    assert(await p4.locator('#detail .detail__pos').count() === 0, 'pager describes the planning results');
    assert(await p4.locator('.nogeo').isHidden(), 'map note describes the planning list');
    assert(!/\d/.test(await p4.locator('.map-btn--check .count').innerText()), 'visible-area count describes the planning list');
    await note.getByRole('button', { name: /Pokaż pozwolenia na liście/ }).click();
    await p4.waitForFunction(() => /rodzaj=wz,cp,ws,pb/.test(window.location.hash));
    await p4.waitForSelector('#detail .detail__pos');
    assert(/\d+ z \d+/.test(await p4.locator('#detail .detail__pos').innerText()), 'not among the results');
    await p4.close();
  });

  await check('"Ostatnie 3 mies." counts back per kind group: switching permits on keeps the same planning records', async () => {
    const planningCards = (p) => p.locator('.cards .card[data-kind="wz"], .cards .card[data-kind="cp"], .cards .card[data-kind="ws"]').count();
    await page.goto(`${url}#/?okres=3m`);
    await waitReady(page);
    await settle(page);
    const before = await planningCards(page);
    await page.goto(`${url}#/?okres=3m&rodzaj=wz,cp,ws,pb`);
    await page.waitForSelector('body[data-permits="loaded"]');
    await settle(page, 600);
    assert(await planningCards(page) === before, `planning records ${before} → ${await planningCards(page)}`);
  });

  await check('only permits selected and the register still loading: "Wczytywanie…", never "Brak wyników"', async () => {
    const p5 = await page.context().newPage();
    let release;
    const gate = new Promise((ok) => { release = ok; });
    await p5.route('**/data/permits.json', async (r) => { await gate; await r.continue(); });
    await p5.goto(`${url}#/?rodzaj=pb`);
    await waitReady(p5);
    await p5.waitForSelector('body[data-permits="loading"]');
    await settle(p5, 900);
    assert(!/Brak wyników/.test(await p5.locator('#results-count').innerText()), 'count says "Brak wyników"');
    assert(!/Nie znaleziono/.test(await p5.locator('#results-live').textContent()), 'live region says "not found"');
    release();
    await p5.waitForSelector('body[data-permits="loaded"]');
    await settle(p5, 900);
    assert(/\d/.test(await p5.locator('#results-count').innerText()), 'count not updated after loading');
    await p5.close();
  });

  const refusal = recordsDoc.records.find((r) => r.outcome === 'refusal');
  await check('BAiPP refusal: badge on the card, outcome facet, warning callout and city-wide file context', async () => {
    await page.goto(`${url}#/`);
    await waitReady(page);
    const card = page.locator(`.cards .card[data-id="${refusal.id}"]`);
    await card.waitFor();
    assert((await card.locator('.obadge--bad').innerText()).includes(recordsDoc.outcomes.refusal.label), 'no refusal badge');
    assert(await card.locator('.dbadge').count() === 1, 'no dataset marker');
    const outcomeGroup = page.locator('#filters fieldset', { has: page.locator('legend', { hasText: 'Rozstrzygnięcie' }) });
    await outcomeGroup.getByRole('checkbox', { name: new RegExp(recordsDoc.outcomes.refusal.label) }).check();
    await settle(page);
    assert(/rozstrzygniecie=refusal/.test(await hashOf(page)), 'outcome not in URL');
    const n = await page.locator('.cards .card').count();
    assert(n === recordsDoc.records.filter((r) => r.outcome === 'refusal').length, `${n} refusals`);
    assert(await page.locator('.cards .card .obadge--bad').count() === n, 'card without badge');
    await card.locator('.card__link').click();
    await page.waitForSelector('#detail .detail__refusal');
    const t = await page.locator('#detail').innerText();
    assert(/Plik ogólnomiejski: \d+ wiersz/.test(t), 'no rows_total context');
    assert(/Biuro Architektury/.test(t), 'issuer/dataset missing');
  });
  await shot(page, `${currentGroup}-refusal`);

  await check('permits arriving while the Sources page is open leave it as it is (opened years stay open)', async () => {
    const p = await page.context().newPage();
    let release;
    const gate = new Promise((ok) => { release = ok; });
    await p.route('**/data/permits.json', async (r) => { await gate; await r.continue(); });
    await p.goto(`${url}#/zrodla`);
    await p.waitForSelector('details.src-year');
    const closed = p.locator('details.src-year:not([open])').first();
    if (await closed.count()) await closed.locator('summary').click();
    const open = await p.locator('details.src-year[open]').count();
    await p.waitForSelector('body[data-permits="loading"]', { timeout: 10000 });
    release();
    await p.waitForSelector('body[data-permits="loaded"]');
    await settle(p, 300);
    assert(await p.locator('details.src-year[open]').count() === open, 'the panel was re-rendered: opened years collapsed');
    await p.close();
  });

  await check('sources: tabs per dataset; BAiPP snapshots; RWDZ files with licence and extract', async () => {
    await page.goto(`${url}#/zrodla`);
    await page.waitForSelector('.page--sources [role="tab"]');
    assert(await page.locator('[role="tab"]').count() === 3, 'expected 3 tabs');
    assert(await page.locator('[role="tab"][aria-selected="true"]').innerText().then((x) => x.includes(recordsDoc.datasets.district.short)), 'district tab not selected');
    await page.locator('[role="tab"]', { hasText: recordsDoc.datasets.baipp.short }).click();
    await page.waitForFunction(() => window.location.hash === '#/zrodla/baipp');
    const baippPages = sourcesDoc.pages.filter((p) => p.source === 'baipp').length;
    assert(await page.locator('.src-panel--baipp .src-page').count() === baippPages, 'BAiPP pages');
    assert(/plik ogólnomiejski: \d+ wiersz/.test(await page.locator('.src-panel--baipp').innerText()), 'no city-wide counts');
    // keyboard: → moves to the next tab
    await page.locator('[role="tab"][aria-selected="true"]').focus();
    await page.keyboard.press('ArrowRight');
    await page.waitForFunction(() => window.location.hash === '#/zrodla/rwdz');
    const reg = page.locator('.src-panel--rwdz');
    await reg.waitFor();
    const files = sourcesDoc.files.filter((f) => f.source === 'rwdz');
    assert(await reg.locator('.src-page--register').count() === files.length, 'register files');
    assert(/CC0/.test(await reg.innerText()), 'licence missing');
    assert(await reg.locator('a', { hasText: 'Wyciąg CSV' }).count() === files.length, 'extract links');
    const titles = await reg.locator('.src-page__title').allInnerTexts();
    assert(titles.every((t) => !/\.zip\)\s*$/.test(t)), `ZIP name repeated in the title: ${titles[0]}`);
  });
  await shot(page, `${currentGroup}-sources-rwdz`);
  await check('sources: "Pokaż N wpisów" of an RWDZ file switches its kind on and filters by file', async () => {
    const link = page.locator('.src-panel--rwdz .src-file__actions a', { hasText: /Pokaż/ }).first();
    const n = Number(((await link.innerText()).match(/\d+/) || [])[0]);
    await link.click();
    await page.waitForFunction(() => /plik=rwdz-/.test(window.location.hash));
    await page.waitForSelector('body[data-permits="loaded"]');
    await settle(page);
    assert(/rodzaj=(pb|zg)/.test(await hashOf(page)), `kind not switched on: ${await hashOf(page)}`);
    const shown = Number((await page.locator('#results-count strong').innerText()).replace(/\D/g, ''));
    assert(shown === n, `${shown} vs ${n}`);
  });

  // Records sharing one point (several decisions on one parcel centroid): find such a place in the data.
  const spots = new Map();
  for (const r of recordsDoc.records) {
    if (typeof r.geo?.lat !== 'number') continue;
    const k = `${r.geo.lat},${r.geo.lon}`;
    spots.set(k, [...(spots.get(k) || []), r.id]);
  }
  const spot = [...spots.values()].filter((ids) => ids.length >= 2).sort((a, b) => b.length - a.length)[0];
  await check('a cluster whose markers share one point opens a list instead of zooming in', async () => {
    assert(spot, 'no shared point in the data');
    await page.goto(`${url}#/wpis/${encodeURIComponent(spot[0])}`);
    await page.waitForSelector('#detail .detail__title');
    await settle(page, 900);
    await page.keyboard.press('Escape');
    await settle(page, 400);
    // A same-place cluster well inside the visible map (Leaflet keeps off-screen icons in the DOM too).
    const visibleSpot = () => page.evaluate(() => {
      const m = document.querySelector('#map').getBoundingClientRect();
      for (const el of document.querySelectorAll('.cl-wrap--spot')) {
        const r = el.getBoundingClientRect();
        if (r.left > m.left + 60 && r.right < m.right - 60 && r.top > m.top + 120 && r.bottom < m.bottom - 60) return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
      }
      return null;
    });
    // On a large parcel other markers may still share the cluster: zoom in until the same-place group stands alone.
    for (let i = 0; i < 4 && !(await visibleSpot()); i += 1) {
      await page.locator('.leaflet-control-zoom-in').click();
      await settle(page, 600);
    }
    const at = await visibleSpot();
    assert(at, 'no same-place cluster on screen');
    // zoom level = scale of Leaflet's proxy element (popups may pan the map, but must not zoom it)
    const zoomOf = () => page.evaluate(() => (document.querySelector('.leaflet-proxy')?.style.transform.match(/scale\(([^)]+)\)/) || [])[1] || '1');
    const zoomBefore = await zoomOf();
    await page.mouse.click(at.x, at.y);
    const list = page.locator('.spot-list');
    await list.waitFor();
    assert(await list.locator('.spot-list__item').count() >= 2, 'list incomplete');
    assert(await page.evaluate(() => document.activeElement?.classList.contains('spot-list__item')), 'focus not in the list');
    await settle(page, 500);
    const zoomAfter = await zoomOf();
    assert(zoomBefore === zoomAfter, 'map zoomed instead of listing');
    const covered = await page.evaluate(() => {
      const a = document.querySelector('.spot-popup')?.getBoundingClientRect();
      const t = document.querySelector('.map-tools')?.getBoundingClientRect();
      return Boolean(a && t && a.top < t.bottom && a.left < t.right && a.right > t.left);
    });
    assert(!covered, 'the list opened under the map tools');
    await shot(page, `${currentGroup}-spot`);
    // Esc closes the list (not the page state behind it) and gives the focus back to the group marker;
    // Enter on the marker opens the list again.
    await page.keyboard.press('Escape');
    await settle(page, 300);
    assert(await list.count() === 0, 'Esc did not close the list');
    assert(await page.evaluate(() => document.activeElement?.classList.contains('cl-wrap--spot')), 'focus not back on the group marker');
    await page.keyboard.press('Enter');
    await list.waitFor();
    await list.locator('.spot-list__item').nth(1).click();
    await page.waitForFunction(() => /#\/wpis\//.test(window.location.hash));
    await page.waitForSelector('#detail .detail__title');
  });
}

/**
 * Zoom level of the map: Leaflet's zoom-animation proxy is scaled by 2^(zoom − 1); without it, the base-map tile URLs
 * (tiles may fail to load offline – their src still says it).
 */
const tileZoom = (page) => page.evaluate(() => {
  const m = (document.querySelector('.leaflet-proxy')?.style.transform || '').match(/scale\(([^)]+)\)/);
  if (m) return Math.round((Math.log2(Number(m[1])) + 1) * 2) / 2;
  const src = [...document.querySelectorAll('.leaflet-tile')].map((t) => t.src).find((x) => /\/\d+\/\d+\/\d+\.png/.test(x));
  return src ? Number(src.match(/\/(\d+)\/\d+\/\d+\.png/)[1]) : null;
});
/** The focused element is completely covered by something else (sticky bars) – WCAG 2.4.11. */
const focusHidden = (page) => page.evaluate(() => {
  const a = document.activeElement;
  if (!a || a === document.body) return null;
  const r = a.getBoundingClientRect();
  if (!r.width || !r.height) return null;
  const pts = [[r.left + r.width / 2, r.top + r.height / 2], [r.left + 2, r.top + 2], [r.right - 2, r.top + 2], [r.left + 2, r.bottom - 2], [r.right - 2, r.bottom - 2]];
  const covered = pts.filter(([x, y]) => {
    if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) return true;
    const e = document.elementFromPoint(x, y);
    return !e || !(a === e || a.contains(e) || e.contains(a));
  }).length;
  return covered === pts.length ? `${a.tagName} "${(a.textContent || '').trim().slice(0, 30)}" under ${document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2)?.className}` : null;
});
async function tabWalk(page, n, shift = false) {
  const hidden = [];
  for (let i = 0; i < n; i += 1) {
    await page.keyboard.press(shift ? 'Shift+Tab' : 'Tab');
    const h = await focusHidden(page);
    if (h) hidden.push(h);
  }
  return hidden;
}
const recordsInBbox = (b) => recordsDoc.records.filter((r) => typeof r.geo?.lat === 'number'
  && r.geo.lon >= b[0] && r.geo.lon <= b[2] && r.geo.lat >= b[1] && r.geo.lat <= b[3]).length;

/**
 * Checks added with the review fixes (UX, accessibility, robustness). Desktop, any data.
 */
async function reviewChecks(page, url) {
  const geoRec = recordsDoc.records.find((r) => r.geo?.method === 'parcel' && (r.geo.parcels_found || []).length);
  const noGeo = recordsDoc.records.find((r) => typeof r.geo?.lat !== 'number');

  await check('a record without a location fits the map to the district and says so (not the previous spot)', async () => {
    assert(noGeo, 'data has no record without a location');
    await page.goto(`${url}#/wpis/${encodeURIComponent(geoRec.id)}`);
    await waitReady(page);
    await page.waitForSelector('#detail .detail__title');
    await page.waitForFunction(() => document.querySelector('.leaflet-tile'), null, { timeout: 5000 }).catch(() => {});
    await settle(page, 1200);
    const z1 = await tileZoom(page);
    await page.evaluate((id) => { window.location.hash = `#/wpis/${encodeURIComponent(id)}`; }, noGeo.id);
    await page.waitForFunction((id) => document.querySelector('#detail-title') && window.location.hash.includes(id), noGeo.id);
    await settle(page, 1500);
    const note = page.locator('.nogeo');
    assert(await note.isVisible(), 'no note on the map');
    assert(/nie ma lokalizacji/.test(await note.innerText()), `note: ${await note.innerText()}`);
    const z2 = await tileZoom(page);
    assert(z1 == null || z2 == null || (z2 <= 14 && z2 < z1), `map stayed on the previous record (zoom ${z1} → ${z2})`);
    const prec = await page.locator('#detail .precision').innerText();
    assert(!/na mapie.*na mapie/.test(prec), `precision line repeats itself: ${prec}`);
  });

  await check('Enter on a focused map marker opens its record (role=button); Esc closes its tooltip first', async () => {
    await page.goto(`${url}#/?q=${encodeURIComponent(geoRec.address?.street || '')}`);
    await waitReady(page);
    await settle(page, 1200);
    const mk = page.locator('.leaflet-marker-icon.mk-wrap').first();
    assert(await mk.count(), 'no single marker on the map');
    await mk.focus();
    assert(await page.locator('.leaflet-tooltip.mk-tip').count() === 1, 'no tooltip on focus');
    await page.keyboard.press('Escape');
    await settle(page, 350);
    assert(await page.locator('.leaflet-tooltip.mk-tip').count() === 0, 'Esc did not close the tooltip');
    await mk.focus();
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => /#\/wpis\//.test(window.location.hash), null, { timeout: 3000 });
    await page.waitForFunction(() => document.activeElement?.id === 'detail-title', null, { timeout: 2000 });
    await page.keyboard.press('Escape');
    await settle(page);
  });

  await check('map layers: Enter opens the list with focus on the first layer, Esc closes it back to the toggle', async () => {
    const toggle = page.locator('.leaflet-control-layers-toggle');
    await toggle.focus();
    assert(await toggle.getAttribute('aria-expanded') === 'false', 'no aria-expanded');
    await page.keyboard.press('Enter');
    await settle(page, 200);
    assert(await toggle.getAttribute('aria-expanded') === 'true', 'not expanded');
    assert(await page.evaluate(() => document.activeElement?.classList.contains('leaflet-control-layers-selector')), 'focus not on a layer');
    await page.keyboard.press('Escape');
    await settle(page, 200);
    assert(await toggle.getAttribute('aria-expanded') === 'false', 'Esc did not collapse');
    assert(await page.evaluate(() => document.activeElement?.classList.contains('leaflet-control-layers-toggle')), 'focus not back on the toggle');
  });

  await check('Tab through the map: every focused marker or group is panned into view, clear of the map controls', async () => {
    await page.goto(`${url}#/`);
    await waitReady(page);
    await settle(page, 800);
    await page.locator('.leaflet-control-zoom-in').click();
    await settle(page, 500);
    await page.locator('#map').focus();
    const bad = [];
    for (let i = 0; i < 15; i += 1) {
      await page.keyboard.press('Tab');
      await settle(page, 400);
      const r = await page.evaluate(() => {
        const a = document.activeElement;
        if (!a?.classList.contains('leaflet-marker-icon')) return 'left';
        const b = a.getBoundingClientRect();
        const e = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
        return e && (a === e || a.contains(e)) ? 'ok' : `${a.getAttribute('aria-label') || a.textContent} under ${e?.closest('.leaflet-control, .nogeo')?.className || 'off screen'}`;
      });
      if (r === 'left') break;
      if (r !== 'ok') bad.push(r);
    }
    assert(!bad.length, bad.slice(0, 3).join('\n'));
  });

  await check('"Wskaż na mapie" by keyboard: a banner explains, Enter on the map picks its centre', async () => {
    await page.goto(`${url}#/`);
    await waitReady(page);
    await settle(page, 800);
    await page.locator('#filters button', { hasText: 'Wskaż na mapie' }).focus();
    await page.keyboard.press('Enter');
    await page.waitForSelector('.pick-banner');
    assert(/Esc/.test(await page.locator('.pick-banner').innerText()), 'desktop banner does not mention Esc');
    await page.waitForFunction(() => document.activeElement?.id === 'map', null, { timeout: 2000 });
    await page.keyboard.press('ArrowLeft');
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => window.location.hash.includes('blisko='), null, { timeout: 3000 });
    assert(await page.locator('.pick-banner').count() === 0, 'banner stays after the pick');
    assert(await page.locator('#map.is-picking').count() === 0, 'still picking');
  });

  await check('choosing a "W pobliżu" radius keeps the focus on it; "Usuń punkt" hands it to "Moja lokalizacja"', async () => {
    const r1k = page.locator('#filters .seg--radius .seg__btn', { hasText: '1 km' });
    await r1k.focus();
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => window.location.hash.includes('promien=1000'));
    assert(await page.evaluate(() => document.activeElement?.textContent.startsWith('1 km')), 'focus lost');
    assert(await r1k.getAttribute('aria-pressed') === 'true', 'not pressed');
    await page.locator('#filters button', { hasText: 'Usuń punkt' }).focus();
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => !window.location.hash.includes('blisko='));
    assert(await page.evaluate(() => document.activeElement?.textContent.trim() === 'Moja lokalizacja'), 'focus not on "Moja lokalizacja"');
  });

  await check('the outcome filter says how many decisions state an outcome at all', async () => {
    await page.goto(`${url}#/?rozstrzygniecie=refusal`);
    await waitReady(page);
    const note = page.locator('.outcome-note');
    await note.waitFor();
    assert(/BAiPP/.test(await note.innerText()) && /znamy je dla \d+ z \d+/.test(await note.innerText()), `note: ${await note.innerText()}`);
    const group = page.locator('#filters fieldset', { has: page.locator('legend', { hasText: 'Rozstrzygnięcie' }) });
    assert(/Biura Architektury/.test(await group.locator('.fgroup__note').innerText()), 'no permanent note in the facet');
  });

  await check('a stale link with unknown values degrades to the remaining filters', async () => {
    await page.goto(`${url}#/?typ=nieistniejacy-typ&okres=constructor&sort=constructor`);
    await page.reload();
    await waitReady(page);
    await page.waitForFunction(() => window.location.hash === '#/' || window.location.hash === '');
    const n = Number((await page.locator('#results-count strong').innerText()).replace(/\D/g, ''));
    assert(n === recordsDoc.records.length, `${n} results`);
  });

  await check('a shared "mapa=" link keeps its area (no rewrite to the receiver\'s screen) until the map is moved', async () => {
    const at = geoRec.geo;
    const b = [at.lon - 0.006, at.lat - 0.004, at.lon + 0.006, at.lat + 0.004].map((x) => Number(x.toFixed(5)));
    const hash = `#/?mapa=${b.map((x) => x.toFixed(5)).join(',')}`;
    await page.goto(`${url}${hash}`);
    await waitReady(page);
    await settle(page, 1500);
    assert(await hashOf(page) === hash, `rewritten to ${await hashOf(page)}`);
    const n = Number((await page.locator('#results-count strong').innerText()).replace(/\D/g, ''));
    assert(n === recordsInBbox(b), `${n} results, ${recordsInBbox(b)} records in the shared area`);
    const m = await page.locator('#map').boundingBox();
    await page.mouse.move(m.x + m.width / 2, m.y + m.height / 2);
    await page.mouse.down();
    await page.mouse.move(m.x + m.width / 2 + 120, m.y + m.height / 2 + 40, { steps: 6 });
    await page.mouse.up();
    await settle(page, 800);
    assert(await hashOf(page) !== hash, 'dragging did not update the area');
  });

  await check('steps and facts: outcomes named in the summary, "Wniosek o: decyzję…", no duplicate BAiPP month', async () => {
    const chainOf = (r) => [r, ...(r.related || []).map((id) => byIdAll.get(id)).filter(Boolean)];
    const story = recordsDoc.records.find((r) => chainOf(r).length <= 6 && chainOf(r).length > 1
      && chainOf(r).some((x) => ['wz', 'cp'].includes(x.kind) && ['refusal', 'discontinued'].includes(x.outcome)));
    if (story) {
      await page.goto(`${url}#/wpis/${encodeURIComponent(story.id)}`);
      await waitReady(page);
      if (HAS_PERMITS) await page.waitForSelector('body[data-permits="loaded"]');
      const sum = await page.locator('.chain-summary').getAttribute('aria-label');
      assert(/(odmowa|umorzenie) (WZ|CP) \d{2}\.\d{4}/.test(sum), `summary: ${sum}`);
    }
    const ws = recordsDoc.records.find((r) => r.kind === 'ws' && r.dataset === 'baipp' && r.date && r.period && r.procedure);
    await page.goto(`${url}#/wpis/${encodeURIComponent(ws.id)}`);
    await page.waitForSelector('#detail .facts');
    const facts = await page.locator('#detail .facts').innerText();
    assert(/Wniosek o/.test(facts) && /decyzję o /.test(facts), `facts: ${facts.slice(0, 160)}`);
    assert(!/Miesiąc decyzji/.test(facts), 'BAiPP initiated proceeding shows "Miesiąc decyzji"');
    const district = recordsDoc.records.find((r) => r.dataset === 'district' && r.period);
    await page.goto(`${url}#/wpis/${encodeURIComponent(district.id)}`);
    await page.waitForSelector('#detail .facts');
    assert(/Opublikowano w zestawieniu/.test(await page.locator('#detail .facts').innerText()), 'district publication month gone');
  });

  await check('the first and last record get a disabled (named) arrow button, not an <a> without href', async () => {
    await page.goto(`${url}#/`);
    await waitReady(page);
    await page.locator('.cards .card .card__link').first().click();
    await page.waitForSelector('#detail .detail__nav');
    const prev = page.locator('#detail .detail__nav button[disabled]');
    assert(await prev.count() === 1, 'no disabled button');
    assert(/Poprzedni wpis/.test(await prev.getAttribute('aria-label')), 'unnamed');
    assert(await page.locator('#detail .detail__nav a:not([href])').count() === 0, '<a> without href');
    await page.keyboard.press('Escape');
  });

  await check('headings: one h1 on Przeglądaj, results under "Lista wyników"; Sources years are h2', async () => {
    assert(await page.locator('#view-explore h1').count() === 1, 'no h1 on the explore view');
    assert(await page.locator('#results-heading').count() === 1, 'no results heading');
    assert(await page.locator('body > .toasts[role="status"]').count() === 1, 'toast live region not created at boot');
    await page.goto(`${url}#/zrodla`);
    await page.waitForSelector('details.src-year');
    assert(await page.locator('details.src-year > summary h2').count() > 0, 'year is not a heading');
  });

  await check('Sources: keyboard focus never ends up under the sticky top bar, tabs and toolbar (1440 px)', async () => {
    await page.$$eval('details.src-year', (ds) => ds.forEach((d) => { d.open = true; }));
    await settle(page, 200);
    const links = page.locator('.src-file__actions a');
    await links.nth(Math.min(40, (await links.count()) - 1)).focus();
    const hidden = await tabWalk(page, 40, true);
    assert(!hidden.length, hidden.slice(0, 3).join('\n'));
  });

  await check('RWDZ: the snapshot date is labelled "Stan rejestru", the build time "Sprawdzono"', async () => {
    if (!sourcesDoc.files.some((f) => f.source === 'rwdz')) return;
    await page.goto(`${url}#/zrodla/rwdz`);
    const reg = page.locator('.src-panel--rwdz');
    await reg.waitFor();
    const t = await reg.innerText();
    assert(/Stan rejestru/.test(t) && /Sprawdzono/.test(t) && !/Last-Modified/.test(t), 'labels');
  });

  await check('About: feed address can be copied, keyboard shortcut switch, UUG credit, third-party map servers named', async () => {
    await page.goto(`${url}#/o-projekcie`);
    await page.waitForSelector('.page--about h1');
    await page.waitForFunction(() => !document.querySelector('.download.is-checking'));
    const feed = page.locator('.download[data-path="feed.xml"]');
    if (!(await feed.evaluate((li) => li.classList.contains('is-missing')))) {
      assert(await feed.getByRole('button', { name: 'Kopiuj adres kanału' }).count() === 1, 'no copy button');
      assert(await feed.locator('a[target="_blank"]', { hasText: 'Podgląd' }).count() === 1, 'no preview link');
    }
    const t = await page.locator('.page--about').innerText();
    assert(/UUG/.test(t), 'UUG not credited');
    assert(/OpenStreetMap Foundation/.test(await page.locator('#about-privacy').innerText()), 'privacy does not name the tile servers');
    // "/" can be switched off
    const sw = page.getByRole('checkbox', { name: /Skrót klawiszowy/ });
    await sw.uncheck();
    await page.locator('a[data-nav="explore"]').click();
    await waitReady(page);
    await page.locator('#results-count').click();
    await page.keyboard.press('/');
    await settle(page, 150);
    assert(await page.evaluate(() => document.activeElement?.id !== 'q'), '"/" still focuses search when switched off');
    await page.goto(`${url}#/o-projekcie`);
    await page.getByRole('checkbox', { name: /Skrót klawiszowy/ }).check();
  });

  await check('forced colours: a pressed year differs from the others; tiles carry the muting filter (not the layer)', async () => {
    await page.goto(`${url}#/?od=2024-01&do=2024-12`);
    await waitReady(page);
    await page.emulateMedia({ forcedColors: 'active' });
    const st = await page.evaluate(() => {
      const bg = (b) => getComputedStyle(b).backgroundColor;
      const ys = [...document.querySelectorAll('.year-btn')];
      return { on: bg(ys.find((b) => b.getAttribute('aria-pressed') === 'true')), off: bg(ys.find((b) => b.getAttribute('aria-pressed') !== 'true')) };
    });
    await page.emulateMedia({ forcedColors: 'none' });
    assert(st.on !== st.off, `pressed ${st.on} = ${st.off}`);
    const f = await page.evaluate(() => ({
      layer: getComputedStyle(document.querySelector('.tiles-muted')).filter,
      tile: document.querySelector('.tiles-muted .leaflet-tile') ? getComputedStyle(document.querySelector('.tiles-muted .leaflet-tile')).filter : 'none?',
    }));
    assert(f.layer === 'none' && f.tile !== 'none', JSON.stringify(f));
  });

  await check('a street-level point gets no fixed 150 m circle (only a stated geo.uncertainty_m is drawn)', async () => {
    const street = [...recordsDoc.records, ...(permitsDoc?.records || [])].find((r) => r.geo?.method === 'street' && typeof r.geo?.lat === 'number' && r.geo.uncertainty_m == null);
    if (!street) return;
    await page.goto(`${url}#/wpis/${encodeURIComponent(street.id)}${OPT_IN.test(street.id) ? `?rodzaj=wz,cp,ws,${street.kind}` : ''}`);
    await waitReady(page);
    await page.waitForSelector('#detail .detail__title:not(.sr-only)');
    await settle(page, 600);
    assert(await page.locator('.leaflet-overlay-pane path[stroke-dasharray="5 5"]').count() === 0, 'dashed circle drawn');
  });

  await check('Esc hides the timeline tip; the tip stays while the pointer is on it', async () => {
    await page.goto(`${url}#/`);
    await waitReady(page);
    const box = await page.locator('.timeline__chart').boundingBox();
    await page.mouse.move(box.x + box.width * 0.9, box.y + box.height * 0.6);
    await settle(page, 150);
    const tip = page.locator('.timeline__tip');
    assert(await tip.isVisible(), 'no tip on hover');
    const tb = await tip.boundingBox();
    await page.mouse.move(tb.x + tb.width / 2, tb.y + tb.height / 2, { steps: 4 });
    await settle(page, 150);
    assert(await tip.isVisible(), 'tip vanished when hovered');
    await page.keyboard.press('Escape');
    await settle(page, 100);
    assert(await tip.isHidden(), 'Esc did not hide the tip');
  });
}

async function d_scrollTop(page) {
  await page.evaluate(() => { const p = document.querySelector('#detail'); if (p) p.scrollTop = 0; });
}

const counts = () => recordsDoc.counts_by_kind || {};

async function mobileSuite(scheme) {
  currentGroup = `mobile-${scheme}`;
  console.log(`\n${currentGroup}`);
  const { context, page, errors } = await newPage({
    viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, colorScheme: scheme,
  });
  await check('mobile layout: single column, no horizontal scroll, map hidden', async () => {
    await page.goto(server.url);
    await waitReady(page);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    assert(overflow <= 0, `horizontal overflow ${overflow}px`);
    assert(await page.locator('.pane--map').isHidden(), 'map visible in list mode');
    assert(await page.locator('.fab').isVisible(), 'list/map toggle missing');
  });
  await shot(page, `${currentGroup}-list`);

  await check('filters open as a full-screen sheet (focus trapped) and close', async () => {
    await page.locator('.filters-toggle').click();
    await settle(page, 350);
    assert(await page.locator('#filters[role="dialog"]').isVisible(), 'drawer not open');
    assert(await page.evaluate(() => document.querySelector('#filters').contains(document.activeElement)), 'focus not in drawer');
  });
  await shot(page, `${currentGroup}-filters`);
  await check('filters sheet closes with the results button', async () => {
    await page.locator('.filters__foot .btn').click();
    await settle(page, 350);
    assert(!(await page.locator('#filters[role="dialog"]').count()), 'drawer still open');
    const gap = await page.evaluate(() => document.querySelector('#results-count').getBoundingClientRect().top
      - document.querySelector('.topbar').getBoundingClientRect().bottom);
    assert(gap >= 0, `result count hidden under the top bar (${gap}px)`);
  });

  await check('list/map toggle shows the map (tryb=mapa)', async () => {
    await page.locator('.fab').click();
    await settle(page, 600);
    assert(await page.locator('.pane--map').isVisible(), 'map hidden');
    assert((await hashOf(page)).includes('tryb=mapa'), 'mode not in URL');
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    assert(overflow <= 0, `horizontal overflow ${overflow}px`);
  });
  await shot(page, `${currentGroup}-map`);

  await check('detail opens as a full-screen modal sheet', async () => {
    await page.locator('.fab').click();
    await settle(page, 300);
    await page.locator('.cards .card .card__link').first().click();
    await page.waitForSelector('#detail[role="dialog"]');
    const box = await page.locator('#detail').boundingBox();
    assert(box.width >= 389 && box.height >= 800, `sheet size ${box.width}x${box.height}`);
  });
  await shot(page, `${currentGroup}-detail`);
  await check('mobile detail closes with the back button', async () => {
    await page.locator('#detail .detail__close').click();
    await settle(page);
    assert(await page.locator('#detail').isHidden(), 'detail still open');
  });
  await check('worst-case records never make the detail sheet scroll sideways (320 px)', async () => {
    // Longest unbroken raw parcel text (e.g. "3/27,3/6,3/5,…"), longest related chain, longest applicant – and from the
    // permits (when present): the longest unbroken investment text ("Przeworskiej,Siennickiej,…"), the most parcels.
    const byLen = (f, list = recordsDoc.records) => [...list].sort((a, b) => f(b) - f(a))[0];
    const longestToken = (t) => Math.max(0, ...String(t || '').split(/\s+/).map((w) => w.length));
    const picks = new Set([
      byLen((r) => longestToken(r.parcels_raw)).id,
      byLen((r) => (r.related || []).length).id,
      byLen((r) => (r.applicant || '').length).id,
      byLen((r) => longestToken(r.investment)).id,
      ...(HAS_PERMITS ? [
        byLen((r) => longestToken(r.investment), permitsDoc.records).id,
        byLen((r) => (r.parcels || []).length, permitsDoc.records).id,
      ] : []),
    ]);
    await page.setViewportSize({ width: 320, height: 640 });
    for (const id of picks) {
      await page.goto(`${server.url}#/wpis/${encodeURIComponent(id)}`);
      await waitReady(page);
      await page.waitForSelector('#detail .detail__title:not(.sr-only)'); // a permit shows a loading panel first
      await page.$$eval('#detail details', (ds) => ds.forEach((d) => { d.open = true; }));
      await page.locator('#detail .chain__gap button').first().click().catch(() => {});
      const over = await page.evaluate(() => {
        const pane = document.querySelector('#detail');
        return pane.scrollWidth - pane.clientWidth;
      });
      assert(over <= 1, `${id}: detail sheet is ${over}px wider than the screen`);
    }
    await page.setViewportSize({ width: 390, height: 844 });
  });

  await check('mobile: first screen says where and that the service is unofficial; the intro can be dismissed for good', async () => {
    await page.goto(server.url);
    await waitReady(page);
    const first = await page.evaluate(() => [...document.querySelectorAll('.topbar, .intro')]
      .filter((e) => e.getBoundingClientRect().bottom <= window.innerHeight).map((e) => e.innerText).join(' '));
    assert(/Praga-Południe|Pragi-Południe/.test(first) && /nieoficjalny/.test(first), `first screen: ${first.slice(0, 200)}`);
    const intro = page.locator('.intro');
    if (await intro.count()) {
      await intro.getByRole('button', { name: 'Ukryj wprowadzenie' }).click();
      await page.reload();
      await waitReady(page);
      assert(await page.locator('.intro').count() === 0, 'intro back after reload');
    }
  });

  await check('mobile: cards show at most 3 tag chips plus "+N"', async () => {
    const counts = await page.$$eval('.cards .card__tags', (uls) => uls.map((ul) => [...ul.children].filter((li) => getComputedStyle(li).display !== 'none' && !li.classList.contains('card__tags-more')).length));
    assert(counts.length && Math.max(...counts) <= 3, `visible tags per card: ${Math.max(...counts)}`);
    const many = [...recordsDoc.records].find((r) => (r.tags || []).length > 3);
    if (many && await page.locator(`.card[data-id="${many.id}"]`).count()) {
      assert(await page.locator(`.card[data-id="${many.id}"] .card__tags-more`).isVisible(), 'no "+N" chip');
    }
  });

  await check('mobile: "Wskaż na mapie" keeps a banner with "Anuluj"; a tap on a group picks that place', async () => {
    await page.locator('.filters-toggle').click();
    await settle(page, 350);
    await page.locator('#filters button', { hasText: 'Wskaż na mapie' }).click();
    await page.waitForSelector('.pick-banner');
    assert(/Dotknij/.test(await page.locator('.pick-banner').innerText()), 'touch wording');
    await settle(page, 1500);
    assert(await page.locator('.pick-banner').isVisible(), 'banner gone');
    await page.locator('.pick-banner').getByRole('button', { name: 'Anuluj' }).click();
    assert(await page.locator('#map.is-picking').count() === 0 && await page.locator('.pick-banner').count() === 0, 'Anuluj did not end picking');
    await page.locator('.filters-toggle').click();
    await settle(page, 350);
    await page.locator('#filters button', { hasText: 'Wskaż na mapie' }).click();
    await page.waitForSelector('.pick-banner');
    await settle(page, 800);
    // A group or marker well inside the visible map (Leaflet keeps some off-screen icons in the DOM).
    const at = await page.evaluate(() => {
      const m = document.querySelector('#map').getBoundingClientRect();
      for (const el of document.querySelectorAll('.leaflet-marker-icon.cl-wrap, .leaflet-marker-icon.mk-wrap')) {
        const r = el.getBoundingClientRect();
        if (r.left > m.left + 20 && r.right < m.right - 60 && r.top > m.top + 100 && r.bottom < m.bottom - 140) return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
      }
      return null;
    });
    assert(at, 'no marker or group on the map');
    await page.touchscreen.tap(at.x, at.y);
    await page.waitForFunction(() => window.location.hash.includes('blisko='), null, { timeout: 3000 });
    assert(await page.locator('.pick-banner').count() === 0, 'banner stays');
    assert(await page.locator('.fab').getAttribute('aria-label').then((l) => /^Lista/.test(l)), 'fab name does not start with its visible label');
  });

  await check('mobile: "/" inside an open record does not close it', async () => {
    const rec = recordsDoc.records.find((r) => (r.parcels || []).some((p) => p.id));
    await page.goto(`${server.url}#/wpis/${encodeURIComponent(rec.id)}`);
    await waitReady(page);
    await page.waitForSelector('#detail[role="dialog"]');
    await page.locator('#detail a.parcel__link').first().focus();
    await page.keyboard.press('/');
    await settle(page, 200);
    assert((await hashOf(page)).includes('/wpis/'), 'record closed by "/"');
    assert(/^Wróć/.test(await page.locator('#detail .detail__close').getAttribute('aria-label')), 'close button name does not start with "Wróć"');
  });

  await check('mobile: filters sheet – keyboard focus never under its sticky head or "Pokaż N wpisów" footer', async () => {
    await page.goto(server.url);
    await waitReady(page);
    await page.locator('.filters-toggle').click();
    await settle(page, 350);
    const fwd = await tabWalk(page, 50);
    const back = await tabWalk(page, 50, true);
    assert(!fwd.length && !back.length, [...fwd, ...back].slice(0, 3).join('\n'));
    await page.keyboard.press('Escape');
  });

  await check('narrow and short screens: no sideways scroll at 300 px; a landscape phone keeps a usable map', async () => {
    await page.setViewportSize({ width: 300, height: 640 });
    await page.goto(server.url);
    await waitReady(page);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'sideways scroll at 300 px');
    await page.setViewportSize({ width: 568, height: 320 });
    await page.goto(`${server.url}#/?tryb=mapa`);
    await waitReady(page);
    await settle(page, 600);
    const m = await page.locator('#map').boundingBox();
    assert(m && m.height >= 200, `map ${m && Math.round(m.height)} px tall`);
    const atSearch = await page.evaluate(() => { const r = document.querySelector('.search').getBoundingClientRect(); return Boolean(document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2)?.closest('.search')); });
    assert(atSearch, 'search covered');
    await page.setViewportSize({ width: 390, height: 844 });
  });

  if (HAS_PERMITS) {
    await check('mobile: next to a search the promo names no register total (permits not loaded on phones)', async () => {
      const street = recordsDoc.records.find((r) => r.address?.street)?.address.street;
      await page.goto(`${server.url}#/?q=${encodeURIComponent(street)}`);
      await waitReady(page);
      const promo = page.locator('.promo');
      if (await promo.isVisible()) {
        const t = await promo.innerText();
        assert(/dla tego wyszukiwania/.test(t) && !new RegExp(`\\(${counts().pb}\\)`).test(t), `promo: ${t}`);
      }
    });

    await check('mobile: permits switched on in the filters sheet, permit detail as a sheet, no sideways scroll', async () => {
      await page.goto(server.url);
      await waitReady(page);
      await page.locator('.filters-toggle').click();
      await settle(page, 350);
      await page.getByRole('checkbox', { name: new RegExp(kindLabel('pb')) }).check();
      await page.waitForSelector('body[data-permits="loaded"]');
      await settle(page);
      await page.locator('.filters__foot .btn').click();
      await settle(page, 350);
      assert(/rodzaj=wz,cp,ws,pb/.test(await hashOf(page)), 'kind not in URL');
      // The longer timeline legend wraps; the "Tabela" button stays on the screen.
      const tableBtn = await page.locator('.timeline button', { hasText: 'Tabela' }).boundingBox();
      assert(tableBtn && tableBtn.x + tableBtn.width <= 390, `"Tabela" pushed off the screen (right edge ${tableBtn && Math.round(tableBtn.x + tableBtn.width)})`);
      const card = page.locator('.cards .card[data-kind="pb"]').first();
      await card.locator('.card__link').click();
      await page.waitForSelector('#detail[role="dialog"]');
      const over = await page.evaluate(() => document.querySelector('#detail').scrollWidth - document.querySelector('#detail').clientWidth);
      assert(over <= 1, `detail ${over}px too wide`);
    });
    await shot(page, `${currentGroup}-permit`);
    await check('mobile: sources tabs fit the screen', async () => {
      await page.goto(`${server.url}#/zrodla/rwdz`);
      await page.waitForSelector('.src-panel--rwdz');
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      assert(overflow <= 0, `horizontal overflow ${overflow}px`);
    });
    await shot(page, `${currentGroup}-sources`);
  }

  await check('no console errors', async () => {
    assert(errors.length === 0, errors.join('\n'));
  });
  await context.close();
}

async function robustnessSuite() {
  currentGroup = 'robustness';
  console.log(`\n${currentGroup}`);
  await check('data load failure shows a friendly error with retry', async () => {
    const { context, page } = await newPage({ viewport: { width: 1024, height: 768 } });
    await page.route('**/data/records.json', (r) => r.fulfill({ status: 500, body: 'boom' }));
    await page.goto(server.url);
    await page.waitForSelector('.error-state');
    assert(/Nie udało się wczytać danych/.test(await page.locator('.error-state').innerText()), 'no message');
    await context.close();
  });
  await check('the data error page links the official lists; technical details are folded away', async () => {
    const { context, page } = await newPage({ viewport: { width: 1024, height: 768 } });
    await page.route('**/data/records.json', (r) => r.fulfill({ status: 404, body: '' }));
    await page.goto(server.url);
    await page.waitForSelector('.error-state');
    const hrefs = await page.locator('.error-state a').evaluateAll((as) => as.map((a) => a.href));
    assert(hrefs.some((h) => h.startsWith('https://pragapld.um.warszawa.pl/')), 'no link to the district office');
    assert(!/python3/.test(await page.locator('.error-state').innerText()), 'developer hint visible');
    await context.close();
  });
  await check('a module that fails to load shows "Odśwież" instead of the skeleton forever', async () => {
    const { context, page } = await newPage({ viewport: { width: 1024, height: 768 } });
    await page.route('**/js/kinds.js', (r) => r.abort());
    await page.goto(server.url);
    await page.waitForSelector('[role="alert"]', { timeout: 6000 });
    assert(/Odśwież/.test(await page.locator('[role="alert"]').innerText()), 'no reload button');
    await context.close();
  });
  await check('Back while the filters drawer is open closes it: top bar not inert, Tab moves on (1024 px)', async () => {
    const { context, page } = await newPage({ viewport: { width: 1024, height: 768 } });
    await page.goto(`${server.url}#/zrodla`);
    await waitReady(page);
    await page.locator('a[data-nav="explore"]').click();
    await page.waitForSelector('.cards .card');
    await page.locator('.filters-toggle').click();
    await settle(page, 300);
    await page.goBack();
    await page.waitForFunction(() => window.location.hash === '#/zrodla');
    await settle(page, 300);
    const st = await page.evaluate(() => ({ inert: document.querySelector('.topbar').inert, open: document.querySelector('.explore').classList.contains('is-drawer-open') }));
    assert(!st.inert && !st.open, JSON.stringify(st));
    const before = await page.evaluate(() => document.activeElement?.outerHTML.slice(0, 60));
    await page.keyboard.press('Tab');
    const after = await page.evaluate(() => document.activeElement?.outerHTML.slice(0, 60));
    assert(before !== after, 'Tab is stuck');
    await page.locator('nav.topnav a[data-nav="about"]').click({ timeout: 2000 });
    await context.close();
  });
  await check('missing optional geo layers are handled gracefully', async () => {
    const { context, page, errors } = await newPage({ viewport: { width: 1280, height: 800 } });
    await page.route('**/data/areas.geojson', (r) => r.fulfill({ status: 404, body: '' }));
    await page.route('**/data/parcels.geojson', (r) => r.fulfill({ status: 200, body: '' }));
    await page.goto(server.url);
    await waitReady(page);
    assert(await page.locator('.cards .card').count() > 0, 'no cards');
    const real = errors.filter((e) => !/404|Failed to load resource/.test(e));
    assert(real.length === 0, real.join('\n'));
    await context.close();
  });
  if (recordsDoc.kinds?.pb || recordsDoc.counts_by_kind?.pb) await check('missing permits layer: the planning records still work; switching permits on explains and offers a retry', async () => {
    const { context, page, errors } = await newPage({ viewport: { width: 1280, height: 800 } });
    await page.route('**/data/permits.json', (r) => r.fulfill({ status: 404, body: '' }));
    await page.goto(`${server.url}#/?rodzaj=wz,cp,ws,pb`);
    await waitReady(page);
    await page.waitForSelector('body[data-permits="error"]');
    await page.waitForSelector('.pending--error');
    assert(/Spróbuj ponownie/.test(await page.locator('.pending').innerText()), 'no retry');
    assert(await page.locator('.cards .card').count() > 0, 'planning records gone');
    // A failed register is not re-requested (and re-toasted) on every state change; the promo is not offered.
    let requests = 0;
    page.on('request', (r) => { if (r.url().endsWith('/data/permits.json')) requests += 1; });
    for (const q of ['a', 'ab', 'abc']) {
      await page.evaluate((x) => { window.location.hash = `#/?rodzaj=wz,cp,ws,pb&q=${x}`; }, q);
      await settle(page, 200);
    }
    assert(requests === 0, `${requests} new requests after the failure`);
    assert(await page.locator('.toast--error').count() <= 1, 'stacked error toasts');
    await page.evaluate(() => { window.location.hash = '#/?rodzaj=pb'; });
    await settle(page, 300);
    assert(/Nie udało się wczytać rejestru/.test(await page.locator('.pending').innerText()), 'strip says "pokazujemy pozostałe" with nothing else selected');
    assert(!/Szukaj też w pozwoleniach/.test(await page.locator('.empty').innerText().catch(() => '')), 'offers the failed register');
    await page.evaluate(() => { window.location.hash = '#/'; });
    await settle(page, 300);
    assert(await page.locator('.promo').isHidden(), 'promo offers the failed register');
    const real = errors.filter((e) => !/404|Failed to load resource/.test(e));
    assert(real.length === 0, real.join('\n'));
    await context.close();
  });
  await check('opening index.html via file:// explains how to start a server', async () => {
    const { context, page } = await newPage({ viewport: { width: 1024, height: 768 } });
    await page.goto(pathToFileURL(join(ROOT, 'site', 'index.html')).href);
    await page.waitForSelector('.page--file');
    assert(/serwer/i.test(await page.locator('.page--file').innerText()), 'no message');
    await context.close();
  });
  await check('stale permalink shows a "not found" panel', async () => {
    const { context, page } = await newPage({ viewport: { width: 1280, height: 800 } });
    await page.goto(`${server.url}#/wpis/wz-1999-999`);
    await waitReady(page);
    await page.waitForSelector('#detail .empty');
    assert(/Nie znaleziono wpisu/.test(await page.locator('#detail').innerText()), 'no message');
    await context.close();
  });
}

/** Safari / iOS engine (optional: runs when Playwright's WebKit is installed). */
async function webkitSuite() {
  currentGroup = 'webkit';
  console.log(`\n${currentGroup}`);
  let wk;
  try {
    wk = await webkit.launch();
  } catch {
    console.log('  – WebKit not installed (npx playwright-core install webkit): skipped');
    return;
  }
  try {
    const context = await wk.newContext({ viewport: { width: 1280, height: 800 }, locale: 'pl-PL' });
    const page = await context.newPage();
    const data = [];
    page.on('request', (r) => { if (/\/data\/(records|sources)\.json$/.test(r.url())) data.push(r.url().split('/').pop()); });
    await check('each data file is requested once (the early fetch is reused)', async () => {
      await page.goto(server.url);
      await waitReady(page);
      await settle(page, 500);
      assert(data.length === 2 && new Set(data).size === 2, data.join(', '));
    });
    await check('the muting filter sits on the tiles (WebKit leaves a filtered 0×0 layer partly blank)', async () => {
      await page.waitForSelector('.leaflet-container');
      const f = await page.evaluate(() => ({
        layer: getComputedStyle(document.querySelector('.tiles-muted')).filter,
        tile: getComputedStyle(document.querySelector('.tiles-muted .leaflet-tile') || document.body).filter,
      }));
      assert(f.layer === 'none' && f.tile !== 'none', JSON.stringify(f));
    });
    await context.close();
  } finally {
    await wk.close();
  }
}

try {
  for (const scheme of ['light', 'dark']) {
    if (!ONLY || ONLY === `desktop-${scheme}`) await desktopSuite(scheme);
    if (!ONLY || ONLY === `mobile-${scheme}`) await mobileSuite(scheme);
  }
  if (!ONLY || ONLY === 'robustness') await robustnessSuite();
  if (!ONLY || ONLY === 'webkit') await webkitSuite();
} finally {
  await browser.close();
  await server.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed · screenshots in ${OUT}`);
if (failed.length) {
  console.log('Failed:\n' + failed.map((f) => `  - ${f.label}`).join('\n'));
  process.exitCode = 1;
}
