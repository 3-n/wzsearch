#!/usr/bin/env node
/**
 * Page speed on the real data – the table in docs/plans/all-districts.md §5a (phase 3): time to the `wz:ready` mark
 * and the longest main-thread task, on a desktop viewport and on a phone (390 px, CPU slowed down 4×).
 *
 *   node scripts/page_speed.mjs [dz …]      (default: praga-poludnie wawer bialoleka warszawa)
 *
 * Needs `npm install` (playwright-core) and Chrome; serves site/ itself (tests/e2e/server.mjs) on port 8026.
 */
import { chromium } from 'playwright-core';
import { startServer } from '../tests/e2e/server.mjs';

const slugs = process.argv.slice(2).length ? process.argv.slice(2) : ['praga-poludnie', 'wawer', 'bialoleka', 'warszawa'];
const server = await startServer({ port: 8026, data: 'site' });
const browser = await chromium.launch({ channel: 'chrome' });
const LONG = () => {
  window.__long = [];
  new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__long.push(Math.round(e.duration)); })
    .observe({ type: 'longtask', buffered: true });
};
console.log('| page | ready | longest task | phone: ready | phone: longest task |\n|---|---:|---:|---:|---:|');
for (const slug of slugs) {
  const cells = [];
  for (const phone of [false, true]) {
    const page = await browser.newPage(phone
      ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }
      : { viewport: { width: 1280, height: 860 } });
    await page.addInitScript(LONG);
    if (phone) await (await page.context().newCDPSession(page)).send('Emulation.setCPUThrottlingRate', { rate: 4 });
    await page.goto(`http://127.0.0.1:8026/#/?dz=${slug}`);
    await page.waitForSelector('body[data-ready="true"]', { timeout: 60000 });
    const ready = await page.evaluate(() => Math.round(performance.getEntriesByName('wz:ready')[0]?.startTime || -1));
    await page.waitForTimeout(phone ? 4000 : 2000);
    const long = await page.evaluate(() => window.__long);
    cells.push(`${ready} ms`, `${Math.max(0, ...long)} ms`);
    await page.close();
  }
  console.log(`| ${slug} | ${cells.join(' | ')} |`);
}
await browser.close();
await server.close?.();
process.exit(0);
