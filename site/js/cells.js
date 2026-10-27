/**
 * Source cells ("Dane w źródle") fetched on demand (pipeline/cells.py, docs/DATA_MODEL.md). The record files leave
 * out each source's `raw`; the cells sit in small bucket files, `<base><prefix><bb>.json`, where <bb> is FNV-1a of
 * the record id's UTF-8 bytes modulo the bucket count, in two hex digits. A bucket maps record id → one `raw` per
 * source (null where a source has none). Each bucket is requested once per page; a failed request may be retried.
 */

/** 32-bit FNV-1a of the UTF-8 bytes of `text` (the same as pipeline/cells.py). */
export function fnv1a32(text) {
  let h = 0x811c9dc5;
  for (const byte of new TextEncoder().encode(String(text))) {
    h = Math.imul(h ^ byte, 0x01000193) >>> 0;
  }
  return h;
}

export function bucketOf(id, buckets) {
  return fnv1a32(id) % buckets;
}

/** A record file's `cells` ({prefix, buckets}) when usable, else null (data without cell buckets). */
export function cellsSet(meta) {
  if (!meta || typeof meta !== 'object') return null;
  const { prefix, buckets } = meta;
  if (typeof prefix !== 'string' || !/^[a-z0-9_/-]{1,40}$/.test(prefix) || prefix.includes('..')) return null;
  if (!Number.isInteger(buckets) || buckets < 1 || buckets > 256) return null;
  return { prefix, buckets };
}

/** URL of the bucket that holds `id`. */
export function bucketUrl(base, set, id) {
  return `${base}${set.prefix}${bucketOf(id, set.buckets).toString(16).padStart(2, '0')}.json`;
}

const buckets = new Map();   // url → Promise<object>

/**
 * The cells of record `id`: an array with one `raw` per source (null entries where a source has none); null when
 * the bucket does not list the record. Rejects when the bucket cannot be fetched.
 */
export function loadCells(base, set, id, fetchImpl = (u) => fetch(u, { cache: 'no-cache' })) {
  const url = bucketUrl(base, set, id);
  if (!buckets.has(url)) {
    const p = Promise.resolve(fetchImpl(url)).then((res) => {
      if (!res.ok) throw new Error(`Serwer zwrócił błąd ${res.status} dla ${url}`);
      return res.json();
    });
    p.catch(() => buckets.delete(url));   // a later opening of the panel tries again
    buckets.set(url, p);
  }
  return buckets.get(url).then((doc) => {
    const raws = doc && Object.prototype.hasOwnProperty.call(doc, id) ? doc[id] : null;
    return Array.isArray(raws) ? raws : null;
  });
}
