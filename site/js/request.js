/**
 * "Zapytaj urząd" – a ready-to-send request for public information (wniosek o udostępnienie informacji publicznej)
 * about one record: the addressee follows the issuing office, the list of documents follows the kind
 * (decision → decision + attachments + urban analysis; initiated case → application + stage; permit → decision +
 * site plan; notification → notification + objection status). Nothing is sent from the site: the letter goes
 * through the user's own mail program, or is copied into ePUAP / e-Doręczenia.
 * DOM-free (unit-tested in tests/js/request.test.mjs).
 */
import { formatDate } from './format.js';
import { INFO_REQUEST } from './config.js';

/** Who receives the request, per issuer code (docs/DATA_MODEL.md). `email` empty → the user fills in the address. */
export const ADDRESSEES = {
  district: {
    lines: ['Prezydent m.st. Warszawy', 'Urząd m.st. Warszawy', 'Wydział Architektury i Budownictwa dla Dzielnicy Praga-Południe'],
    email: INFO_REQUEST.emails.district, inbox: 'Urząd Dzielnicy Praga-Południe',
    fallback: INFO_REQUEST.fallback, edelivery: INFO_REQUEST.edelivery,
  },
  city: {
    lines: ['Prezydent m.st. Warszawy', 'Urząd m.st. Warszawy', 'Biuro Architektury i Planowania Przestrzennego'],
    email: INFO_REQUEST.emails.city, inbox: 'sekretariat Biura Architektury i Planowania Przestrzennego',
    fallback: INFO_REQUEST.fallback, edelivery: INFO_REQUEST.edelivery,
  },
  voivode: {
    lines: ['Wojewoda Mazowiecki', 'Mazowiecki Urząd Wojewódzki w Warszawie'],
    email: INFO_REQUEST.emails.voivode, inbox: 'Mazowiecki Urząd Wojewódzki', fallback: '', edelivery: '',
    note: 'Tę sprawę prowadził Wojewoda Mazowiecki, nie urząd miasta – wniosek trafia do Mazowieckiego Urzędu Wojewódzkiego.',
  },
  other: {
    lines: ['[nazwa organu, który wydał decyzję]'],
    email: '', inbox: '', fallback: '', edelivery: '',
    note: 'Rejestr nie podaje, który urząd prowadził tę sprawę. Uzupełnij adresata – podpowie go znak sprawy.',
  },
};

const PARCELS_MAX = 5;
const SHORT = { wz: 'WZ', cp: 'CP', ws: 'sprawa', pb: 'pozwolenie na budowę', zg: 'zgłoszenie' };

function parcelsLine(parcels) {
  const list = (Array.isArray(parcels) ? parcels : []).filter((p) => p?.number);
  if (!list.length) return null;
  const one = (p) => `${p.partial ? 'cz. ' : ''}${p.number}${p.obreb ? ` (obręb ${p.obreb})` : ''}`;
  const shown = list.slice(0, PARCELS_MAX).map(one).join(', ');
  return `${list.length > 1 ? 'działki' : 'działka'} ewid. ${shown}${list.length > PARCELS_MAX ? ` i ${list.length - PARCELS_MAX} innych` : ''}`;
}

/** "nr X z dnia 16 września 2026" (each part only when known). */
function numberDate(r) {
  return [r.number ? `nr ${r.number}` : null, r.date ? `z dnia ${formatDate(r.date)}` : null].filter(Boolean).join(' ');
}

