/**
 * Tiny DOM helpers. Data from the spreadsheets is untrusted: it is only ever
 * inserted as text (textContent / attributes), never as HTML.
 */

/**
 * Create an element.
 * @param {string} tag
 * @param {object|null} [props] attributes; `class`, `dataset`, `style` (object), `on<Event>` handlers,
 *   `text` (textContent), boolean true → empty attribute, null/false → skipped
 * @param {...(Node|string|number|null|false|Array)} children
 */
export function h(tag, props, ...children) {
  const el = document.createElement(tag);
  if (props) {
    for (const [k, v] of Object.entries(props)) {
      if (v == null || v === false) continue;
      if (k === 'class') el.className = Array.isArray(v) ? v.filter(Boolean).join(' ') : v;
      else if (k === 'dataset') Object.assign(el.dataset, v);
      else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
      else if (k === 'text') el.textContent = v;
      else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
      else if (v === true) el.setAttribute(k, '');
      else el.setAttribute(k, String(v));
    }
  }
  append(el, children);
  return el;
}

/** Append children (nested arrays, strings, numbers; null/false skipped). */
export function append(el, children) {
  for (const c of children) {
    if (c == null || c === false) continue;
    if (Array.isArray(c)) append(el, c);
    else if (c instanceof Node) el.appendChild(c);
    else el.appendChild(document.createTextNode(String(c)));
  }
  return el;
}

/** Remove all children and append new ones. */
export function replaceChildren(el, ...children) {
  el.textContent = '';
  append(el, children);
  return el;
}

/** Visually hidden text for screen readers. */
export function srOnly(text) {
  return h('span', { class: 'sr-only' }, text);
}

/**
 * Render text with highlighted segments (from search.highlightSegments) as <mark> elements.
 * @param {{text: string, hit: boolean}[]} segments
 */
export function highlighted(segments) {
  return segments.map((s) => (s.hit ? h('mark', null, s.text) : document.createTextNode(s.text)));
}

const FOCUSABLE = [
  'a[href]', 'button:not([disabled])', 'input:not([disabled]):not([type="hidden"])', 'select:not([disabled])',
  'textarea:not([disabled])', 'summary', '[tabindex]:not([tabindex="-1"])',
].join(',');

/** Visible focusable descendants. */
export function focusables(root) {
  return [...root.querySelectorAll(FOCUSABLE)].filter((el) => !el.closest('[hidden],[inert]') && el.getClientRects().length > 0);
}

/**
 * Keep Tab focus inside `root` (for modal dialogs/sheets). Returns a release function.
 */
export function trapFocus(root) {
  const onKey = (e) => {
    if (e.key !== 'Tab') return;
    const items = focusables(root);
    if (!items.length) {
      // A trap whose dialog has gone away (hidden view, detached, closed drawer) must never swallow Tab for the
      // whole page: let the browser move the focus.
      if (!root.isConnected || root.closest('[hidden]') || !root.getClientRects().length
        || getComputedStyle(root).visibility === 'hidden') return;
      e.preventDefault();
      root.focus();
      return;
    }
    const first = items[0];
    const last = items[items.length - 1];
    if (e.shiftKey && (document.activeElement === first || !root.contains(document.activeElement))) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && (document.activeElement === last || !root.contains(document.activeElement))) {
      e.preventDefault();
      first.focus();
    }
  };
  document.addEventListener('keydown', onKey, true);
  return () => document.removeEventListener('keydown', onKey, true);
}

/** Is the event target a text-entry control (so global shortcuts must not fire)? */
export function isTyping(target) {
  if (!target || !(target instanceof Element)) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName;
  if (tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (tag === 'INPUT') {
    const type = (target.getAttribute('type') || 'text').toLowerCase();
    return !['checkbox', 'radio', 'button', 'submit', 'reset', 'range'].includes(type);
  }
  return false;
}

/** Debounce a function. */
export function debounce(fn, ms) {
  let t = null;
  const wrapped = (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
  wrapped.cancel = () => clearTimeout(t);
  wrapped.flush = (...args) => { clearTimeout(t); fn(...args); };
  return wrapped;
}

/** matchMedia helper. */
export function mq(query) {
  return window.matchMedia(query);
}

export const isMobile = () => mq('(max-width: 767.98px)').matches;
export const isDesktopWide = () => mq('(min-width: 1200px)').matches;
export const prefersReducedMotion = () => mq('(prefers-reduced-motion: reduce)').matches;

/** Download a string as a file. */
export function downloadText(text, filename, type = 'text/csv;charset=utf-8') {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const a = h('a', { href: url, download: filename, hidden: true });
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 1000);
}

/** Copy text to the clipboard with a legacy fallback. */
export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = h('textarea', { style: { position: 'fixed', top: '-1000px', opacity: '0' } });
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try { ok = document.execCommand('copy'); } catch { ok = false; }
    ta.remove();
    return ok;
  }
}

/**
 * Only allow http(s) and relative URLs from data into href attributes. The string is first normalised the way the
 * browser's URL parser reads it (tab/CR/LF removed anywhere, C0 controls and spaces stripped at both ends – so
 * "java\tscript:…" is a javascript: URL), then the scheme is decided on the parsed URL, never by a regex alone.
 * DOM-free at import time (unit-tested in node).
 */
export function safeUrl(url) {
  if (typeof url !== 'string' || !url) return null;
  const u = url.replace(/[\t\n\r]/g, '').replace(/^[\u0000-\u0020]+|[\u0000-\u0020]+$/g, '');
  if (!u || /^[\\/]{2}/.test(u)) return null; // protocol-relative ("//host", "\\host") – another origin
  let parsed;
  try {
    parsed = new URL(u, typeof document !== 'undefined' && document.baseURI ? document.baseURI : 'http://localhost/');
  } catch {
    return null;
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return null;
  return u;
}
