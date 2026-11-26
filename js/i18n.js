/**
 * Interface text.
 *
 * The words of the interface are kept in data/text.json and arrive here as window.FOODMAP_TEXT,
 * one table per language. This script picks the language, fills in the text that is written into
 * index.html, draws the language switch, and gives the rest of the page a function to look text
 * up with.
 *
 * The language is the one named by ?lang= in the address. Failing that, it is the one last
 * clicked on the switch on this device, and the address is given its lang= to say so. Failing
 * that, the page follows the browser: the first of the reader's languages that is one of ours,
 * or English, and the address carries no lang=. So an address with lang= is a link to the page
 * in that language, and one without is a link to the page in each reader's own.
 *
 * The switch has a globe before the languages. A language loads the page again in it, with the
 * same place selected, and is remembered. The globe goes back to following the browser and
 * forgets the remembered one. A lang= that arrives in a link is shown but not remembered, so
 * someone else's link does not change the reader's own choice.
 *
 * A language written in Traditional Chinese also needs the names in the data converted, because
 * the data is kept in Simplified Chinese. See "names in the language's script" below.
 */
(function () {
  'use strict';

  const FILE = window.FOODMAP_TEXT;
  // Not the earlier 'foodmap-lang', which also kept a language that only arrived in a link.
  const STORE_KEY = 'foodmap-lang-chosen';
  const FALLBACK = 'en';
  const byKey = {};
  for (const language of FILE.languages) byKey[language.key] = language;

  function remembered() {
    try {
      return localStorage.getItem(STORE_KEY);
    } catch (error) {
      return null;
    }
  }

  /** Keep the language clicked on the switch, or with no key, forget it. */
  function remember(key) {
    try {
      if (key) localStorage.setItem(STORE_KEY, key);
      else localStorage.removeItem(STORE_KEY);
    } catch (error) {
      // Storage can be closed to the page, as in private browsing. The address still carries it.
    }
  }

  /** Which of our languages a language tag of the browser's stands for, if any. */
  function ours(tag) {
    const parts = String(tag).toLowerCase().split('-');
    if (parts[0] === 'en') return 'en';
    if (parts[0] !== 'zh') return null;
    if (parts.includes('hant')) return 'zh-hant';
    if (parts.includes('hans')) return 'zh-hans';
    return parts.some((part) => part === 'tw' || part === 'hk' || part === 'mo') ? 'zh-hant' : 'zh-hans';
  }

  /** The language the browser asks for: the first of the reader's languages that is one of ours. */
  function browsers() {
    const tags = navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language];
    for (const tag of tags) {
      const key = ours(tag);
      if (key && byKey[key]) return key;
    }
    return FALLBACK;
  }

  const asked = (new URLSearchParams(location.search).get('lang') || '').toLowerCase();
  const saved = remembered();
  const followed = browsers();
  // True when the language was asked for by name, and so belongs in the address.
  const explicit = Boolean(byKey[asked] || byKey[saved]);
  const lang = byKey[asked] ? asked : byKey[saved] ? saved : followed;
  const table = FILE.text[lang];

  function has(key) {
    return table[key] !== undefined;
  }

  /**
   * The text for a key, with the names in braces filled in from `vars`. Where an entry has two
   * forms, `vars.n` chooses between them: one, or any other number.
   */
  function t(key, vars) {
    return fill(table, key, vars);
  }

  /**
   * A text in the script the names are shown in, for words that join a Chinese name, such as 州
   * in 阿坝州: the Simplified text in the English interface, which shows names in Simplified,
   * and the language's own text in a Chinese one.
   */
  function namesText(key, vars) {
    return fill(lang === 'en' ? FILE.text['zh-hans'] : table, key, vars);
  }

  function fill(from, key, vars) {
    let entry = from[key];
    if (entry === undefined) {
      console.warn('no text for "' + key + '"');
      return key;
    }
    if (typeof entry !== 'string') entry = vars && vars.n === 1 ? entry.one : entry.other;
    if (!vars) return entry;
    return entry.replace(/\{(\w+)\}/g, (whole, name) => (vars[name] == null ? whole : String(vars[name])));
  }

  // ---------- the text written into index.html ----------

  document.documentElement.lang = byKey[lang].tag;
  document.title = t('site.pageTitle');
  const description = document.querySelector('meta[name="description"]');
  if (description) description.setAttribute('content', t('site.description'));
  for (const node of document.querySelectorAll('[data-t]')) {
    const text = t(node.getAttribute('data-t'));
    node.textContent = text;
    node.hidden = !text; // a piece that one language has no use for
  }
  for (const name of ['placeholder', 'aria-label', 'title']) {
    for (const node of document.querySelectorAll('[data-t-' + name + ']')) node.setAttribute(name, t(node.getAttribute('data-t-' + name)));
  }
  // A touch screen has no keyboard shortcuts, and a narrow box no room for them, so a text may
  // have a short form: data-t-placeholder-touch beside data-t-placeholder. A box narrower than
  // 300 px takes it, checked again whenever its width changes.
  const touch = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
  const shortened = document.querySelectorAll('[data-t-placeholder-touch]');
  function fitPlaceholders() {
    for (const node of shortened) {
      const short = touch || (node.offsetWidth > 0 && node.offsetWidth < 300);
      node.setAttribute('placeholder', t(node.getAttribute(short ? 'data-t-placeholder-touch' : 'data-t-placeholder')));
    }
  }
  fitPlaceholders();
  if (window.ResizeObserver) {
    const watch = new ResizeObserver(fitPlaceholders);
    for (const node of shortened) watch.observe(node);
  }

  // ---------- the switch ----------

  /** The address of the page as it stands, in another language, or with no key, in the browser's. */
  function addressIn(key) {
    const q = new URLSearchParams(location.search);
    if (key) q.set('lang', key);
    else q.delete('lang');
    const text = q.toString().replace(/%3A/g, ':').replace(/%2C/g, ',');
    return text ? '?' + text : location.pathname;
  }

  // A remembered language reached by a link without lang=: say so in the address.
  if (explicit && asked !== lang) history.replaceState(null, '', addressIn(lang) + location.hash);

  /** A globe, for the choice that follows the browser. */
  function globe() {
    const NS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 16 16');
    svg.setAttribute('aria-hidden', 'true');
    for (const d of ['M8 1.5a6.5 6.5 0 1 0 0 13a6.5 6.5 0 0 0 0-13z', 'M1.5 8h13', 'M8 1.5c-4 4-4 9 0 13', 'M8 1.5c4 4 4 9 0 13']) {
      const path = document.createElementNS(NS, 'path');
      path.setAttribute('d', d);
      svg.append(path);
    }
    return svg;
  }

  /**
   * A click on the switch: remember the choice and load the page in it in place of the current
   * step, so the browser's back goes to the place before, not to the other language. A click
   * that opens a new tab or window is left to the browser.
   */
  function choose(e, key) {
    remember(key);
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    document.dispatchEvent(new Event('foodmap:switch')); // the map keeps its view (js/app.js)
    location.replace(e.currentTarget.href);
  }

  /** An element with a class and a text, either of which may be left out. */
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  const links = [];
  const holder = document.getElementById('lang-switch');
  if (holder) {
    const auto = document.createElement('a');
    auto.className = 'lang-auto';
    auto.append(globe());
    // In the page's language: "Default (English)", naming the language the browser leads to.
    auto.title = t('lang.auto', { language: t('lang.name.' + followed) });
    auto.setAttribute('aria-label', auto.title);
    if (!explicit) auto.setAttribute('aria-current', 'true');
    auto.addEventListener('click', (e) => choose(e, null));
    holder.append(auto);
    links.push({ key: null, node: auto });
    for (const language of FILE.languages) {
      // Each choice is written in its own language, whatever language the page is in.
      const link = document.createElement('a');
      // The short form on the switch; the full name is its hover tip and spoken label.
      link.textContent = language.short;
      link.lang = language.tag;
      link.hreflang = language.tag;
      link.title = language.name;
      link.setAttribute('aria-label', language.name);
      if (explicit && language.key === lang) link.setAttribute('aria-current', 'true');
      link.addEventListener('click', (e) => choose(e, language.key));
      holder.append(link);
      links.push({ key: language.key, node: link });
    }
  }

  // ---------- light and dark, and the layout ----------
  //
  // Three icons: the system's setting, light, dark. js/theme.js keeps the choice and applies it;
  // nothing is loaded again and the address does not change. Beside them, two icons for the
  // layouts, simple and modern; choosing the other one loads the page again, as it is built
  // differently.

  const THEME = window.FoodMapTheme;
  let drawLayoutIcons = null; // set below once the layout switch exists: (onPhone) => void
  const themeHolder = document.getElementById('theme-switch');
  if (THEME && themeHolder) {
    const NS = 'http://www.w3.org/2000/svg';
    const ICONS = {
      // A disc, half filled: whichever the system says.
      auto: [['M8 2.2a5.8 5.8 0 1 0 0 11.6a5.8 5.8 0 0 0 0-11.6z'], ['M8 2.2a5.8 5.8 0 0 1 0 11.6z', 'solid']],
      // A sun.
      light: [['M8 5.2a2.8 2.8 0 1 0 0 5.6a2.8 2.8 0 0 0 0-5.6z'], ['M8 1.2v1.6M8 13.2v1.6M1.2 8h1.6M13.2 8h1.6M3.2 3.2l1.1 1.1M11.7 11.7l1.1 1.1M3.2 12.8l1.1-1.1M11.7 4.3l1.1-1.1']],
      // A crescent moon.
      dark: [['M13.2 9.6A5.6 5.6 0 0 1 6.4 2.8a5.6 5.6 0 1 0 6.8 6.8z']],
    };
    const buttons = [];
    for (const choice of THEME.choices) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'theme-choice';
      const svg = document.createElementNS(NS, 'svg');
      svg.setAttribute('viewBox', '0 0 16 16');
      svg.setAttribute('aria-hidden', 'true');
      for (const part of ICONS[choice]) {
        const path = document.createElementNS(NS, 'path');
        path.setAttribute('d', part[0]);
        if (part[1]) path.setAttribute('class', part[1]);
        svg.append(path);
      }
      button.append(svg);
      button.title = t('theme.' + choice);
      button.setAttribute('aria-label', button.title);
      button.addEventListener('click', function () {
        THEME.set(choice);
        for (const other of buttons) other.node.setAttribute('aria-pressed', String(other.choice === THEME.choice()));
      });
      button.setAttribute('aria-pressed', String(choice === THEME.choice()));
      themeHolder.append(button);
      buttons.push({ choice: choice, node: button });
    }

    // Each layout as it looks on the screen in hand: an outline for the screen, and a filled
    // shape for the panel. On a phone (upright) the panel slid up over the lower part (modern) or
    // a bar across the middle (simple); on a wide screen (landscape) a small card floating at the
    // lower right (modern) or a column beside the map (simple). The icons change with the screen
    // (drawLayoutIcons, below).
    const PHONE_OUTLINE = 'M4.5 1.5h7a1.5 1.5 0 0 1 1.5 1.5v10a1.5 1.5 0 0 1-1.5 1.5h-7A1.5 1.5 0 0 1 3 13V3a1.5 1.5 0 0 1 1.5-1.5z';
    const WIDE_OUTLINE = 'M3 3h10a1.5 1.5 0 0 1 1.5 1.5v7A1.5 1.5 0 0 1 13 13H3a1.5 1.5 0 0 1-1.5-1.5v-7A1.5 1.5 0 0 1 3 3z';
    const LAYOUT_ICONS = {
      phone: {
        sheet: [[PHONE_OUTLINE], ['M3 10a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v3a1.5 1.5 0 0 1-1.5 1.5h-7A1.5 1.5 0 0 1 3 13z', 'solid']],
        bar: [[PHONE_OUTLINE], ['M3 7.2h10v2.6H3z', 'solid']],
      },
      wide: {
        sheet: [[WIDE_OUTLINE], ['M9.3 6.5h3.4a.8.8 0 0 1 .8.8v3.4a.8.8 0 0 1-.8.8H9.3a.8.8 0 0 1-.8-.8V7.3a.8.8 0 0 1 .8-.8z', 'solid']],
        bar: [[WIDE_OUTLINE], ['M10 3h3a1.5 1.5 0 0 1 1.5 1.5v7A1.5 1.5 0 0 1 13 13h-3z', 'solid']],
      },
    };
    const layoutIcons = [];
    if (THEME.layouts) {
      const layoutGroup = el('div', 'lang theme layout-switch');
      layoutGroup.setAttribute('role', 'group');
      layoutGroup.setAttribute('aria-label', t('layout.label'));
      for (const choice of THEME.layouts) {
        const button = document.createElement('button');
        button.type = 'button';
        const svg = document.createElementNS(NS, 'svg');
        svg.setAttribute('viewBox', '0 0 16 16');
        svg.setAttribute('aria-hidden', 'true');
        layoutIcons.push({ choice: choice, svg: svg });
        button.append(svg);
        button.title = choice === 'sheet' ? t('layout.sheet') : t('layout.bar');
        button.setAttribute('aria-label', button.title);
        button.setAttribute('aria-pressed', String(choice === THEME.layout()));
        button.addEventListener('click', function () {
          if (choice === THEME.layout()) return;
          THEME.setLayout(choice);
          document.dispatchEvent(new Event('foodmap:switch')); // the map keeps its view (js/app.js)
          location.reload();
        });
        layoutGroup.append(button);
      }
      themeHolder.after(layoutGroup);
      drawLayoutIcons = function (onPhone) {
        for (const icon of layoutIcons) {
          icon.svg.textContent = '';
          for (const part of LAYOUT_ICONS[onPhone ? 'phone' : 'wide'][icon.choice]) {
            const path = document.createElementNS(NS, 'path');
            path.setAttribute('d', part[0]);
            if (part[1]) path.setAttribute('class', part[1]);
            icon.svg.append(path);
          }
        }
      };
    }
  }

  // ---------- the switches on a phone ----------
  //
  // On a phone (js/theme.js says what counts as one) the switches (theme, layout, language) move
  // from the top bar into the map options, as their first row, opened by the button beside the
  // title; on a wide screen they stand at the end of the top bar.

  const switches = holder ? holder.parentNode : null;
  const topbar = document.querySelector('.topbar');
  const options = document.getElementById('filters');
  const phone = THEME && THEME.phone;
  // The layout icons are drawn for the screen in hand too, so they change at the same moment.
  function placeSwitches() {
    if (drawLayoutIcons) drawLayoutIcons(Boolean(phone && phone.matches));
    if (!switches || !topbar || !options || !phone) return;
    if (phone.matches) {
      if (switches.parentNode !== options) options.prepend(switches);
    } else if (switches.parentNode !== topbar) {
      topbar.append(switches);
    }
  }
  placeSwitches();
  if (phone) {
    if (phone.addEventListener) phone.addEventListener('change', placeSwitches);
    else if (phone.addListener) phone.addListener(placeSwitches);
  }

  /** Point the switch at the page as it stands now. The page calls this when its address changes. */
  function refreshLinks() {
    for (const link of links) link.node.href = addressIn(link.key);
  }
  refreshLinks();

  // ---------- names in the language's script ----------
  //
  // The names of places, records and sources are kept in Simplified Chinese. A language written
  // in Traditional Chinese comes with a table, made by the build, that says how to write them:
  // `chars` gives the form that most names want for each character, as pairs, and `texts` gives
  // in full the names that would come out wrong that way. So the page shows exactly what the
  // build's converter decided, without downloading every name twice.
  //
  // Each file of data is put through `localise` once, when it arrives. Twice would be wrong:
  // a converted name can hold a character that the table would convert again.

  let usual = null; // Map: Simplified character -> Traditional character
  let whole = null; // { Simplified text: Traditional text }
  const HAN = /[\u3400-\u9fff\ud840-\ud87f]/;
  // Values that are not words: shapes, and the search file's groups of like characters.
  const NOT_WORDS = { polys: true, outline: true, maritime: true, alike: true };

  /** One text in the language's script. */
  function inScript(text) {
    if (!usual || !HAN.test(text)) return text;
    if (Object.prototype.hasOwnProperty.call(whole, text)) return whole[text];
    let out = '';
    for (const char of text) out += usual.get(char) || char;
    return out;
  }

  // ---------- names as their sources write them ----------
  //
  // The English interface shows the names that come from Traditional sources (Taiwan's places
  // and registers, Hong Kong's and Macau's) as written there, not in Simplified. The build gives
  // it a table of those texts by id, {id: {field: text}}, and `localise` puts them in place in any
  // object with that id. The Chinese interfaces never load it.

  let written = null; // { id: { field: text } }, in the languages that show names as written

  /** Put the source's own wording into one object with an id, in place. */
  function asWritten(item) {
    if (written && item && Object.prototype.hasOwnProperty.call(written, item.id)) Object.assign(item, written[item.id]);
    return item;
  }

  /** One field of the thing with this id, as its source writes it, or `fallback`. */
  function writtenAs(id, field, fallback) {
    const own = written && Object.prototype.hasOwnProperty.call(written, id) ? written[id][field] : null;
    return own || fallback;
  }

  /** Put every text inside a loaded file into the language's script, in place. */
  function localise(value) {
    if ((!usual && !written) || !value || typeof value !== 'object') return value;
    if (typeof value.id === 'string') asWritten(value);
    if (!usual) {
      for (const inner of Object.values(value)) if (inner && typeof inner === 'object') localise(inner);
      return value;
    }
    for (const key of Object.keys(value)) {
      if (NOT_WORDS[key]) continue;
      const inner = value[key];
      if (typeof inner === 'string') value[key] = inScript(inner);
      else localise(inner);
    }
    return value;
  }

  /** Load one of the build's tables by its address; `take` reads it once it has arrived. */
  function loadTable(src, take) {
    return new Promise(function (resolve) {
      const script = document.createElement('script');
      script.src = src;
      script.onload = function () {
        take();
        resolve();
      };
      script.onerror = function () {
        // The page still works: its own words are right, only the names are not as they should be.
        console.warn('could not load ' + src);
        resolve();
      };
      document.head.append(script);
    });
  }

  const namesAt = byKey[lang].names; // the address of the table, if this language has one
  const ready = Promise.all([
    namesAt
      ? loadTable(namesAt, function () {
          const file = window.FOODMAP_NAMES;
          if (file) {
            const pairs = Array.from(file.chars);
            usual = new Map();
            for (let i = 0; i + 1 < pairs.length; i += 2) usual.set(pairs[i], pairs[i + 1]);
            whole = file.texts;
          }
        })
      : null,
    byKey[lang].asWritten ? loadTable(byKey[lang].asWritten, () => (written = window.FOODMAP_AS_WRITTEN || null)) : null,
  ]);

  window.FoodMapText = {
    lang: lang,
    tag: byKey[lang].tag,
    // True when the address should name the language: it was asked for, not taken from the browser.
    explicit: explicit,
    // True when the names in the data are converted for this language (Traditional Chinese).
    converted: Boolean(byKey[lang].names),
    // True in a Chinese interface, which shows no English at all.
    chinese: lang !== 'en',
    t: t,
    namesText: namesText,
    has: has,
    refreshLinks: refreshLinks,
    // Resolves when the page can start: at once, or when the table of names has loaded.
    ready: ready,
    localise: localise,
    // Names from Traditional sources as written there, in the English interface only.
    asWritten: asWritten,
    writtenAs: writtenAs,
    // The language tag of the names as the page shows them.
    namesTag: () => (usual ? byKey[lang].tag : 'zh-Hans'),
  };
})();
