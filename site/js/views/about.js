/**
 * About view (#/o-projekcie): glossary, how the data is produced, limitations, downloads,
 * unofficial disclaimer, licences/attribution, repository links (from config.js).
 */
import { h, replaceChildren, safeUrl, copyText, prefersReducedMotion } from '../dom.js';
import { icon, kindGlyph } from '../icons.js';
import { exists, datasetOf } from '../data.js';
import { formatDateTime, formatNumber } from '../format.js';
import { REPO_URL, ISSUES_URL, CONTACT_EMAIL, SOURCE_INDEX_URL, BAIPP_URL } from '../config.js';
import { UNOFFICIAL, LICENCE_URLS } from '../copy.js';
import { toast } from '../components/toast.js';

/** The "/" → search shortcut can be switched off here (WCAG 2.1.4); per-viewer setting, localStorage best effort. */
const SLASH_KEY = 'wz:slash';
export function slashShortcutEnabled() {
  try { return window.localStorage.getItem(SLASH_KEY) !== '0'; } catch { return true; }
}
function setSlashShortcut(on) {
  try { window.localStorage.setItem(SLASH_KEY, on ? '1' : '0'); } catch { /* private mode – the default stays */ }
}

function ext(href, label) {
  const url = safeUrl(href);
  if (!url) return label;
  return h('a', { class: 'link', href: url, target: '_blank', rel: 'noopener noreferrer' }, label, h('span', { class: 'sr-only' }, ' (nowa karta)'));
}

const DOWNLOADS = [
  { path: 'data/records.json', label: 'Decyzje WZ, CP i wszczęcia (JSON)', desc: 'Pełne dane z dzielnicy i z BAiPP: pola znormalizowane, lokalizacja, powiązania i surowe wiersze źródłowe.', iconName: 'code' },
  { path: 'data/records.csv', label: 'Decyzje WZ, CP i wszczęcia (CSV)', desc: 'Tabela do Excela / arkusza: UTF-8, separator średnik.', iconName: 'table' },
  { path: 'data/permits.json', label: 'Pozwolenia na budowę i zgłoszenia (JSON)', desc: 'Sprawy z rejestru GUNB RWDZ dla Pragi-Południe (od 2016 r.), w tym samym formacie co pozostałe wpisy.', iconName: 'code' },
  { path: 'data/permits.csv', label: 'Pozwolenia na budowę i zgłoszenia (CSV)', desc: 'Te same kolumny co tabela decyzji; licencja danych źródłowych CC0 1.0.', iconName: 'table' },
  { path: 'data/sources.json', label: 'Wykaz źródeł (JSON)', desc: 'Strony, pliki i wersje plików, liczby pozycji, sumy kontrolne – dla wszystkich trzech źródeł.', iconName: 'sheet' },
  { path: 'data/parcels.geojson', label: 'Geometrie działek (GeoJSON)', desc: 'Obrysy działek z ewidencji (GUGiK ULDK), EPSG:4326.', iconName: 'map' },
  { path: 'data/parcels-permits.geojson', label: 'Geometrie działek z pozwoleń (GeoJSON)', desc: 'Działki występujące tylko w pozwoleniach i zgłoszeniach.', iconName: 'map' },
  {
    path: 'feed.xml', label: 'Kanał nowych wpisów (RSS/Atom)', iconName: 'inbox', feed: true,
    desc: 'Wklej ten adres do czytnika RSS (np. Feedly, Inoreader, Thunderbird), aby dostawać nowe decyzje WZ, CP i wszczęcia z całej dzielnicy (bez pozwoleń na budowę).',
  },
];

function licenceLink(name) {
  const url = name ? LICENCE_URLS[name] : null;
  return url ? ext(url, name) : name;
}

/**
 * @param {HTMLElement} host
 * @param {object} index
 */