/** The numbered list of requested documents for one record. */
export function requestItems(kind, r) {
  const p = r.permit && typeof r.permit === 'object' ? r.permit : {};
  const nd = numberDate(r);
  switch (kind) {
    case 'wz':
    case 'cp': {
      const what = kind === 'wz' ? 'decyzji o warunkach zabudowy' : 'decyzji o ustaleniu lokalizacji inwestycji celu publicznego';
      return [
        `kopii ${what}${nd ? ` ${nd}` : ''} wraz ze wszystkimi załącznikami, w szczególności załącznikiem graficznym;`,
        kind === 'wz'
          ? 'kopii analizy funkcji oraz cech zabudowy i zagospodarowania terenu sporządzonej w tym postępowaniu, wraz z jej częścią graficzną;'
          : 'kopii analiz sporządzonych w tym postępowaniu (w tym analizy warunków i zasad zagospodarowania terenu), wraz z częścią graficzną;',
        'kopii wniosku o wydanie tej decyzji wraz z załącznikami.',
      ];
    }
    case 'ws':
      return [
        `kopii wniosku w sprawie${r.number ? ` o znaku ${r.number}` : ''} wraz z załącznikami, w szczególności mapą z oznaczeniem terenu inwestycji;`,
        'informacji o aktualnym etapie postępowania, w tym o dokonanych uzgodnieniach i wydanych postanowieniach;',
        r.procedure === 'cp'
          ? 'kopii projektu decyzji oraz analiz sporządzonych w tym postępowaniu – jeżeli zostały już sporządzone.'
          : 'kopii projektu decyzji oraz analizy funkcji oraz cech zabudowy i zagospodarowania terenu – jeżeli zostały już sporządzone.',
      ];
    case 'pb':
      return [
        `kopii decyzji${nd ? ` ${nd}` : ''}${p.case_sign && p.case_sign !== r.number ? ` (znak sprawy ${p.case_sign})` : ''} wraz z załącznikami;`,
        'kopii projektu zagospodarowania działki lub terenu oraz rysunków elewacji z projektu architektoniczno-budowlanego zatwierdzonego tą decyzją, '
          + 'a gdyby udostępnienie kopii nie było możliwe – umożliwienia wglądu w te dokumenty w siedzibie urzędu.',
      ];
    case 'zg':
      return [
        `kopii zgłoszenia${p.case_sign || r.number ? ` (znak sprawy ${p.case_sign || r.number})` : ''} wraz z załącznikami, w szczególności rysunkami lub szkicami;`,
        'informacji, czy organ wniósł sprzeciw od tego zgłoszenia albo wydał zaświadczenie o braku podstaw do jego wniesienia – i z jaką datą.',
      ];
    default:
      return [`kopii dokumentów w sprawie${r.number ? ` ${r.number}` : ''}.`];
  }
}

/**
 * The whole request for one record.
 * @returns {{ to: string, inbox: string, fallback: string, edelivery: string, note: string|null, addressee: string[],
 *   subject: string, body: string }}
 */
export function infoRequest(kind, r, { kindLabel } = {}) {
  const ad = ADDRESSEES[r.issuer] || ADDRESSEES.other;
  const p = r.permit && typeof r.permit === 'object' ? r.permit : {};
  const ref = [
    kindLabel ? `${kindLabel}${r.number ? ` ${r.number}` : ''}` : r.number,
    r.address?.display ? `adres: ${r.address.display}` : null,
    parcelsLine(r.parcels),
    p.register_id ? `nr w rejestrze GUNB ${p.register_id}` : null,
  ].filter(Boolean);
  const items = requestItems(kind, r);
  const body = [
    ...ad.lines,
    '',
    'WNIOSEK O UDOSTĘPNIENIE INFORMACJI PUBLICZNEJ',
    '',
    'Na podstawie art. 2 ust. 1 ustawy z dnia 6 września 2001 r. o dostępie do informacji publicznej, a w zakresie informacji o środowisku – '
      + 'także art. 8 ustawy z dnia 3 października 2008 r. o udostępnianiu informacji o środowisku i jego ochronie, udziale społeczeństwa '
      + 'w ochronie środowiska oraz o ocenach oddziaływania na środowisko, wnoszę o udostępnienie:',
    '',
    ...items.map((t, i) => `${i + 1}. ${t}`),
    '',
    `Dotyczy: ${ref.join('; ')}.`,
    '',
    'Proszę o przesłanie skanów dokumentów w formie elektronicznej na adres, z którego wysyłam ten wniosek. '
      + 'Nie wnoszę o udostępnienie danych osobowych osób fizycznych – mogą one zostać zanonimizowane.',
    '',
    'Z poważaniem',
    '[imię i nazwisko]',
  ].join('\n');
  const subject = `Wniosek o udostępnienie informacji publicznej – ${SHORT[kind] || 'sprawa'}${r.number ? ` ${r.number}` : ''}`;
  return { to: ad.email, inbox: ad.inbox, fallback: ad.fallback, edelivery: ad.edelivery, note: ad.note || null, addressee: ad.lines, subject, body };
}

/** mailto: link for the user's mail program (RFC 6068: every value percent-encoded, line breaks as CRLF). */
export function mailtoHref({ to, subject, body }) {
  const enc = (s) => encodeURIComponent(s).replace(/%0A/g, '%0D%0A');
  return `mailto:${to ? encodeURIComponent(to).replace(/%40/g, '@') : ''}?subject=${enc(subject)}&body=${enc(body)}`;
}
