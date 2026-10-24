/**
 * Toast notifications in a polite live region.
 */
import { h, append } from '../dom.js';
import { icon } from '../icons.js';

let region = null;

function ensureRegion() {
  if (region && document.body.contains(region)) return region;
  region = document.querySelector('body > .toasts')
    || document.body.appendChild(h('div', { class: 'toasts', role: 'status', 'aria-live': 'polite', 'aria-atomic': 'false' }));
  return region;
}

/**
 * Create the (empty) live region at boot: screen readers often miss a message inserted together with a new live
 * region, so the first toast must land in a region that already exists.
 */
export function initToasts() {
  ensureRegion();
}

/**
 * Show a short message.
 * @param {string} message
 * @param {{kind?: 'info'|'success'|'error', timeout?: number}} [opts]
 */
export function toast(message, { kind = 'info', timeout = 3200 } = {}) {
  const r = ensureRegion();
  const el = h('div', { class: `toast toast--${kind}` },
    icon(kind === 'success' ? 'check' : kind === 'error' ? 'alert' : 'info', { size: 18 }),
    h('span', null, message));
  append(r, [el]);
  requestAnimationFrame(() => el.classList.add('is-in'));
  setTimeout(() => {
    el.classList.remove('is-in');
    el.classList.add('is-out');
    setTimeout(() => el.remove(), 300);
  }, timeout);
}
