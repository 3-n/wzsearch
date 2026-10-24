/**
 * Plain-language UI copy that does not come from the data.
 * Kind codes (wz / cp / ws / pb / zg) are fixed by docs/DATA_MODEL.md; labels still come from records.json.
 * DOM-free (unit-tested in node).
 */
import { formatNumber, pluralForm } from './format.js';

/** One-line explanations shown in info tooltips and the detail panel. */
export const KIND_EXPLAINERS = {
  wz: 'Ustala, co i w jakiej formie można zbudować na działce, dla której nie ma planu miejscowego. To jeszcze nie jest pozwolenie na budowę.',
  cp: 'Ustala lokalizację inwestycji publicznej (np. sieci, drogi, parku, szkoły) na terenie bez planu miejscowego.',
  ws: 'Ktoś złożył wniosek o decyzję WZ lub o lokalizację celu publicznego. Sprawa jest w toku – decyzji jeszcze nie ma.',
  pb: 'Sprawa o pozwolenie na budowę (albo rozbiórkę) zakończona decyzją urzędu – zwykle pozwoleniem, po którym inwestor może zacząć budowę. Tam, gdzie nie ma planu miejscowego, poprzedza ją decyzja WZ.',
  zg: 'Prostsze roboty (np. dom jednorodzinny o niewielkim oddziaływaniu, przyłącza) zgłasza się zamiast prosić o pozwolenie. Rejestr GUNB obejmuje tylko część zgłoszeń.',
};

/** Fallback labels when records.json lacks a dictionary entry. */
export const KIND_FALLBACK = {
  wz: { label: 'Decyzja o warunkach zabudowy', short: 'WZ' },
  cp: { label: 'Decyzja o lokalizacji inwestycji celu publicznego', short: 'CP' },
  ws: { label: 'Wszczęte postępowanie', short: 'Wszczęcie' },
  pb: { label: 'Pozwolenie na budowę lub rozbiórkę', short: 'Pozwolenie' },
  zg: { label: 'Zgłoszenie budowy lub robót', short: 'Zgłoszenie' },
};

/** Short labels for the related-records mini timeline ("wszczęcie 03.2023 → WZ 09.2023 → pozwolenie na budowę 05.2024"). */
export const KIND_STEP = {
  wz: 'decyzja WZ', cp: 'decyzja CP', ws: 'wszczęcie', pb: 'pozwolenie na budowę', zg: 'zgłoszenie',
};
/**
 * Step label of a WZ/CP decision whose source states a negative outcome (BAiPP lists only): a refusal is not
 * "decyzja WZ" – the summary must not read as if building conditions were issued.
 */
export const OUTCOME_STEP = { refusal: 'odmowa', discontinued: 'umorzenie', transfer: 'przeniesienie', expiry: 'wygaśnięcie' };
/** Plural forms [one, few, many] of OUTCOME_STEP for counts ("w tym 1 odmowa, 2 umorzenia"). */
export const OUTCOME_PLURAL = {
  refusal: ['odmowa', 'odmowy', 'odmów'],
  discontinued: ['umorzenie', 'umorzenia', 'umorzeń'],
  transfer: ['przeniesienie', 'przeniesienia', 'przeniesień'],
  expiry: ['wygaśnięcie', 'wygaśnięcia', 'wygaśnięć'],
};

/** What an initiated proceeding asks for, in the accusative ("Wniosek o: decyzję o warunkach zabudowy (WZ)"). */
export const PROCEDURE_ACC = {
  wz: 'decyzję o warunkach zabudowy (WZ)',
  cp: 'decyzję o lokalizacji inwestycji celu publicznego (CP)',
};

/** A kind as the list shows it, plural ("Pozwolenia są ukryte na liście", "Pokaż pozwolenia na liście"). */
export const KIND_LIST_LABEL = { wz: 'decyzje WZ', cp: 'decyzje CP', ws: 'wszczęte postępowania', pb: 'pozwolenia', zg: 'zgłoszenia' };

/** Step label of a demolition permit (permit scope "rozbiorka", docs/DATA_MODEL.md). */
export const DEMOLITION_STEP = 'pozwolenie na rozbiórkę';

/** Plural forms [one, few, many] for counting related records per kind ("3 decyzje WZ", "5 wszczęć"). */
export const KIND_PLURAL = {
  wz: ['decyzja WZ', 'decyzje WZ', 'decyzji WZ'],
  cp: ['decyzja CP', 'decyzje CP', 'decyzji CP'],
  ws: ['wszczęcie', 'wszczęcia', 'wszczęć'],
  pb: ['pozwolenie', 'pozwolenia', 'pozwoleń'],
  zg: ['zgłoszenie', 'zgłoszenia', 'zgłoszeń'],
};

