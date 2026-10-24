/**
 * Pure full-text search: Polish-diacritics-insensitive folding, tokenizing,
 * multi-word AND matching (exact substrings plus a light Polish inflection fallback),
 * relevance scoring and highlight ranges.
 * DOM-free; unit-tested in tests/js/search.test.mjs.
 */

const COMBINING = /[̀-ͯ]/g;
const SPECIAL = { ł: 'l', Ł: 'l', ß: 'ss', æ: 'ae', ø: 'o', đ: 'd' };

/** Fold one character (may return '' or more than one char). */
function foldChar(ch) {
  const special = SPECIAL[ch];
  if (special) return special;
  return ch.normalize('NFD').replace(COMBINING, '').toLowerCase();
}

/**
 * Fold a string for comparison: lowercase, strip diacritics (ą→a, ł→l, ó→o …),
 * normalise typographic quotes/dashes and collapse whitespace into single spaces.
 */
export function fold(str) {
  return foldWithMap(str).folded;
}

/**
 * Fold a string and keep a map from each folded index to the original index,
 * so match positions in folded text can be projected back for highlighting.
 * @returns {{folded: string, map: number[]}} map has length folded.length + 1
 */
export function foldWithMap(str) {
  const s = str == null ? '' : String(str);
  let folded = '';
  const map = [];
  let prevSpace = false;
  for (let i = 0; i < s.length; i += 1) {
    let ch = s[i];
    if (/\s/.test(ch)) {
      if (prevSpace) continue;
      prevSpace = true;
      folded += ' ';
      map.push(i);
      continue;
    }
    prevSpace = false;
    if (ch === '„' || ch === '”' || ch === '“' || ch === '«' || ch === '»') ch = '"';
    else if (ch === '–' || ch === '—' || ch === '‑') ch = '-';
    const f = foldChar(ch);
    for (let k = 0; k < f.length; k += 1) {
      folded += f[k];
      map.push(i);
    }
  }
  map.push(s.length);
  return { folded, map };
}

/**
 * Tokens that carry no meaning for search: street prefixes ("ul. Grochowska", "ulicy Grochowskiej"),
 * parcel designators ("dz. 46/4 obr. 3-01-24" – the way the detail panel prints a parcel, "działka 46/4") and
 * short prepositions/conjunctions ("w Grochowie", "na Saskiej Kępie") that would match almost every record.
 */
const STOPWORDS = new Set(['ul', 'ulica', 'ulicy', 'al', 'aleja', 'aleje', 'alei',
  'dz', 'dzialka', 'dzialki', 'dzialek', 'dzialce', 'obr', 'obreb', 'obrebie', 'obrebu', 'nr',
  'w', 'we', 'na', 'i', 'oraz', 'z', 'ze', 'o', 'u', 'do', 'od', 'po', 'przy', 'pod', 'nad', 'za']);

/**
 * Inflectional endings (folded, no diacritics) removed by stem(), longest first.
 * Deliberately small: enough for the declension seen in the source texts
 * ("budynku mieszkalnego", "stacji bazowej", "w Grochowie", "na Saskiej Kępie").
 */
const ENDINGS = ['iego', 'iemu', 'ach', 'ami', 'ego', 'emu', 'iej', 'ich', 'ych', 'imi', 'ymi', 'iem',
  'ej', 'em', 'ia', 'ie', 'ii', 'iu', 'im', 'ym', 'a', 'e', 'i', 'o', 'u', 'y'];
const LETTERS_ONLY = /^\p{L}+$/u;
const WORD = /\p{L}+/gu;
/** Minimal length of a token for the inflection fallback, and of a stem for prefix matching. */
const MIN_STEM_TOKEN = 4;
const MIN_PREFIX_STEM = 5;

/**
 * Very light Polish stemmer for ONE folded word: strips one inflectional ending (keeping ≥ 3 letters)
 * and drops the mobile "e" of "-ek" ("budynek" → "budynk" = "budynku" → "budynk").
 * Words with digits or punctuation, and words shorter than 4 letters, are returned unchanged.
 * @param {string} word folded word
 * @returns {string}
 */
export function stem(word) {
  const w = String(word || '');
  if (w.length < MIN_STEM_TOKEN || !LETTERS_ONLY.test(w)) return w;
  for (const end of ENDINGS) {
    if (w.endsWith(end) && w.length - end.length >= 3) return w.slice(0, -end.length);
  }
  if (w.endsWith('ek') && w.length >= 5) return `${w.slice(0, -2)}k`;
  return w;
}

