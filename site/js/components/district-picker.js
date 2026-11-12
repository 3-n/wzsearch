/**
 * District switcher (docs/plans/all-districts.md §1.1): the district is the scope of the whole page, not one more
 * facet. A button next to the brand names the current district and opens a native <dialog> (focus handling and
 * Escape come with it; on phones it is a full-screen sheet) listing the 18 districts and, at the bottom, "Cała
 * Warszawa" (the planning records of every district – no permits; plan §1.3). Picking one reloads the page on the same view with `dz=<slug>` (filters that only make sense inside one district – street,
 * neighbourhood, map area, "near me", file – are dropped).
 */
import { h } from '../dom.js';
import { icon } from '../icons.js';
import { formatNumber, plural } from '../format.js';
import { allDistricts, currentDistrict, districtTotals } from '../district.js';

const PLANNING = ['decyzja lub wszczęcie', 'decyzje lub wszczęcia', 'decyzji lub wszczęć'];

/**
 * Mount the switcher into `slot` (an element in the top bar).
 * @param {HTMLElement} slot
 * @param {{hrefFor: (slug: string) => string, city?: object|null}} opts hash of the current view in another
 *   district; `city`: districts.json's "Cała Warszawa" entry (no row without it)
 */
export function mountDistrictPicker(slot, { hrefFor, city = null }) {
  const current = currentDistrict();
  const list = allDistricts();
  if (!slot || !list.length) return null;

  const items = list.map((d) => {
    const { planning, permits } = districtTotals(d);
    const isCurrent = d.slug === current.slug;
    const meta = d.available
      ? [planning ? plural(planning, PLANNING) : null, permits ? `${formatNumber(permits)} pozw. i zgł.` : null].filter(Boolean).join(' · ')
      : 'dane w przygotowaniu';
    return h('li', { class: 'district-list__item' },
      h('a', {
        class: ['district-list__link', isCurrent && 'is-current', d.status !== 'enabled' && 'is-partial'],
        href: hrefFor(d.slug),
        'aria-current': isCurrent ? 'true' : null,
        onClick: (e) => pick(e, d.slug),
      },
      h('span', { class: 'district-list__name' }, d.name),
      h('span', { class: 'district-list__meta' }, meta),
      d.status !== 'enabled' ? h('span', { class: 'district-list__note' }, 'Listy urzędu dzielnicy w przygotowaniu') : null));
  });

  if (city) {
    const { planning } = districtTotals(city);
    const isCurrent = city.slug === current.slug;
    items.push(h('li', { class: 'district-list__item district-list__item--city' },
      h('a', {
        class: ['district-list__link', isCurrent && 'is-current'],
        href: hrefFor(city.slug),
        'aria-current': isCurrent ? 'true' : null,
        onClick: (e) => pick(e, city.slug),
      },
      h('span', { class: 'district-list__name' }, city.name),
      h('span', { class: 'district-list__meta' }, planning ? plural(planning, PLANNING) : ''),
      h('span', { class: 'district-list__note' }, 'Wszystkie dzielnice naraz – bez pozwoleń na budowę; wpis otwiera się w swojej dzielnicy'))));
  }

  const titleId = 'district-dialog-title';
  const dialog = h('dialog', { class: 'district-dialog', 'aria-labelledby': titleId },
    h('div', { class: 'district-dialog__head' },
      h('h2', { class: 'district-dialog__title', id: titleId }, 'Wybierz dzielnicę'),
      h('button', { type: 'button', class: 'btn btn--icon btn--ghost', 'aria-label': 'Zamknij', onClick: () => dialog.close() },
        icon('x', { size: 18 }))),
    h('p', { class: 'district-dialog__lead muted small' },
      'Każda dzielnica ma własne zestawienia decyzji WZ i celu publicznego. Pozwolenia na budowę (GUNB) i sprawy ',
      'Biura Architektury są dostępne dla wszystkich dzielnic.'),
    h('ul', { class: 'district-list' }, items));
  dialog.addEventListener('click', (e) => { if (e.target === dialog) dialog.close(); });   // backdrop click

  const button = h('button', {
    type: 'button', class: 'district-switch', 'aria-haspopup': 'dialog',
    title: 'Zmień dzielnicę',
    onClick: () => {
      dialog.showModal();
      dialog.querySelector('.is-current')?.focus();
    },
  },
  icon('pin', { size: 15, class: 'district-switch__icon' }),
  h('span', { class: 'district-switch__name' }, current.name),
  h('span', { class: 'sr-only' }, ' – zmień dzielnicę'),
  h('span', { class: 'district-switch__caret', 'aria-hidden': 'true' }, '▾'));

  function pick(e, slug) {
    if (e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;   // new tab/window: let the link work
    e.preventDefault();
    dialog.close();
    if (slug === current.slug) return;
    // A new history entry (Back returns to the previous district), then a fresh page for the new data shard.
    window.history.pushState(null, '', `${window.location.pathname}${window.location.search}${hrefFor(slug)}`);
    window.location.reload();
  }

  slot.replaceChildren(button, dialog);
  slot.hidden = false;
  return { button, dialog };
}
