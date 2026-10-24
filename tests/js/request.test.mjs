import { test } from 'node:test';
import assert from 'node:assert/strict';
import { infoRequest, requestItems, mailtoHref } from '../../site/js/request.js';

const wz = {
  issuer: 'city', number: '95/AM/PPD/WZ/2026/O', date: '2026-09-16', address: { display: 'Ostrobramska 73' },
  parcels: [{ number: '7/5', obreb: '3-05-24', partial: true }],
};
const pb = {
  issuer: 'district', number: '163/PPD/PB/2026', date: '2026-10-14', address: { display: 'Salamandry 3' },
  parcels: [{ number: '25/12', obreb: '3-06-05' }],
  permit: { register_id: 'ST-MZ-PA/WNIOSEK/29594/2026', case_sign: 'RPW/142815/2026-1B/FSO' },
};

test('a WZ decision asks for the decision with attachments, the urban analysis and the application', () => {
  const items = requestItems('wz', wz);
  assert.equal(items.length, 3);
  assert.match(items[0], /decyzji o warunkach zabudowy nr 95\/AM\/PPD\/WZ\/2026\/O z dnia 16 września 2026/);
  assert.match(items[0], /załącznikiem graficznym/);
  assert.match(items[1], /analizy funkcji oraz cech zabudowy/);
});

test('the addressee follows the issuing office; the letter names the case, address and parcels', () => {
  const req = infoRequest('wz', wz, { kindLabel: 'Decyzja o warunkach zabudowy' });
  assert.equal(req.to, 'sekretariat.BAiPP@um.warszawa.pl');
  assert.equal(req.fallback, 'kancelaria@um.warszawa.pl');
  assert.equal(infoRequest('pb', pb).to, 'pragapoludnie.urzad@um.warszawa.pl');
  assert.match(req.body, /^Prezydent m\.st\. Warszawy\nUrząd m\.st\. Warszawy\nBiuro Architektury i Planowania Przestrzennego\n/);
  assert.match(req.body, /Dotyczy: Decyzja o warunkach zabudowy 95\/AM\/PPD\/WZ\/2026\/O; adres: Ostrobramska 73; działka ewid\. cz\. 7\/5 \(obręb 3-05-24\)\./);
  assert.match(req.body, /art\. 2 ust\. 1 ustawy z dnia 6 września 2001 r\. o dostępie do informacji publicznej/);
  assert.equal(req.subject, 'Wniosek o udostępnienie informacji publicznej – WZ 95/AM/PPD/WZ/2026/O');
  assert.match(infoRequest('pb', pb).body, /Wydział Architektury i Budownictwa dla Dzielnicy Praga-Południe/);
});

test('a building permit names the office case sign and asks for the site plan, with inspection as a fallback', () => {
  const items = requestItems('pb', pb);
  assert.match(items[0], /\(znak sprawy RPW\/142815\/2026-1B\/FSO\)/);
  assert.match(items[1], /projektu zagospodarowania działki lub terenu/);
  assert.match(items[1], /wglądu/);
  assert.match(infoRequest('pb', pb).body, /nr w rejestrze GUNB ST-MZ-PA\/WNIOSEK\/29594\/2026/);
});

test('an initiated case asks for the application and the stage; a notification asks about an objection', () => {
  const ws = requestItems('ws', { number: 'UD-VI-WAB-U.6730.36.2026.AZM', procedure: 'wz' });
  assert.match(ws[0], /wniosku w sprawie o znaku UD-VI-WAB-U\.6730\.36\.2026\.AZM/);
  assert.match(ws[1], /etapie postępowania/);
  const zg = requestItems('zg', { number: 'RPW/1/2026', permit: { case_sign: 'RPW/1/2026' } });
  assert.match(zg[0], /znak sprawy RPW\/1\/2026/);
  assert.match(zg[1], /sprzeciw/);
});

test('voivode cases go to the voivode office (no city fallback); unknown issuers get no prefilled address', () => {
  const v = infoRequest('pb', { ...pb, issuer: 'voivode' });
  assert.equal(v.to, 'info@mazowieckie.pl');
  assert.equal(v.fallback, '');
  assert.match(v.note, /Wojewoda Mazowiecki/);
  assert.match(v.body, /^Wojewoda Mazowiecki\n/);
  assert.equal(infoRequest('pb', { ...pb, issuer: undefined }).to, '');
});

test('long parcel lists are capped', () => {
  const parcels = Array.from({ length: 8 }, (_, i) => ({ number: `${i + 1}`, obreb: '3-05-24' }));
  assert.match(infoRequest('cp', { issuer: 'district', parcels }).body, /działki ewid\. 1 \(obręb 3-05-24\), .*5 \(obręb 3-05-24\) i 3 innych/);
});

test('mailto: encodes subject and body, with CRLF line breaks', () => {
  const href = mailtoHref({ to: 'kancelaria@um.warszawa.pl', subject: 'A & B', body: 'x\ny?' });
  assert.equal(href, 'mailto:kancelaria@um.warszawa.pl?subject=A%20%26%20B&body=x%0D%0Ay%3F');
  assert.ok(mailtoHref({ to: '', subject: 's', body: 'b' }).startsWith('mailto:?subject='));
});