export function renderAbout(host, index) {
  const kinds = index.dicts.kinds || {};
  const k = (code) => kinds[code]?.label || code;
  const dlList = h('ul', { class: 'downloads' }, DOWNLOADS.map((d) => h('li', { class: 'download is-checking', 'data-path': d.path },
    h('span', { class: 'download__icon' }, icon(d.iconName, { size: 20 })),
    h('div', { class: 'download__main' }, h('p', { class: 'download__label' }, d.label), h('p', { class: 'download__desc' }, d.desc)),
    h('span', { class: 'download__action' }, h('span', { class: 'muted small' }, 'sprawdzanie…')))));

  // Probe optional downloads; show a link only when the file exists.
  for (const li of dlList.children) {
    const path = li.dataset.path;
    exists(path).then((ok) => {
      li.classList.remove('is-checking');
      const action = li.querySelector('.download__action');
      if (ok) {
        const d = DOWNLOADS.find((x) => x.path === path);
        // The feed is for a reader, not for the browser tab (raw XML): copy its address; preview in a new tab.
        replaceChildren(action, d?.feed
          ? [h('button', {
            type: 'button', class: 'btn btn--secondary btn--sm',
            onClick: async () => {
              const copied = await copyText(new URL(path, window.location.href).href);
              toast(copied ? 'Skopiowano adres kanału.' : 'Nie udało się skopiować adresu.', { kind: copied ? 'success' : 'error' });
            },
          }, icon('link', { size: 15 }), 'Kopiuj adres kanału'),
          h('a', { class: 'btn btn--ghost btn--sm', href: path, target: '_blank', rel: 'noopener noreferrer', type: 'application/atom+xml' },
            icon('external', { size: 15 }), 'Podgląd', h('span', { class: 'sr-only' }, ' (nowa karta)'))]
          : h('a', { class: 'btn btn--secondary btn--sm', href: path, download: '' }, icon('download', { size: 15 }), 'Pobierz'));
      } else {
        li.classList.add('is-missing');
        replaceChildren(action, h('span', { class: 'muted small' }, 'niedostępne w tej wersji'));
      }
    });
  }

  const repoLinks = [
    REPO_URL ? h('li', null, icon('code', { size: 16 }), ext(REPO_URL, 'Kod źródłowy projektu')) : null,
    ISSUES_URL ? h('li', null, icon('alert', { size: 16 }), ext(ISSUES_URL, 'Zgłoś błąd lub pomysł')) : null,
    CONTACT_EMAIL ? h('li', null, icon('inbox', { size: 16 }), h('a', { class: 'link', href: `mailto:${CONTACT_EMAIL}` }, CONTACT_EMAIL)) : null,
  ].filter(Boolean);

  const glossary = [
    {
      term: [kindGlyph('wz'), `${k('wz')} (WZ)`],
      body: [
        h('p', null, 'Wydawana, gdy dla danego terenu nie ma miejscowego planu zagospodarowania przestrzennego. Określa, co i w jakiej formie można na działce zbudować lub jak zmienić sposób użytkowania budynku – np. wysokość, linię zabudowy, funkcję.'),
        h('p', { class: 'em-box' }, icon('alert', { size: 16 }), h('span', null, h('strong', null, 'Decyzja WZ to nie jest pozwolenie na budowę. '), 'To dopiero pierwszy krok – inwestor musi jeszcze uzyskać pozwolenie na budowę (albo dokonać zgłoszenia). Decyzja nie przesądza też, że inwestycja w ogóle powstanie.')),
      ],
    },
    {
      term: [kindGlyph('cp'), `${k('cp')} (ULICP, „CP”)`],
      body: [h('p', null, 'Odpowiednik decyzji WZ dla inwestycji celu publicznego – służących wszystkim, np. sieci wodociągowych i ciepłowniczych, dróg, stacji transformatorowych, szkół czy parków. Wydawana również tylko tam, gdzie nie ma planu miejscowego.')],
    },
    {
      term: [kindGlyph('ws'), `${k('ws')}`],
      body: [h('p', null, 'Informacja, że do urzędu wpłynął wniosek o wydanie decyzji WZ lub lokalizacji celu publicznego i sprawa się rozpoczęła. Decyzji jeszcze nie ma – to wczesny sygnał, że w danym miejscu coś jest planowane. Strony postępowania (np. właściciele sąsiednich działek) mogą w nim uczestniczyć.')],
    },
    {
      term: [icon('map', { size: 16 }), 'Działka ewidencyjna i obręb'],
      body: [h('p', null, 'Działka jest wskazana numerem (np. „46/4”) i obrębem ewidencyjnym (np. „3-01-24”). Razem tworzą jednoznaczny identyfikator, po którym znajdziemy działkę w Geoportalu. „Część” oznacza, że inwestycja obejmuje tylko fragment działki.')],
    },
    {
      term: [icon('book', { size: 16 }), 'Plan miejscowy (MPZP)'],
      body: [h('p', null, 'Akt prawa miejscowego uchwalany przez Radę Miasta. Tam, gdzie obowiązuje plan, decyzji WZ się nie wydaje – zasady zabudowy wynikają wprost z planu.')],
    },
    {
      term: [kindGlyph('pb'), `${k('pb')}`],
      body: [
        h('p', null, 'Decyzja, po której inwestor może rozpocząć budowę, rozbudowę, nadbudowę albo rozbiórkę. Zwykle wydawana po decyzji WZ (tam, gdzie nie ma planu miejscowego) – to ostatni urzędowy krok przed wejściem koparek.'),
        h('p', null, 'Pozwolenia pochodzą z ogólnopolskiego rejestru GUNB (od 2016 r.). Są domyślnie ukryte – włączysz je w filtrze „Rodzaj”. Rejestr nie podaje, czy decyzja była pozytywna, i nie zawiera spraw w toku.'),
      ],
    },
    {
      term: [kindGlyph('zg'), `${k('zg')}`],
      body: [h('p', null, 'Prostsze roboty – np. dom jednorodzinny, którego oddziaływanie mieści się na działce, małe budynki czy przyłącza – wymagają tylko zgłoszenia. Jeśli urząd nie wniesie sprzeciwu, można budować. W rejestrze GUNB są tylko niektóre rodzaje zgłoszeń, więc ta lista jest niepełna.')],
    },
    {
      term: [icon('scale', { size: 16 }), 'Kto wydaje decyzje?'],
      body: [
        h('p', null, h('strong', null, 'Urząd Dzielnicy Praga-Południe'), ' (Wydział Architektury i Budownictwa) wydaje większość decyzji WZ, decyzji celu publicznego i pozwoleń na budowę z terenu dzielnicy.'),
        h('p', null, h('strong', null, 'Biuro Architektury i Planowania Przestrzennego'), ' Urzędu m.st. Warszawy prowadzi część spraw centralnie i publikuje je w osobnych, ogólnomiejskich zestawieniach – bierzemy z nich tylko wiersze z Pragi-Południe. Tylko te zestawienia podają rozstrzygnięcie (np. odmowę).'),
        h('p', null, h('strong', null, 'Wojewoda Mazowiecki'), ' wydaje pozwolenia m.in. dla sieci, linii kolejowych i dróg wyższej kategorii – na Pradze-Południe to pojedyncze sprawy.'),
      ],
    },
    {
      term: [icon('ban', { size: 16 }), 'Odmowa, umorzenie, przeniesienie'],
      body: [h('p', null, 'Nie każda decyzja jest zgodą. „Odmowa” oznacza, że urząd nie ustalił warunków zabudowy (nie można budować tego, o co wnioskowano), „umorzenie” – że postępowanie zakończono bez rozstrzygnięcia (np. wniosek wycofano), „przeniesienie” – że decyzję przepisano na innego inwestora. Te informacje podaje tylko Biuro Architektury; przy wpisach z dzielnicy rozstrzygnięcia nie znamy.')],
    },
  ];

  replaceChildren(host, h('div', { class: 'page page--about' },
    h('header', { class: 'page__head' },
      h('p', { class: 'eyebrow' }, 'O projekcie'),
      h('h1', { class: 'page__title', tabindex: '-1' }, 'Co się planuje na Pradze\u2011Południe?'),
      h('p', { class: 'lead' }, 'wzSearch zbiera w jednym miejscu wszystkie decyzje o warunkach zabudowy, decyzje o lokalizacji inwestycji celu publicznego i informacje o wszczętych postępowaniach z Pragi-Południe – z comiesięcznych zestawień Urzędu Dzielnicy i z ogólnomiejskich zestawień Biura Architektury – a na życzenie także pozwolenia na budowę i zgłoszenia z rejestru GUNB. ',
        'Możesz je przeszukiwać, filtrować, oglądać na mapie i pobierać – a przy każdym wpisie jest link do oryginalnego pliku.'),
      h('p', { class: 'notice notice--unofficial' }, icon('info', { size: 18 }),
        h('span', null, h('strong', null, `${UNOFFICIAL}. `), 'Projekt obywatelski, niezwiązany z Urzędem m.st. Warszawy. Wiążące są wyłącznie dokumenty urzędowe – ',
          ext(index.meta.sourceIndexUrl || SOURCE_INDEX_URL, 'oryginalny wykaz na stronie urzędu'), '.'))),

    h('nav', { class: 'toc', 'aria-label': 'Spis treści' }, h('ul', null,
      [['about-glossary', 'Słowniczek'], ['about-sources', 'Źródła'], ['about-how', 'Jak powstają dane'], ['about-limits', 'Ograniczenia'], ['about-download', 'Pobierz dane'], ['about-licences', 'Licencje'], ['about-privacy', 'Prywatność'], ['about-keys', 'Klawiatura']]
        .map(([id, label]) => h('li', null, h('button', { type: 'button', class: 'toc__link', onClick: () => jumpTo(id) }, label))))),

    h('section', { class: 'prose', id: 'about-glossary', 'aria-labelledby': 'h-glossary' },
      h('h2', { id: 'h-glossary' }, 'Słowniczek'),
      h('dl', { class: 'glossary' }, glossary.map((g) => h('div', { class: 'glossary__item' },
        h('dt', null, g.term), h('dd', null, g.body))))),

    h('section', { class: 'prose', id: 'about-sources', 'aria-labelledby': 'h-sources' },
      h('h2', { id: 'h-sources' }, 'Trzy źródła danych'),
      h('ul', { class: 'sources-list' }, sourceItems(index)),
      h('p', null, 'Pełny wykaz stron i plików, z liczbami pozycji i wersjami plików, jest na stronie ', h('a', { class: 'link', href: '#/zrodla' }, 'Źródła danych'), '.')),

    h('section', { class: 'prose', id: 'about-how', 'aria-labelledby': 'h-how' },
      h('h2', { id: 'h-how' }, 'Skąd są dane i jak powstają'),
      h('ol', { class: 'steps' },
        h('li', null, h('span', { class: 'steps__no' }, '1'), h('div', null, h('h3', null, 'Pobranie'), h('p', null, 'Automat odwiedza wykazy Urzędu Dzielnicy i Biura Architektury, pobiera wszystkie podlinkowane pliki Excel oraz paczki rejestru GUNB. Kopia każdego pliku (a z rejestru GUNB – wyciąg dla Pragi-Południe) jest archiwizowana.'))),
        h('li', null, h('span', { class: 'steps__no' }, '2'), h('div', null, h('h3', null, 'Odczyt'), h('p', null, 'Pliki mają kilka różnych układów kolumn (zmieniały się w latach 2020–2026). Kolumny rozpoznajemy po nagłówkach, a każdy wiersz zachowujemy także w postaci surowej – zobaczysz go w szczegółach wpisu jako „Dane w źródle”.'))),
        h('li', null, h('span', { class: 'steps__no' }, '3'), h('div', null, h('h3', null, 'Lokalizacja'), h('p', null, 'Numery działek i obręby wyszukujemy w usłudze ULDK (GUGiK). Gdy działki nie ma, próbujemy adresu (usługa UUG GUGiK), a w ostateczności samej ulicy – wtedy punkt na mapie jest przybliżony i oznaczony pustym znacznikiem.'))),
        h('li', null, h('span', { class: 'steps__no' }, '4'), h('div', null, h('h3', null, 'Publikacja'), h('p', null, 'Wynik to zwykła strona internetowa – bez własnego serwera, ciasteczek i analityki. ',
          index.meta.generatedAt ? `Ostatnia aktualizacja danych: ${formatDateTime(index.meta.generatedAt)}. ` : '',
          // Planning records come from the Excel files; the GUNB register files are counted with the permits.
          `W bazie jest ${formatNumber(index.meta.count)} decyzji i wszczęć z ${formatNumber(index.files.filter((f) => datasetOf(f, index.pagesById) !== 'rwdz').length)} plików Excel`,
          index.countsByKind.pb || index.countsByKind.zg ? ` oraz ${formatNumber((index.countsByKind.pb || 0) + (index.countsByKind.zg || 0))} pozwoleń i zgłoszeń z rejestru GUNB.` : '.'))))),

    h('section', { class: 'prose', id: 'about-limits', 'aria-labelledby': 'h-limits' },
      h('h2', { id: 'h-limits' }, 'Ograniczenia – zawsze sprawdź w źródle'),
      h('ul', { class: 'limits' },
        h('li', null, h('strong', null, 'Lokalizacje bywają przybliżone. '), 'Część wpisów ma tylko nazwę ulicy albo działki, które od czasu decyzji podzielono lub scalono (ewidencja zna tylko obecne działki).'),
        h('li', null, h('strong', null, 'Dane osobowe są ukryte. '), 'Urząd zwykle pisze „osoba fizyczna”, ale w kilku starszych plikach pojawiają się imiona i nazwiska – w wyszukiwarce zastępujemy je napisem „osoba fizyczna (dane usunięte)”. Nazwy firm i instytucji zostają.'),
        h('li', null, h('strong', null, 'Możliwe błędy odczytu. '), 'Pliki są przygotowywane ręcznie i zawierają literówki, scalone komórki czy różne formaty dat. Wpisy z wykrytymi problemami mają sekcję „Uwagi do danych”.'),
        h('li', null, h('strong', null, 'Typy inwestycji są nadawane automatycznie '), 'na podstawie słów w opisie – traktuj je jako pomoc w filtrowaniu, nie klasyfikację urzędową.'),
        h('li', null, h('strong', null, 'Rejestr pozwoleń GUNB ma swoje luki. '), 'Zawiera sprawy od 2016 r., tylko decyzje pierwszej instancji i tylko sprawy zakończone decyzją; nie mówi, czy decyzja była pozytywna. Zgłoszenia obejmują jedynie część rodzajów robót. Brak w nim inwestycji na terenach zamkniętych (np. kolejowych, wojskowych).'),
        h('li', null, h('strong', null, 'Powiązanie WZ z pozwoleniem jest przybliżone. '), 'Łączymy wpisy, które dotyczą tej samej działki lub adresu. Na dużych działkach (np. spółdzielczych) bywa wiele niezależnych spraw – sprawdź opis i numer sprawy.'),
        h('li', null, h('strong', null, 'Nie ma tu decyzji z innych dzielnic. '), 'Z ogólnomiejskich zestawień Biura Architektury bierzemy tylko wiersze opisane jako Praga-Południe; nieliczne błędy opisu w źródle oznaczamy uwagą przy wpisie.'))),

    h('section', { class: 'prose', id: 'about-download', 'aria-labelledby': 'h-download' },
      h('h2', { id: 'h-download' }, 'Pobierz dane'),
      h('p', null, 'Dane możesz swobodnie wykorzystywać – podaj źródło (Urząd Dzielnicy Praga-Południe, Urząd m.st. Warszawy, GUNB) i pamiętaj o ograniczeniach opisanych wyżej. ',
        'Bieżące wyniki wyszukiwania pobierzesz przyciskiem „CSV” na stronie ', h('a', { class: 'link', href: '#/' }, 'Przeglądaj'), '.'),
      dlList,
      h('p', { class: 'muted small' }, 'Pliki CSV: kodowanie UTF-8 ze znacznikiem BOM, separator „;” (średnik), przecinek dziesiętny we współrzędnych, wiele wartości w jednej komórce rozdzielone „ | ”. Excel w polskiej wersji otwiera je poprawnie dwuklikiem.')),

    h('section', { class: 'prose', id: 'about-licences', 'aria-labelledby': 'h-lic' },
      h('h2', { id: 'h-lic' }, 'Licencje i atrybucja'),
      h('ul', { class: 'credits' },
        h('li', null, h('strong', null, 'Dane źródłowe: '), 'Urząd Dzielnicy Praga-Południe m.st. Warszawy – informacja publiczna, ', ext(index.meta.sourceIndexUrl || SOURCE_INDEX_URL, 'wykaz publikacji'), '.'),
        h('li', null, h('strong', null, 'Zestawienia Biura Architektury i Planowania Przestrzennego: '), 'Urząd m.st. Warszawy – informacja publiczna, ', ext(index.dicts.datasets?.baipp?.url || BAIPP_URL, 'architektura.um.warszawa.pl'), '.'),
        h('li', null, h('strong', null, 'Rejestr wniosków, decyzji i zgłoszeń (RWDZ): '), 'Główny Urząd Nadzoru Budowlanego, licencja ', licenceLink(index.dicts.datasets?.rwdz?.licence || 'CC0 1.0'),
          ' (', ext('https://dane.gov.pl/pl/dataset/3467', 'dane.gov.pl'), ').'),
        h('li', null, h('strong', null, 'Mapa podkładowa: '), '© ', ext('https://www.openstreetmap.org/copyright', 'autorzy OpenStreetMap'), ' (dane ODbL, kafelki OpenStreetMap Foundation).'),
        h('li', null, h('strong', null, 'Ortofotomapa, granice działek, geometrie działek i adresy: '), '© ', ext('https://www.geoportal.gov.pl', 'Główny Urząd Geodezji i Kartografii'),
          ' (usługi WMS ORTO, KIEG, ULDK i ', ext('https://services.gugik.gov.pl/uug/', 'UUG'), ').'),
        h('li', { class: 'credit-areas', hidden: true }, h('strong', null, 'Granice osiedli: '), h('span', { class: 'credit-areas__text' })),
        h('li', null, h('strong', null, 'Biblioteki: '), ext('https://leafletjs.com', 'Leaflet'), ' (BSD-2-Clause), ', ext('https://github.com/Leaflet/Leaflet.markercluster', 'Leaflet.markercluster'), ' (MIT).'))),

    h('section', { class: 'prose', id: 'about-privacy', 'aria-labelledby': 'h-privacy' },
      h('h2', { id: 'h-privacy' }, 'Prywatność'),
      h('p', null, 'Strona nie używa ciasteczek ani narzędzi analitycznych. Funkcja „W pobliżu mnie” korzysta z lokalizacji tylko w Twojej przeglądarce – do adresu strony (żeby link dało się udostępnić) trafia punkt zaokrąglony do ok. 100 m, a nie Twoje dokładne położenie.'),
      h('p', null, 'Podkład mapy pobierany jest z serwerów OpenStreetMap Foundation, a po włączeniu ortofotomapy lub granic działek – z serwerów GUGiK; serwery te widzą adres IP Twojej przeglądarki. Kilka ustawień (np. ukryte podpowiedzi) zapamiętuje tylko Twoja przeglądarka.'),
      h('p', null, 'Osoby fizyczne nie są wymieniane z nazwiska: urzędy piszą „osoba fizyczna”, GUNB nie publikuje takich inwestorów, a kilka nazwisk ze starszych plików usuwamy. Nie pokazujemy też nazwisk projektantów z rejestru GUNB.')),

    h('section', { class: 'prose', id: 'about-keys', 'aria-labelledby': 'h-keys' },
      h('h2', { id: 'h-keys', tabindex: '-1' }, 'Klawiatura'),
      h('ul', { class: 'limits' },
        h('li', null, h('kbd', null, '/'), ' – przejście do wyszukiwania (na liście wpisów).'),
        h('li', null, h('kbd', null, '←'), ' ', h('kbd', null, '→'), ' – poprzedni / następny wpis w otwartych szczegółach.'),
        h('li', null, h('kbd', null, 'Esc'), ' – zamyka szczegóły, filtry, podpowiedzi na mapie i wskazywanie punktu.'),
        h('li', null, 'Mapa: strzałki przesuwają, ', h('kbd', null, '+'), ' ', h('kbd', null, '−'), ' przybliżają, ', h('kbd', null, 'Enter'), ' otwiera wpis lub grupę.')),
      h('label', { class: 'opt__label about-switch' },
        h('input', {
          type: 'checkbox', checked: slashShortcutEnabled() || null,
          onChange: (e) => { setSlashShortcut(e.target.checked); toast(e.target.checked ? 'Skrót „/” włączony.' : 'Skrót „/” wyłączony.'); },
        }),
        h('span', null, 'Skrót klawiszowy „/” (przejdź do wyszukiwania)'))),

    repoLinks.length ? h('section', { class: 'prose', 'aria-labelledby': 'h-repo' },
      h('h2', { id: 'h-repo' }, 'Kod i kontakt'), h('ul', { class: 'repo-links' }, repoLinks)) : null));
  return { title: 'O projekcie' };
}