/** Can this (folded) token use the inflection fallback? */
function stemmable(token) {
  return token.length >= MIN_STEM_TOKEN && LETTERS_ONLY.test(token);
}

/** Does a word's stem match a token's stem (equal, or a prefix when the token stem is long enough)? */
function stemMatches(wordStem, tokenStem) {
  return wordStem === tokenStem || (tokenStem.length >= MIN_PREFIX_STEM && wordStem.startsWith(tokenStem));
}

/** Unique stems of the words in a folded text. */
function stemsOf(folded) {
  const out = new Set();
  for (const m of folded.matchAll(WORD)) out.add(stem(m[0]));
  return [...out];
}

/**
 * Split a user query into folded tokens (AND semantics).
 * Keeps inner punctuation (46/4, 15/PPD/WZ/2026, 6730.29.2026) but trims it at the edges.
 * @param {string} query
 * @returns {string[]}
 */
export function tokenize(query) {
  const f = fold(query);
  const seen = new Set();
  const out = [];
  for (const raw of f.split(' ')) {
    const t = raw.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, '');
    if (!t || STOPWORDS.has(t) || seen.has(t)) continue;
    seen.add(t);
    out.push(t);
  }
  return out;
}

const DIGIT = /\d/;
const WORDCHAR = /[\p{L}\p{N}]/u;

/**
 * Find occurrences of `token` in already-folded `text`.
 * Numeric tokens ("5", "46/4") must start at a non-digit boundary so that
 * "5" matches "Domeyki 5" / "5A" but not "15" or "2025".
 * @returns {number[]} start offsets
 */
export function findToken(text, token) {
  const out = [];
  if (!token || !text) return out;
  const numeric = DIGIT.test(token[0]);
  let from = 0;
  while (from <= text.length - token.length) {
    const i = text.indexOf(token, from);
    if (i < 0) break;
    if (!numeric || i === 0 || !DIGIT.test(text[i - 1])) out.push(i);
    from = i + 1;
  }
  return out;
}

/** Field weights for relevance scoring. */
export const FIELD_WEIGHTS = {
  number: 10,
  register: 9,
  address: 8,
  street: 8,
  parcels: 6,
  applicant: 5,
  area: 4,
  tags: 3,
  investment: 2,
  kind: 1,
};

/**
 * Prepare a search document for a record: folded text per field.
 * @param {object} rec Record (DATA_MODEL.md)
 * @param {{tags?: object, areas?: object, kinds?: object, outcomes?: object, datasets?: object, scopes?: object}} dicts
 *   dictionaries from records.json (data.js buildIndex)
 * @returns {{fields: {key: string, text: string, folded: string, weight: number}[], all: string}}
 */
export function buildSearchDoc(rec, dicts = {}) {
  const parts = [];
  const add = (key, text) => {
    if (text == null || text === '') return;
    const t = String(text);
    const folded = fold(t);
    parts.push({ key, text: t, folded, stems: stemsOf(folded), weight: FIELD_WEIGHTS[key] || 1 });
  };
  add('number', rec.number);
  // Building permits: GUNB register number and the office case sign are searchable like decision numbers.
  const permit = rec.permit && typeof rec.permit === 'object' ? rec.permit : {};
  add('register', [permit.register_id, permit.case_sign].filter(Boolean).join(' ; '));
  const addr = rec.address || {};
  add('address', addr.display);
  // Normalised street names (nominative, typo-fixed) of every street the address mentions.
  const streets = [addr.street, ...(Array.isArray(addr.parts) ? addr.parts.map((p) => p && p.street) : [])]
    .filter((x, i, arr) => x && arr.indexOf(x) === i);
  add('street', streets.join(' ; '));
  add('applicant', rec.applicant);
  add('investment', rec.investment);
  // Number + obręb, and the cadastral id Geoportal shows ("146507_8.0605.25/12") for pasting.
  const parcels = (rec.parcels || []).map((p) => [p.number, p.obreb, p.id].filter(Boolean).join(' ')).join(' ; ');
  add('parcels', parcels || rec.parcels_raw);
  const tagLabels = (rec.tags || []).map((t) => dicts.tags?.[t]?.label || t).join(' ; ');
  add('tags', tagLabels);
  if (rec.area) add('area', dicts.areas?.[rec.area]?.label || rec.area);
  // Low-weight labels: "odmowa", "BAiPP", "rozbiórka" find records by outcome, dataset or scope of works.
  add('kind', [
    rec.outcome ? dicts.outcomes?.[rec.outcome]?.label : null,
    rec.dataset ? dicts.datasets?.[rec.dataset]?.short : null,
    permit.scope ? dicts.scopes?.[permit.scope]?.label : null,
  ].filter(Boolean).join(' ; '));
  return { fields: parts, all: parts.map((p) => p.folded).join(' \u0001 ') };
}

