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
 *
 * The layout is kept here too, for the same reasons: 'bar' (simple: on a wide screen the panel
 * beside the map, on a phone below it with a bar between them) or 'sheet' (modern: the panel
 * lies over the map, as a card on a wide screen and a sliding sheet on a phone). A layout chosen
 * on the switch is remembered on this device, either one. Until one is chosen, a browser with
 * what the modern layout needs (svh, overscroll-behavior and scroll snapping) gets the modern
 * one, and any other the simple one. js/app.js builds the page for it once, so a change takes
 * effect when the page is loaded again.
 *
 * And what counts as a phone, which decides between the phone's page and the wide screen's: a
 * screen narrower than 744 px, or a touch screen no taller than 500 px (a phone on its side;
 * the smallest tablet on its side is 744 px tall). The styles write the same rule in their media
 * queries (css/style.css); every script asks this one, `phone`, and takes any other screen as
 * wide, so the two can never disagree.
 */
(function () {
  'use strict';

  const STORE_KEY = 'foodmap-theme';
  const LAYOUT_KEY = 'foodmap-layout';
  const root = document.documentElement;
  const system = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  const phone = window.matchMedia ? window.matchMedia('(max-width: 743px), (pointer: coarse) and (max-height: 500px)') : null;
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

  /** The layout for a visitor who has not chosen one: modern where the browser can show it. */
  function defaultLayout() {
    const supports = window.CSS && CSS.supports;
    if (!supports) return 'bar';
    const able =
      CSS.supports('height', '100svh') && CSS.supports('overscroll-behavior', 'none') && CSS.supports('scroll-snap-type', 'y proximity');
    return able ? 'sheet' : 'bar';
  }

  function rememberedLayout() {
    try {
      const value = localStorage.getItem(LAYOUT_KEY);
      return value === 'sheet' || value === 'bar' ? value : defaultLayout();
    } catch (error) {
      return defaultLayout();
    }
  }

  let layout = rememberedLayout();

  function setLayout(next) {
    layout = next === 'sheet' ? 'sheet' : 'bar';
    try {
      localStorage.setItem(LAYOUT_KEY, layout); // either choice, so it holds against the default
    } catch (error) {
      // As for the theme: without storage the choice lasts until the page is left.
    }
  }
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
    layouts: ['sheet', 'bar'],
    layout: () => layout,
    setLayout: setLayout,
    phone: phone, // a MediaQueryList, or null where the browser has none
  };
})();
