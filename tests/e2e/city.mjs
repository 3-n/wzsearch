/**
 * Browser checks of the city-wide site (docs/plans/all-districts.md §7), against the REAL build in site/data
 * (`make city-offline` first): the district picker, links without dz, permalinks of other districts, "Cała Warszawa",
 * its permits (desktop opt-in, phones sent to a district), the "niepełne dane" notes and the phone top bar.
 * Drives the system Google Chrome via playwright-core.   Usage: npm run e2e:city
 */
import { chromium } from 'playwright-core';
import { existsSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { startServer } from './server.mjs';

const ROOT = resolve(fileURLToPath(new URL('../..', import.meta.url)));
const DATA = join(ROOT, 'site', 'data');
if (!existsSync(join(DATA, 'districts.json'))) {
  console.error('site/data/districts.json is missing – run `make city-offline` first.');
  process.exit(2);
}
const index = JSON.parse(readFileSync(join(DATA, 'districts.json'), 'utf8'));
const read = (p) => JSON.parse(readFileSync(join(DATA, p), 'utf8'));
const ppRecord = read('records.json').records.find((r) => r.dataset === 'district');
const bemRecord = read('d/bemowo/records.json').records.find((r) => /^wz-bem-/.test(r.id));
const withGaps = index.districts.filter((d) => d.gaps).map((d) => d.name);

const results = [];
async function check(name, fn) {
  try {
    await fn();
    results.push(true);
    console.log(`  ✓ ${name}`);
  } catch (err) {
    results.push(false);
    console.log(`  ✗ ${name}\n    ${String(err?.message || err).split('\n').slice(0, 6).join('\n    ')}`);
  }
}
function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const server = await startServer({ data: 'site', base: '/wzsearch/' });
const { url } = server;
const browser = await chromium.launch({ channel: 'chrome' });
const errors = [];

async function newPage(opts = {}) {
  const context = await browser.newContext({ locale: 'pl-PL', timezoneId: 'Europe/Warsaw', ...opts });
  const page = await context.newPage();
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  page.on('console', (m) => {
    if (m.type() === 'error' && !/openstreetmap|geoportal|gugik/.test(`${m.text()} ${m.location()?.url || ''}`)) {
      errors.push(`${m.text()} ${m.location()?.url || ''}`);
    }
  });
  return page;
}
const ready = (page) => page.waitForFunction(() => document.querySelectorAll('.cards .card').length > 0, null, { timeout: 30000 });
// A fresh load: a dz change in the hash makes the app reload itself, which races page.reload().
const fresh = async (page, to) => { await page.goto('about:blank'); await page.goto(to); };
const dz = (page) => new URL(page.url()).hash.match(/[?&]dz=([a-z-]+)/)?.[1] || null;

console.log('desktop');
{
  const page = await newPage({ viewport: { width: 1280, height: 900 } });
  await check('a bare link opens Praga-Południe; the brand is "wzSearch Warszawa"', async () => {
    await page.goto(url);
    await ready(page);
    assert(dz(page) === 'praga-poludnie', `dz=${dz(page)}`);
    assert((await page.locator('.brand__sub').innerText()) === 'Warszawa', 'brand sub');
    assert((await page.locator('.district-switch__name').innerText()) === 'Praga-Południe', 'switch name');
  });
  await check('the picker switches district (Wola) and names the gaps of thin districts', async () => {
    await page.locator('.district-switch').click();
    const notes = await page.locator('.district-list__note').allInnerTexts();
    for (const name of withGaps) {
      const row = page.locator('.district-list__link', { hasText: name }).first();
      assert(/Niepełne dane/.test(await row.innerText()), `no gap note for ${name}`);
    }
    assert(notes.length >= withGaps.length, 'gap notes');
    await page.locator('.district-list__link', { hasText: /^Wola/ }).first().click();
    await page.waitForFunction(() => /dz=wola/.test(location.hash));
    await ready(page);
    assert((await page.locator('.district-switch__name').innerText()) === 'Wola', 'switch shows Wola');
  });
  await check('a bare link after visiting Wola still opens Praga-Południe (no remembered choice)', async () => {
    await fresh(page, url);
    await ready(page);
    assert(dz(page) === 'praga-poludnie', `dz=${dz(page)}`);
  });
  await check('a legacy permalink without dz opens in Praga-Południe', async () => {
    await fresh(page, `${url}#/wpis/${encodeURIComponent(ppRecord.id)}`);
    await page.waitForSelector('#detail .facts', { timeout: 20000 });
    assert(dz(page) === 'praga-poludnie', `dz=${dz(page)}`);
  });
  await check('a permalink of another district without dz opens in that district', async () => {
    await fresh(page, `${url}#/wpis/${encodeURIComponent(bemRecord.id)}`);
    await page.waitForSelector('#detail .facts', { timeout: 20000 });
    assert(dz(page) === 'bemowo', `dz=${dz(page)}`);
  });
  await check('"Cała Warszawa": districts as areas, a record opens in its district', async () => {
    await fresh(page, `${url}#/?dz=warszawa`);
    await ready(page);
    assert((await page.locator('.district-switch__name').innerText()) === 'Cała Warszawa', 'switch');
    await page.locator('.cards .card').first().click();
    await page.waitForSelector('#detail .facts', { timeout: 20000 });
    assert(dz(page) && dz(page) !== 'warszawa', `record opened in ${dz(page)}`);
  });
  await check('"Cała Warszawa" on desktop: permits load only when switched on, and the panel names the size', async () => {
    const requests = [];
    page.on('request', (r) => { if (/warszawa\/permits\.json/.test(r.url())) requests.push(r.url()); });
    await fresh(page, `${url}#/?dz=warszawa`);
    await ready(page);
    await page.waitForTimeout(3500);   // longer than the idle prefetch delay
    assert(requests.length === 0, 'prefetched');
    assert(/całej Warszawy \(ok\. [\d,]+ MB\)/.test(await page.locator('.kinds-optin__hint').innerText()), 'size hint');
    await page.locator('.kinds-optin label', { hasText: 'Pozwolenie' }).first().click();
    await page.waitForFunction(() => document.body.dataset.permits === 'loaded', null, { timeout: 60000 });
    assert(requests.length === 1, `${requests.length} requests`);
  });
  await page.context().close();
}

console.log('phone');
{
  const page = await newPage({ viewport: { width: 360, height: 780 }, isMobile: true, hasTouch: true });
  await check('the top bar fits at 360 px: brand, district switch and three nav links on one line', async () => {
    await page.goto(`${url}#/?dz=praga-poludnie`);
    await ready(page);
    const boxes = await page.evaluate(() => [...document.querySelectorAll('.topnav a')].map((a) => a.getBoundingClientRect().height));
    assert(boxes.every((hgt) => hgt <= 34), `nav heights ${boxes}`);
    const over = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    assert(!over, 'horizontal scroll');
    assert(await page.locator('.district-switch').isVisible(), 'switch hidden');
  });
  await check('"Cała Warszawa" on a phone: permit kinds disabled, nothing downloaded, a way to a district', async () => {
    const requests = [];
    page.on('request', (r) => { if (/permits\.json/.test(r.url())) requests.push(r.url()); });
    await fresh(page, `${url}#/?dz=warszawa`);
    await ready(page);
    await page.locator('button', { hasText: /Filtry/ }).first().click();
    assert(await page.locator('.kinds-optin input').first().isDisabled(), 'enabled');
    await page.locator('.kinds-optin__blocked button').click();
    await page.waitForFunction(() => document.querySelector('.district-dialog')?.open);
    assert(requests.length === 0, 'downloaded');
  });
  await page.context().close();
}

await browser.close();
await server.close();
console.log(errors.length ? `\nconsole errors:\n  ${errors.join('\n  ')}` : '\nno console errors');
const failed = results.filter((r) => !r).length + (errors.length ? 1 : 0);
console.log(`${results.length - results.filter((r) => !r).length}/${results.length} checks passed`);
process.exit(failed ? 1 : 0);