/**
 * Match a prepared document against tokens (all must match, in any field).
 * A token matches a field as a substring (diacritics-insensitive) or, for words, by inflection:
 * "stacja bazowa" finds "stacji bazowej", "budynek" finds "budynku" (see stem()).
 * @returns {number} relevance score, or 0 when the document does not match
 */
export function scoreDoc(doc, tokens) {
  if (!tokens.length) return 1;
  let score = 0;
  for (const tok of tokens) {
    const tokStem = stemmable(tok) ? stem(tok) : null;
    let best = 0;
    for (const f of doc.fields) {
      const hits = findToken(f.folded, tok);
      let s = 0;
      if (hits.length) {
        s = f.weight;
        const at = hits[0];
        if (at === 0 || !WORDCHAR.test(f.folded[at - 1])) s *= 1.5; // word-start match
        if (f.key === 'number' && f.folded === tok) s *= 2; // exact decision number / case sign
      } else if (tokStem && (f.stems || []).some((ws) => stemMatches(ws, tokStem))) {
        s = f.weight * 1.2; // another grammatical form of the word
      }
      if (s > best) best = s;
    }
    if (!best) return 0;
    score += best;
  }
  return score;
}

/**
 * Compute merged highlight ranges [start, end) in the ORIGINAL text for given tokens.
 * @param {string} text original text
 * @param {string[]} tokens folded tokens
 * @returns {[number, number][]}
 */
export function highlightRanges(text, tokens) {
  if (!text || !tokens || !tokens.length) return [];
  const { folded, map } = foldWithMap(text);
  const ranges = [];
  const project = (i, len) => {
    const start = map[i];
    const endIdx = i + len;
    const end = endIdx < map.length - 1 ? map[endIdx] : text.length;
    ranges.push([start, Math.max(end, start + 1)]);
  };
  for (const tok of tokens) {
    for (const i of findToken(folded, tok)) project(i, tok.length);
    if (!stemmable(tok)) continue;
    // Other grammatical forms of the word ("stacja" → "stacji"): highlight the whole word.
    const tokStem = stem(tok);
    for (const m of folded.matchAll(WORD)) {
      if (stemMatches(stem(m[0]), tokStem)) project(m.index, m[0].length);
    }
  }
  ranges.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const merged = [];
  for (const r of ranges) {
    const last = merged[merged.length - 1];
    if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1]);
    else merged.push([r[0], r[1]]);
  }
  return merged;
}

/**
 * Split text into segments for rendering highlights.
 * @returns {{text: string, hit: boolean}[]}
 */
export function highlightSegments(text, tokens) {
  const s = text == null ? '' : String(text);
  const ranges = highlightRanges(s, tokens);
  if (!ranges.length) return s ? [{ text: s, hit: false }] : [];
  const out = [];
  let pos = 0;
  for (const [a, b] of ranges) {
    if (a > pos) out.push({ text: s.slice(pos, a), hit: false });
    out.push({ text: s.slice(a, b), hit: true });
    pos = b;
  }
  if (pos < s.length) out.push({ text: s.slice(pos), hit: false });
  return out;
}

/**
 * A short excerpt of `text` around [start, end) for showing why a record matched, cut at word boundaries,
 * with "…" where text was dropped.
 * @param {string} text
 * @param {number} start
 * @param {number} end
 * @param {number} [radius] characters of context on each side
 * @returns {string}
 */
export function snippetAround(text, start, end, radius = 36) {
  const s = String(text ?? '');
  let a = Math.max(0, start - radius);
  let b = Math.min(s.length, end + radius);
  if (a > 0) {
    const sp = s.lastIndexOf(' ', a);
    a = sp >= 0 && a - sp <= 12 ? sp + 1 : a;
  }
  if (b < s.length) {
    const sp = s.indexOf(' ', b);
    b = sp >= 0 && sp - b <= 12 ? sp : b;
  }
  return `${a > 0 ? '…' : ''}${s.slice(a, b).trim()}${b < s.length ? '…' : ''}`;
}
