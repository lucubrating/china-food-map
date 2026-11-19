/**
 * Light and dark.
 *
 * This runs in the head, before the styles, so the page is never drawn in the wrong colours.
 * The choice is one of three: 'auto' follows the system's setting, and 'light' and 'dark' hold
 * whatever the system says. A choice other than auto is remembered on this device. It is never
 * in the address, because it does not change what the page says.
 *
 * The styles read one attribute, data-scheme="light" or "dark" on the root element, which is
 * the choice resolved. Scripts that paint with colours of their own (the shading of provinces)
 * ask for `scheme` and are told when it changes. The switch itself is drawn by js/i18n.js,
 * which has the words for its labels.
 */
(function () {
  'use strict';

  const STORE_KEY = 'foodmap-theme';
  const root = document.documentElement;
  const system = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  const listeners = [];

  function remembered() {
    try {
      const value = localStorage.getItem(STORE_KEY);
      return value === 'light' || value === 'dark' ? value : 'auto';
    } catch (error) {
      return 'auto';
    }
  }

  let choice = remembered();
  let printing = false;

  function resolved() {
    if (printing) return 'light'; // paper is white
    if (choice !== 'auto') return choice;
    return system && system.matches ? 'dark' : 'light';
  }

  function apply() {
    const scheme = resolved();
    if (root.getAttribute('data-scheme') === scheme) return;
    root.setAttribute('data-scheme', scheme);
    for (const listener of listeners) listener(scheme);
  }

  function set(next) {
    choice = next === 'light' || next === 'dark' ? next : 'auto';
    try {
      if (choice === 'auto') localStorage.removeItem(STORE_KEY);
      else localStorage.setItem(STORE_KEY, choice);
    } catch (error) {
      // Storage can be closed to the page. The choice then lasts until the page is left.
    }
    apply();
  }

  if (system) {
    if (system.addEventListener) system.addEventListener('change', apply);
    else if (system.addListener) system.addListener(apply);
  }
  window.addEventListener('beforeprint', function () {
    printing = true;
    apply();
  });
  window.addEventListener('afterprint', function () {
    printing = false;
    apply();
  });
  apply();

  window.FoodMapTheme = {
    choices: ['auto', 'light', 'dark'],
    choice: () => choice,
    scheme: resolved,
    set: set,
    onChange: (listener) => listeners.push(listener),
  };
})();