/** Promo / empty-state wording for switching on an opt-in kind, [one, few, many]. */
export const KIND_PROMO = {
  pb: ['pozwolenie na budowę', 'pozwolenia na budowę', 'pozwoleń na budowę'],
  zg: ['zgłoszenie', 'zgłoszenia', 'zgłoszeń'],
};

/**
 * Wording of the "show permits too" promo. Before permits.json is loaded only register TOTALS are known: next to an
 * active search they would read as matches, so the button then names no number ("Sprawdź też … dla tego
 * wyszukiwania"); without other filters the total says "łącznie". Once loaded, counts follow the filters.
 * @param {{loaded: boolean, filtered: boolean, main: 'pb'|'zg', pb: number, zg: number}} o
 * @returns {{lead: string, tail: string, count: string|null, note: string, more: string|null}}
 *   lead + tail = the button text (the count is glued to `tail`), `more` = the "with notifications" link (pb + zg)
 */
export function promoText({ loaded, filtered, main, pb = 0, zg = 0 }) {
  const n = main === 'pb' ? pb : zg;
  const what = main === 'pb' ? ['Pokaż też pozwolenia na ', 'budowę'] : ['Pokaż też zgłoszenia ', 'budowy'];
  const total = (x) => (loaded ? formatNumber(x) : `łącznie ${formatNumber(x)}`);
  const generic = 'Z rejestru GUNB, od 2016 r. – domyślnie ukryte.';
  const more = pb && zg ? `Razem ze zgłoszeniami (${total(zg)})` : null;
  if (!loaded && filtered) {
    return {
      lead: main === 'pb' ? 'Sprawdź też pozwolenia na budowę dla tego ' : 'Sprawdź też zgłoszenia budowy dla tego ',
      tail: 'wyszukiwania', count: null, note: generic, more,
    };
  }
  return {
    lead: what[0], tail: what[1], count: `(${total(n)})`,
    note: loaded && filtered ? `Pasujące do tych kryteriów: ${formatNumber(n)} ${pluralForm(n, KIND_PROMO[main])}.` : generic,
    more,
  };
}

/** What the record's date means, per kind. */
export const DATE_LABEL = {
  wz: 'Data decyzji', cp: 'Data decyzji', ws: 'Data wszczęcia', pb: 'Data decyzji', zg: 'Data zgłoszenia',
};
export const NUMBER_LABEL = {
  wz: 'Numer decyzji', cp: 'Numer decyzji', ws: 'Znak sprawy', pb: 'Numer decyzji', zg: 'Numer w urzędzie',
};

/** Outcome codes (docs/DATA_MODEL.md) that deserve a warning-style badge; labels come from records.json → outcomes. */
export const OUTCOME_EMPHASIS = { refusal: 'bad', discontinued: 'neutral', transfer: 'neutral', expiry: 'neutral', granted: 'good' };

export const APPLICANT_LABELS = {
  person: 'Osoba fizyczna',
  organization: 'Firma lub instytucja',
  unknown: 'Nieustalony',
};

/** Headings for tag groups (records.json tags[].group); unknown groups show their raw name. */
export const TAG_GROUP_LABELS = { funkcja: 'Co powstaje', roboty: 'Rodzaj robót' };

export const PRECISION = {
  parcel: { label: 'Lokalizacja według działki', short: 'działka', icon: 'target' },
  address: { label: 'Lokalizacja według adresu', short: 'adres', icon: 'approx' },
  street: { label: 'Lokalizacja przybliżona (ulica)', short: 'przybliżona', icon: 'approx' },
  conflict: { label: 'Lokalizacja niepewna – adres i działki się różnią', short: 'niepewna', icon: 'approx' },
  none: { label: 'Brak lokalizacji na mapie', short: 'brak', icon: 'pinOff' },
};

export const UNOFFICIAL = 'Serwis nieoficjalny – dane z publikacji Urzędu Dzielnicy Praga-Południe, Urzędu m.st. Warszawy i GUNB';

/** Licence names (as in the data) → licence page. */
export const LICENCE_URLS = {
  'CC0 1.0': 'https://creativecommons.org/publicdomain/zero/1.0/deed.pl',
  'CC0': 'https://creativecommons.org/publicdomain/zero/1.0/deed.pl',
};