/** Table of contents: jump to a section (instantly with reduced motion) and move the keyboard focus to its heading. */
function jumpTo(id) {
  const sec = document.getElementById(id);
  if (!sec) return;
  sec.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth', block: 'start' });
  const heading = sec.querySelector('h2');
  if (heading) {
    heading.setAttribute('tabindex', '-1');
    heading.focus({ preventScroll: true });
  }
}

/** One list item per dataset (records.json → datasets), with publisher, licence and link. */
function sourceItems(index) {
  const ds = index.dicts.datasets || {};
  const keys = Object.keys(ds);
  if (!keys.length) {
    return [h('li', null, h('strong', null, 'Urząd Dzielnicy Praga-Południe: '), 'comiesięczne zestawienia w plikach Excel – ', ext(index.meta.sourceIndexUrl || SOURCE_INDEX_URL, 'wykaz publikacji'), '.')];
  }
  return keys.map((key) => {
    const d = ds[key] || {};
    return h('li', { class: 'sources-list__item' },
      h('p', { class: 'sources-list__title' }, h('strong', null, d.label || key), d.short && d.short !== d.label ? [' ', h('span', { class: 'dbadge' }, d.short)] : null),
      d.description ? h('p', null, d.description) : null,
      h('p', { class: 'muted small' }, [d.publisher, d.licence ? `licencja ${d.licence}` : 'informacja publiczna'].filter(Boolean).join(' · '),
        d.url ? [' · ', ext(d.url, 'strona źródła')] : null,
        ' · ', h('a', { class: 'link', href: `#/zrodla/${encodeURIComponent(key)}` }, 'pliki i wersje')));
  });
}

