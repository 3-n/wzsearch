/**
 * Accessible autocomplete combobox (ARIA 1.2 "combobox with listbox popup", list autocomplete).
 * Keyboard: ↓/↑ move, Enter selects, Esc closes (or clears), Home/End inside the input as usual.
 */
import { h, replaceChildren } from '../dom.js';
import { icon } from '../icons.js';
import { formatNumber } from '../format.js';

let uid = 0;

/**
 * @param {{
 *   label: string, placeholder?: string, emptyText?: (q: string) => string,
 *   getOptions: (query: string) => {value: string, label: string, count?: number, disabled?: boolean}[],
 *   onSelect: (value: string, option: object) => void,
 * }} cfg
 */
export function createCombobox(cfg) {
  uid += 1;
  const base = `combo-${uid}`;
  const listId = `${base}-list`;
  const input = h('input', {
    id: `${base}-input`, class: 'input combo__input', type: 'text', role: 'combobox', autocomplete: 'off',
    spellcheck: 'false', 'aria-autocomplete': 'list', 'aria-expanded': 'false', 'aria-controls': listId,
    placeholder: cfg.placeholder || '',
  });
  const list = h('ul', { id: listId, class: 'combo__list', role: 'listbox', 'aria-label': cfg.label, hidden: true });
  const root = h('div', { class: 'combo' },
    h('label', { class: 'field-label sr-only', for: input.id }, cfg.label),
    h('div', { class: 'combo__field' }, icon('search', { size: 16, class: 'combo__icon' }), input),
    list);

  let options = [];
  let active = -1;
  let open = false;

  function setOpen(v) {
    open = v;
    list.hidden = !v;
    input.setAttribute('aria-expanded', String(v));
    if (!v) {
      active = -1;
      input.removeAttribute('aria-activedescendant');
    }
  }

  function render() {
    options = cfg.getOptions(input.value) || [];
    if (!options.length) {
      replaceChildren(list, h('li', { class: 'combo__empty', role: 'presentation' },
        cfg.emptyText ? cfg.emptyText(input.value) : 'Brak wyników'));
      active = -1;
      input.removeAttribute('aria-activedescendant');
      return;
    }
    if (active >= options.length) active = options.length - 1;
    replaceChildren(list, options.map((o, i) => h('li', {
      id: `${base}-opt-${i}`,
      class: ['combo__option', i === active && 'is-active', o.disabled && 'is-disabled'],
      role: 'option',
      'aria-selected': String(i === active),
      'aria-disabled': o.disabled ? 'true' : null,
      onMousedown: (e) => { e.preventDefault(); },
      onClick: () => choose(i),
    },
    h('span', { class: 'combo__label' }, o.label),
    o.count != null ? h('span', { class: 'count' }, formatNumber(o.count)) : null)));
    if (active >= 0) {
      input.setAttribute('aria-activedescendant', `${base}-opt-${active}`);
      list.children[active]?.scrollIntoView({ block: 'nearest' });
    } else {
      input.removeAttribute('aria-activedescendant');
    }
  }

  function choose(i) {
    const o = options[i];
    if (!o || o.disabled) return;
    input.value = '';
    setOpen(false);
    cfg.onSelect(o.value, o);
  }

  function move(delta) {
    if (!open) { setOpen(true); render(); }
    if (!options.length) return;
    active = active < 0 ? (delta > 0 ? 0 : options.length - 1) : (active + delta + options.length) % options.length;
    render();
  }

  input.addEventListener('input', () => {
    active = input.value ? 0 : -1;
    setOpen(true);
    render();
  });
  input.addEventListener('focus', () => { setOpen(true); render(); });
  input.addEventListener('blur', () => setTimeout(() => setOpen(false), 120));
  input.addEventListener('keydown', (e) => {
    switch (e.key) {
      case 'ArrowDown': e.preventDefault(); move(1); break;
      case 'ArrowUp': e.preventDefault(); move(-1); break;
      case 'Enter':
        if (open && active >= 0) { e.preventDefault(); choose(active); }
        break;
      case 'Escape':
        if (open) { e.preventDefault(); e.stopPropagation(); setOpen(false); } else if (input.value) {
          e.preventDefault(); e.stopPropagation(); input.value = '';
        }
        break;
      case 'Tab': setOpen(false); break;
      default: break;
    }
  });

  return {
    el: root,
    input,
    refresh() { if (open) render(); },
    close() { setOpen(false); },
  };
}