/** Fill in area attribution once areas.geojson has loaded. */
export function setAreasAttribution(host, geo) {
  const li = host.querySelector('.credit-areas');
  if (!li || !geo) return;
  // Prefer the collection-level attribution; fall back to (deduplicated) per-feature sources.
  let text = typeof geo.attribution === 'string' ? geo.attribution : '';
  if (!text) {
    const sources = new Set();
    for (const f of geo.features || []) if (typeof f?.properties?.source === 'string') sources.add(f.properties.source);
    text = [...sources].slice(0, 3).join('; ');
  }
  if (!text) return;
  const target = li.querySelector('.credit-areas__text');
  if (/openstreetmap/i.test(text)) {
    // OpenStreetMap boundaries: say it in Polish, link the copyright and licence pages; the technical
    // source description of the file (English, from the pipeline) stays available as a tooltip.
    const licence = typeof geo.licence === 'string' ? geo.licence : 'ODbL';
    replaceChildren(target, '© ', ext(geo.copyright_url || 'https://www.openstreetmap.org/copyright', 'autorzy OpenStreetMap'),
      ' (licencja ', ext(geo.licence_url || 'https://opendatacommons.org/licenses/odbl/', licence), ')',
      ', pobrane przez Overpass API', geo.fetched_at ? ` (stan z ${formatDateTime(geo.fetched_at, { time: false })})` : '', '.');
    if (typeof geo.source === 'string') target.title = geo.source;
  } else {
    target.textContent = text + (typeof geo.source === 'string' ? ` – ${geo.source}` : '');
  }
  li.hidden = false;
}
