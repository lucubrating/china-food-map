/**
 * China Food Map: page controller.
 *
 * One SVG holds the whole map. Geometry is projected once; panning and zooming only change the
 * SVG viewBox. Data arrives as generated scripts built from the files in data/. Two load at the
 * start: the province shapes (js/data/regions.js) and a summary (js/data/summary.js). The rest
 * load when they are needed: the shapes inside a province and its records when it is opened
 * (js/data/units/, js/data/records/), and the search index when the search box is first used.
 *
 * The page starts once js/i18n.js says the language is ready. In Traditional Chinese that is
 * when the table of converted names has loaded; each file of data is then put into that script
 * as it arrives, with TEXT.localise.
 */
window.FoodMapText.ready.then(function () {
  'use strict';

  const { decodeRing, Projector } = window.FoodMapGeo;
  const Timeline = window.FoodMapTimeline;
  const REGIONS = window.FOODMAP_REGIONS;
  const DATA = window.FOODMAP_DATA;
  const TEXT = window.FoodMapText;
  const t = TEXT.t; // the words of the interface, by key: see js/i18n.js and data/text.json
  // True in a Chinese interface, which shows no English at all. The English interface is mixed:
  // it keeps the Chinese names of places and records beside its own text.
  const CHINESE = TEXT.chinese;
  // What goes between two sentences, or between a sentence and the button that follows it.
  const GAP = CHINESE ? '' : ' ';
  TEXT.localise(REGIONS);
  TEXT.localise(DATA);
  // The language tag of the Chinese names on the page, for the browser's choice of font.
  const NAMES_TAG = TEXT.namesTag();
  const SVG_NS = 'http://www.w3.org/2000/svg';

  const CONFIG = {
    // The window of the earth the map covers. Widen it to add other countries later.
    bounds: { west: 72.5, east: 136, south: 2.5, north: 54.5 },
    width: 1000,
    // The view the page opens at, and returns to from the trail's first item and Reset. Zooming
    // out still reaches the whole window above.
    home: { west: 72.5, east: 136, south: 17.5, north: 54.5 },
    // The space left around a frame the map fits, as a share of the frame.
    margin: 0.04,
    // Close enough to read the smallest districts. Boundaries are stored to 0.001 of a degree,
    // which is about four pixels on screen at this zoom.
    maxZoom: 320,
    // Where the code and data are published, linked from the "About this map" box.
    repository: 'https://github.com/lucubrating/china-food-map',
    features: {
      // The time axis is built but hidden. See js/timeline.js.
      timeline: false,
    },
  };

  // Point layers. Colours are the first three slots of the chart palette, which stay
  // distinguishable from each other for colour-blind readers.
  //
  // Naming rule: `label` is the one official name of a category and is used everywhere text has
  // room (panel, legend, search, hover). `one` is its singular. `short` appears only on the
  // switches above the map, where space is tight; each short name uses a different word, and
  // the switch shows the full name on hover and to screen readers. The names themselves are in
  // data/text.json, under layer.<key>.
  const LAYERS = ['products', 'heritage', 'farm'].map((key) => ({
    key: key,
    label: t('layer.' + key + '.label'),
    one: t('layer.' + key + '.one'),
    short: t('layer.' + key + '.short'),
  }));
  const LAYER = {};
  for (const layer of LAYERS) LAYER[layer.key] = layer;
  // Dishes are tied to a province, not a point, so they have no dots and no switch.
  const DISHES = { label: t('dishes.label'), one: t('dishes.one') };
  // One-hue ramp for shading provinces by a number. On the light theme it runs from pale to
  // deep. On the dark theme it runs the other way, from a blue close to the dark land up to a
  // bright one, so that in both a low figure stays quiet and a high one stands out.
  const THEME = window.FoodMapTheme;
  const RAMPS = {
    dark: ['#16263a', '#1a3352', '#1c416b', '#1e4f85', '#215e9f', '#256dba', '#2a78d6', '#3987e5', '#5598e7', '#6da7ec', '#86b6ef', '#9ec5f4', '#b7d3f6'],
    light: ['#cde2fb', '#b7d3f6', '#9ec5f4', '#86b6ef', '#6da7ec', '#5598e7', '#3987e5', '#2a78d6', '#256abf', '#1c5cab', '#184f95', '#104281', '#0d366b'],
  };
  let RAMP = RAMPS[THEME.scheme()];
  // A phone or a wide screen: js/theme.js holds the rule, the same as the styles'.
  const PHONE = THEME.phone;
  const wide = () => !(PHONE && PHONE.matches);

  /** Whether the map is shown over the whole page (immersive view, below). */
  const isImmersive = () => document.documentElement.classList.contains('is-immersive');

  /** Call `listener` whenever the screen turns from a phone's into a wide one, or back. */
  function onLayoutChange(listener) {
    if (!PHONE) return;
    if (PHONE.addEventListener) PHONE.addEventListener('change', listener);
    else if (PHONE.addListener) PHONE.addListener(listener);
  }

  /**
   * The name of a kind, as the data spells it: what a heritage entry makes ('heritage', 'tea'),
   * or what sort of unit a place is ('unit', 'county'). Empty for a kind with no name.
   */
  function kindName(group, kind) {
    const key = group + '.kind.' + kind;
    return kind && TEXT.has(key) ? t(key) : '';
  }

  // ---------- small helpers ----------

  function el(tag, props) {
    const node = document.createElement(tag);
    if (props) {
      for (const key of Object.keys(props)) {
        const value = props[key];
        if (value == null) continue;
        if (key === 'class') node.className = value;
        else if (key === 'text') node.textContent = value;
        else if (key.slice(0, 2) === 'on') node.addEventListener(key.slice(2), value);
        else node.setAttribute(key, value);
      }
    }
    for (let i = 2; i < arguments.length; i++) {
      const child = arguments[i];
      if (child != null) node.append(child);
    }
    return node;
  }

  function svgEl(tag, attrs) {
    const node = document.createElementNS(SVG_NS, tag);
    if (attrs) for (const key of Object.keys(attrs)) node.setAttribute(key, attrs[key]);
    return node;
  }

  /**
   * The line back up, above a name: "‹" and the place, side by side, so a long name wraps in its
   * own column, in line with its first word. The arrow is not read out; the button is named
   * "Back to …" instead.
   */
  function backLine(place, onclick) {
    return el(
      'button',
      { type: 'button', class: 'up', 'aria-label': t('back.to', { place: place }), onclick: onclick },
      el('span', { class: 'up-arrow', 'aria-hidden': 'true', text: '‹' }),
      el('span', { text: place })
    );
  }

  /** A cross for the panel's close button, drawn like the one that closes the search. */
  function crossIcon() {
    const icon = svgEl('svg', { viewBox: '0 0 16 16', 'aria-hidden': 'true' });
    icon.append(svgEl('path', { d: 'M4 4l8 8M12 4l-8 8' }));
    return icon;
  }

  function clamp(v, lo, hi) {
    return Math.max(lo, Math.min(hi, v));
  }

  /** Add one of the generated scripts to the page. Resolves once it has run. */
  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      const script = document.createElement('script');
      script.src = src;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error('could not load ' + src));
      document.head.append(script);
    });
  }

  function hexToRgb(hex) {
    return [parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16)];
  }

  function rampColor(t) {
    const n = RAMP.length - 1;
    const f = clamp(t, 0, 1) * n;
    const i = Math.min(n - 1, Math.floor(f));
    const a = hexToRgb(RAMP[i]);
    const b = hexToRgb(RAMP[i + 1]);
    const k = f - i;
    return 'rgb(' + [0, 1, 2].map((c) => Math.round(a[c] + (b[c] - a[c]) * k)).join(',') + ')';
  }

  function formatNumber(v) {
    return v == null ? t('value.none') : v.toFixed(1);
  }

  // ---------- elements ----------

  const svg = document.getElementById('map');
  const mapWrap = svg.parentNode;
  const gProvinces = document.getElementById('g-provinces');
  const gUnits = document.getElementById('g-units');
  const gMaritime = document.getElementById('g-maritime');
  const gLabels = document.getElementById('g-labels');
  const gPoints = document.getElementById('g-points');
  const gFaint = document.getElementById('g-faint');
  const openOutline = document.getElementById('open-outline');
  const selectionOutline = document.getElementById('selection-outline');
  const trail = document.getElementById('trail');
  const tooltip = document.getElementById('tooltip');
  const legend = document.getElementById('legend');
  const panel = document.getElementById('panel');
  const metricSelect = document.getElementById('metric-select');
  const layerToggles = document.getElementById('layer-toggles');
  const searchInput = document.getElementById('search-input');
  const searchResults = document.getElementById('search-results');

  // ---------- state ----------

  const params = new URLSearchParams(location.search);
  const state = {
    region: null, // the selected unit at any level, as its id: cn:510000, cn:510100
    metric: '',
    hidden: new Set(),
    focus: null,
    item: null, // the entry whose own page fills the panel, as its id
  };
  const timeline = new Timeline({
    enabled: CONFIG.features.timeline || params.get('timeline') === '1',
    element: document.getElementById('timeline'),
    label: t('timeline.label'),
    onChange: function () {
      tallies.clear();
      hovered.id = null;
      refreshPoints();
      refreshCounts();
      renderPanel();
      renderLegend();
    },
  });

  // ---------- geometry ----------

  const projector = new Projector(CONFIG.bounds, CONFIG.width);
  const full = { x0: 0, y0: 0, x1: projector.width, y1: projector.height };
  const home = (function () {
    const [x0, y0] = projector.project(CONFIG.home.west, CONFIG.home.north);
    const [x1, y1] = projector.project(CONFIG.home.east, CONFIG.home.south);
    return { x0: x0, y0: y0, x1: x1, y1: y1 };
  })();

  /** Path data for a list of encoded polygons, and the box that frames their main body. */
  function trace(polys, scale, whole) {
    let d = '';
    const boxes = [];
    for (const poly of polys) {
      const box = { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity };
      for (const ringText of poly) d += projector.ringPath(decodeRing(ringText, scale), box);
      boxes.push(box);
    }
    // Frame the main body, not distant islands: start from the largest piece and add the
    // pieces that sit close to it. A unit marked `whole` is a group of islands with no main
    // body, and is framed with every piece.
    boxes.sort((a, b) => (b.x1 - b.x0) * (b.y1 - b.y0) - (a.x1 - a.x0) * (a.y1 - a.y0));
    const main = Object.assign({}, boxes[0]);
    const reachX = (main.x1 - main.x0) * 0.5;
    const reachY = (main.y1 - main.y0) * 0.5;
    const frame = Object.assign({}, main);
    for (const b of boxes.slice(1)) {
      if (whole || (b.x1 > main.x0 - reachX && b.x0 < main.x1 + reachX && b.y1 > main.y0 - reachY && b.y0 < main.y1 + reachY)) {
        frame.x0 = Math.min(frame.x0, b.x0);
        frame.y0 = Math.min(frame.y0, b.y0);
        frame.x1 = Math.max(frame.x1, b.x1);
        frame.y1 = Math.max(frame.y1, b.y1);
      }
    }
    return { d: d, frame: frame, size: (main.x1 - main.x0) * (main.y1 - main.y0) };
  }

  // Every administrative unit the page has a shape for: the provinces from the start, and the
  // units inside a province once its file has loaded (see "inside a province" below).
  const units = new Map();

  function makeUnit(src, parent, scale) {
    const shape = src.polys && src.polys.length ? trace(src.polys, scale, src.frame === 'all') : null;
    const at = src.anchor || src.at;
    const unit = {
      id: src.id,
      name: src.name,
      short: src.short,
      en: src.en || '',
      tag: src.tag || '', // tells apart places that share an English name: Suzhou (Jiangsu)
      enShort: src.enShort || '', // the English name as the trail shortens it: Ngawa
      namesake: Boolean(src.namesake), // its short name would be its parent's: 长沙县 under 长沙市
      likeProvince: Boolean(src.likeProvince), // its short name is a province's: 海南藏族自治州
      kind: src.kind || '',
      parent: parent ? parent.id : null,
      depth: parent ? parent.depth + 1 : 1,
      n: src.n || 0, // how many units it divides into
      kids: null, // those units, once their file has loaded
      d: shape ? shape.d : '',
      frame: shape ? shape.frame : null,
      size: shape ? shape.size : 0,
      anchor: at ? projector.project(at[0], at[1]) : null,
      path: null,
      label: null,
    };
    units.set(unit.id, unit);
    return unit;
  }

  const provinces = REGIONS.provinces.map((p) => makeUnit(p, null, REGIONS.scale));
  const provinceById = new Map(provinces.map((p) => [p.id, p]));
  const labelOrder = provinces.slice().sort((a, b) => b.size - a.size);

  function regionName(id) {
    const p = provinceById.get(id);
    return p ? p.name : id;
  }

  /**
   * A place's English name, with the tag that tells it apart from places of the same name:
   * Suzhou (Jiangsu). `bare` leaves the tag out, where the places around it already say it.
   */
  function englishName(en, tag, bare) {
    return tag && !bare ? t('place.tagged', { name: en, tag: tag }) : en;
  }

  /**
   * A place's name as text: 四川省 Sichuan in the English interface, 四川省 in a Chinese one.
   * `bare` leaves out the tag of a shared English name (see englishName).
   */
  function fullName(unit, bare) {
    return unit.name + (unit.en && !CHINESE ? ' ' + englishName(unit.en, unit.tag, bare) : '');
  }

  /** The same with the short name: 四川 Sichuan, 阿坝 Ngawa, or 四川 and 阿坝. */
  function briefName(unit) {
    const en = unit.enShort || unit.en;
    return unit.short + (en && !CHINESE ? ' ' + en : '');
  }

  /**
   * A place in the trail just above a place that shares its name, or one whose short name is a
   * province's: a longer form made from its kind, so the two are told apart: 长沙市 Changsha City
   * above 长沙县, 阿坝州 Ngawa Prefecture above 阿坝县, 海南州 Hainan Prefecture in Qinghai.
   * A kind with no such form gives the full name.
   */
  function namesakeName(unit) {
    const key = 'trail.long.' + unit.kind;
    if (!TEXT.has(key)) return fullName(unit, true);
    const en = unit.enShort || unit.en;
    return TEXT.namesText(key, { name: unit.short }) + (en && !CHINESE ? ' ' + t(key, { name: en }) : '');
  }

  /** The name of a food in the eating table. */
  function foodName(column) {
    return CHINESE ? column.zh : column.en;
  }

  // ---------- drawing the base map ----------

  for (const p of provinces) {
    const path = svgEl('path', { class: 'prov', d: p.d, 'data-id': p.id, tabindex: '0', role: 'button', 'aria-label': fullName(p) });
    p.path = path;
    gProvinces.append(path);
    // The name, with a count of the province's records under it while the province is closed.
    // Sizes inside are in em, so they stay the same on screen as the map is zoomed.
    const label = svgEl('g', { class: 'prov-name', transform: 'translate(' + p.anchor[0].toFixed(2) + ' ' + p.anchor[1].toFixed(2) + ')' });
    const name = svgEl('text', { class: 'place-label' });
    name.textContent = p.short;
    const badge = svgEl('g', { class: 'badge' });
    const plate = svgEl('rect', { y: '0.85em', height: '1.3em', rx: '0.65em' });
    const number = svgEl('text', { y: '1.5em' });
    badge.append(plate, number);
    label.append(name, badge);
    p.label = label;
    p.badge = { node: badge, plate: plate, number: number, shown: false, width: 0 };
    gLabels.append(label);
  }
  {
    let d = '';
    for (const poly of REGIONS.maritime) for (const ringText of poly) d += projector.ringPath(decodeRing(ringText, REGIONS.scale));
    gMaritime.append(svgEl('path', { class: 'maritime', d: d }));
  }
  // Land of one province inside another's shape (加格达奇区: Heilongjiang's, inside Inner
  // Mongolia). The national map shows the provinces as the source draws them. While a province is
  // open, the piece is added to both shapes: the fill rule makes it a hole in the one and a part
  // of the other, so it shows, and opens, as its own province (see syncEnclaves).
  for (const enclave of REGIONS.enclaves || []) {
    const ring = projector.ringPath(decodeRing(enclave.ring, REGIONS.scale));
    for (const id of [enclave.from, enclave.to]) {
      const p = provinceById.get(id);
      if (p) p.dOpen = (p.dOpen || p.d) + ring;
    }
  }

  /** Draw the two shapes an enclave belongs to as the national map or a province needs them. */
  function syncEnclaves(provinceOpen) {
    for (const p of provinces) if (p.dOpen) p.path.setAttribute('d', provinceOpen ? p.dOpen : p.d);
  }

  // ---------- records ----------
  //
  // Records are kept by province, because that is how the page uses them: a panel lists the
  // records of one province, and the map shows dots for the open province only. Each province's
  // records are in a file of their own, loaded when the province is first opened. Until then the
  // page works from the counts in the summary it loads at the start.

  const RECORD_KEYS = ['dishes'].concat(LAYERS.map((layer) => layer.key));
  const store = new Map(); // province id -> { dishes: [], products: [], heritage: [], farm: [] }, once loaded
  const recordLoads = new Map(); // province id -> Promise for its file
  const recordById = new Map(); // record id -> { record, layer }, for the provinces loaded
  // Every entry by id, dishes too: { record, layer }, where a dish has no layer.
  const entryById = new Map();
  // An entry's title as its source writes it: Simplified for the mainland's sources, Traditional
  // for Hong Kong's, Macau's and Taiwan's. Kept from before the file is put into the script of
  // the interface, for the name in the address.
  const sourceNames = new Map();
  const ownScript = new Set(); // the ids of entries whose source writes in Traditional Chinese
  let wantedFocus = null; // { id, options }: a record to mark once its province's records are in

  function loadRecords(province) {
    if (!recordLoads.has(province.id)) {
      const src = 'js/data/records/' + province.id.replace(':', '-') + '.js?v=' + DATA.recordsVersion;
      recordLoads.set(
        province.id,
        loadScript(src).then(function () {
          const file = (window.FOODMAP_RECORDS || {})[province.id];
          if (!file) throw new Error('nothing for ' + province.id + ' in ' + src);
          for (const key of RECORD_KEYS) {
            for (const record of file[key]) {
              sourceNames.set(record.id, record.own || record.title);
              if (record.own) ownScript.add(record.id);
              delete record.own; // already in its own script: not for `localise`
            }
          }
          TEXT.localise(file);
          for (const key of RECORD_KEYS) {
            for (const record of file[key]) {
              record.region = province.id; // left out of the file, which is all one province
              if (LAYER[key]) recordById.set(record.id, { record: record, layer: LAYER[key] });
              entryById.set(record.id, { record: record, layer: LAYER[key] || null });
            }
          }
          store.set(province.id, file);
        })
      );
    }
    return recordLoads.get(province.id);
  }

  // What an entry's own page shows beyond its record (the source's wording of its area, remarks,
  // an introduction) is in one more file per province, fetched when a page is first opened there.
  const detailLoads = new Map(); // province id -> Promise for { record id: details }

  function loadDetails(provinceId) {
    if (!detailLoads.has(provinceId)) {
      const none = Promise.resolve({});
      if (DATA.detailed.indexOf(provinceId) === -1) return none;
      const src = 'js/data/details/' + (TEXT.converted ? TEXT.lang + '/' : '') + provinceId.replace(':', '-') + '.js?v=' + DATA.detailsVersion;
      detailLoads.set(
        provinceId,
        loadScript(src).then(
          () => (window.FOODMAP_DETAILS || {})[provinceId] || {},
          function (error) {
            console.warn(error.message);
            return {};
          }
        )
      );
    }
    return detailLoads.get(provinceId);
  }

  /** Fetch a province's records if they are not here yet, and redraw once they are. */
  function requestRecords(province) {
    if (store.has(province.id) || province.fetching || province.noRecords) return;
    province.fetching = true;
    loadRecords(province).then(
      function () {
        province.fetching = false;
        tallies.delete(province.id);
        hovered.id = null;
        if (chainOf(state.region)[0] !== province) {
          if (openProvinces().indexOf(province) !== -1) refreshMap(); // opened without choosing
          return;
        }
        applySelection();
        if (wantedFocus) {
          const waiting = wantedFocus;
          wantedFocus = null;
          focusRecord(waiting.id, waiting.options);
        }
      },
      function (error) {
        province.fetching = false;
        province.noRecords = true;
        console.warn(error.message);
        if (chainOf(state.region)[0] === province) renderPanel();
      }
    );
  }

  /** One province's records in one category. Empty until the province's file has loaded. */
  function recordsOf(provinceId, key) {
    const own = store.get(provinceId);
    return own ? own[key] : [];
  }

  /** How many records a province has in one category, at the chosen year. */
  function countOf(province, key) {
    const own = store.get(province.id);
    if (own) return key === 'dishes' ? own.dishes.length : own[key].filter((r) => timeline.accepts(r)).length;
    return (DATA.counts[province.id] || {})[key] || 0;
  }

  /** The same across the country. */
  function nationalCount(key) {
    let n = 0;
    for (const p of provinces) n += countOf(p, key);
    return n;
  }

  // ---------- inside a province ----------
  //
  // A province opens into the units directly under it, and a unit that has shapes below it
  // opens the same way: a city into its districts and counties. The shapes arrive on demand,
  // one generated file per opened unit (js/data/units/). One branch is open at a time: the
  // selected unit and the units above it.

  const lower = new Map(); // id -> { id, name, short, parent }: places known by name only
  const lowerKids = new Map(); // unit id -> the ids of such places directly under it
  const loads = new Map(); // unit id -> Promise for the file that describes its parts
  const drawn = new Map(); // unit id -> { group, base, labels } while its parts are on the map
  const tallies = new Map(); // province id -> Map(place id -> number of records there)
  let wanted = null; // { id, options, on }: a selection waiting for the file of the unit `on`

  // Places opened on the map without being chosen: one by a soft click (Shift), which a new soft
  // click replaces, and any number by background clicks (Cmd or Ctrl). A hard
  // choice (a click, Esc, the trail, search) clears them all. See "soft, view and background clicks".
  const peeks = { soft: null, background: new Set(), round: 0 }; // round: moved on by each clearing

  /** The ids of the places open on the map: the chosen one and the ones opened without choosing. */
  function openIds() {
    const ids = [];
    if (state.region) ids.push(state.region);
    if (peeks.soft) ids.push(peeks.soft);
    for (const id of peeks.background) ids.push(id);
    return ids;
  }

  /** Every unit open on the map: each open place's chain, the units that open, parents first. */
  function openBranch() {
    const branch = [];
    for (const id of openIds()) for (const unit of chainOf(id)) if (opens(unit) && branch.indexOf(unit) === -1) branch.push(unit);
    return branch;
  }

  /** The provinces open on the map, whose dots are drawn. */
  function openProvinces() {
    const list = [];
    for (const id of openIds()) {
      const province = chainOf(id)[0];
      if (province && list.indexOf(province) === -1) list.push(province);
    }
    return list;
  }

  /** The province an id belongs to, read from the id alone. */
  function provinceIdOf(id) {
    const parts = String(id || '').split(':');
    if (parts[0] === 'cn') return /^\d{6}$/.test(parts[1] || '') ? 'cn:' + parts[1].slice(0, 2) + '0000' : null;
    return REGIONS.prefixes[parts[0]] || null;
  }

  /** A unit with a shape or, failing that, a place known by name only. */
  function place(id) {
    return units.get(id) || lower.get(id) || null;
  }

  function parentOf(id) {
    const found = place(id);
    return found ? found.parent : null;
  }

  /** True if `id` is the unit `ancestor` or lies inside it. */
  function within(id, ancestor) {
    for (let at = id; at; at = parentOf(at)) if (at === ancestor) return true;
    return false;
  }

  /** The units from the province down to `id`. Empty if `id` is not a unit the page has loaded. */
  function chainOf(id) {
    const chain = [];
    for (let unit = units.get(id); unit; unit = units.get(unit.parent)) chain.unshift(unit);
    return chain;
  }

  /** The names on the way down from a unit to a place inside it: 成都市蒲江县, seen from Sichuan. */
  function pathBelow(id, top) {
    let text = '';
    for (let at = id; at && at !== top; at = parentOf(at)) {
      const found = place(at);
      if (!found) return '';
      text = found.name + text;
    }
    return text;
  }

  /** Whether a unit's parts have shapes to load. */
  function opens(unit) {
    return unit.n > 0 && !unit.failed && REGIONS.unitLevels.indexOf(unit.depth + 1) !== -1;
  }

  /**
   * The borders between the parts of a unit, each as one line, so that the page draws a border
   * once and can hide it (see applySelection). Parts that share a border have the same points
   * along it, which is how a border is found: by matching the steps from point to point. The
   * outer edge of the parts together is left out, because the outline of the unit they make up
   * is drawn there.
   */
  function bordersBetween(file) {
    const sides = new Map(); // one step between two points -> the parts it runs along
    const rings = [];
    file.units.forEach(function (part, index) {
      for (const poly of part.polys || []) {
        for (const text of poly) {
          const ring = decodeRing(text, file.scale);
          const steps = [];
          for (let i = 1; i < ring.length; i++) {
            const a = ring[i - 1];
            const b = ring[i];
            const key = a[0] < b[0] || (a[0] === b[0] && a[1] < b[1]) ? a + ';' + b : b + ';' + a;
            steps.push(key);
            if (sides.has(key)) sides.get(key).push(index);
            else sides.set(key, [index]);
          }
          rings.push({ index: index, ring: ring, steps: steps });
        }
      }
    });
    const found = new Map(); // "3|7" -> path data for the border between parts 3 and 7
    for (const item of rings) {
      let other = -1; // the part on the far side of the current run of steps
      let run = [];
      const close = function () {
        // Each border turns up twice, once from either side. Keep the one from the earlier part.
        if (other > item.index) {
          const key = item.index + '|' + other;
          found.set(key, (found.get(key) || '') + projector.linePath(run));
        }
      };
      item.steps.forEach(function (key, i) {
        const across = sides.get(key).find((index) => index !== item.index);
        const next = across === undefined ? -1 : across;
        if (next !== other || !run.length) {
          close();
          other = next;
          run = [item.ring[i]];
        }
        run.push(item.ring[i + 1]);
      });
      close();
    }
    return Array.from(found, function (entry) {
      const pair = entry[0].split('|');
      return { a: file.units[pair[0]].id, b: file.units[pair[1]].id, d: entry[1], path: null };
    });
  }

  /** Load the file that describes the parts of a unit. Resolves once they are in `units`. */
  function loadKids(unit) {
    if (!loads.has(unit.id)) {
      const src = 'js/data/units/' + unit.id.replace(':', '-') + '.js?v=' + REGIONS.unitsVersion;
      loads.set(
        unit.id,
        loadScript(src).then(function () {
          const file = (window.FOODMAP_UNITS || {})[unit.id];
          if (!file) throw new Error('nothing for ' + unit.id + ' in ' + src);
          TEXT.localise(file);
          unit.kids = file.units.map((part) => makeUnit(part, unit, file.scale));
          unit.bySize = unit.kids.slice().sort((a, b) => b.size - a.size);
          unit.borders = bordersBetween(file);
          // The outer boundary of the parts together. An opened unit is drawn with it, because
          // its own shape comes from a coarser file and does not follow its parts exactly.
          unit.fine = '';
          for (const ringText of file.outline || []) unit.fine += projector.ringPath(decodeRing(ringText, file.scale));
          const below = file.below || {};
          for (const id of Object.keys(below)) {
            const row = below[id];
            lower.set(id, TEXT.asWritten({ id: id, name: row[0], short: row[1], parent: row[2] }));
            if (!lowerKids.has(row[2])) lowerKids.set(row[2], []);
            lowerKids.get(row[2]).push(id);
          }
          return unit;
        })
      );
    }
    return loads.get(unit.id);
  }

  /** The parts of a unit, for listing: units with shapes if they have loaded, names otherwise. */
  function partsOf(unit) {
    if (unit.kids) return unit.kids;
    return (lowerKids.get(unit.id) || []).map((id) => lower.get(id));
  }

  function recordIn(record, unit) {
    if (unit.depth === 1) return record.region === unit.id;
    return (record.areas || []).some((area) => within(area, unit.id));
  }

  /** The records of one layer in a unit: those whose places are the unit or lie inside it. */
  function recordsIn(layer, unit) {
    return recordsOf(provinceIdOf(unit.id), layer.key).filter((r) => timeline.accepts(r) && recordIn(r, unit));
  }

  /**
   * How many records each place in a province holds. A record that spans several places counts
   * once in each, so the numbers can add up to more than the province's total.
   */
  function tallyOf(province) {
    if (!tallies.has(province.id)) {
      const counts = new Map();
      for (const layer of LAYERS) {
        for (const record of recordsOf(province.id, layer.key)) {
          if (!timeline.accepts(record)) continue;
          const touched = new Set();
          for (const area of record.areas || []) {
            for (let at = area; at && at !== province.id; at = parentOf(at)) touched.add(at);
          }
          for (const id of touched) counts.set(id, (counts.get(id) || 0) + 1);
        }
      }
      tallies.set(province.id, counts);
    }
    return tallies.get(province.id);
  }

  /** The outline to draw around a unit: the detailed one while its parts are on the map. */
  function outlineOf(unit) {
    return drawn.has(unit.id) && unit.fine ? unit.fine : unit.d;
  }

  function drawKids(unit) {
    const depth = unit.depth + 1;
    const group = svgEl('g', { class: 'units depth-' + depth });
    // The opened unit itself, in its detailed outline, lies under its parts. Its usual shape is
    // hidden meanwhile (see .is-open in the styles).
    const base = svgEl('path', { class: 'base', d: unit.fine || unit.d, 'data-id': unit.id });
    group.append(base);
    const labels = svgEl('g', { class: 'unit-labels depth-' + depth });
    for (const kid of unit.kids) {
      if (!kid.d) continue; // the boundary source has no shape for this unit
      kid.path = svgEl('path', { class: 'unit', d: kid.d, 'data-id': kid.id, tabindex: '0', role: 'button', 'aria-label': fullName(kid) });
      group.append(kid.path);
      if (kid.anchor) {
        kid.label = svgEl('text', { class: 'place-label', x: kid.anchor[0].toFixed(2), y: kid.anchor[1].toFixed(2) });
        kid.label.textContent = kid.short;
        labels.append(kid.label);
      }
    }
    // The borders between the parts lie on top of them.
    const lines = svgEl('g', { class: 'borders' });
    for (const border of unit.borders) {
      border.path = svgEl('path', { class: 'border', d: border.d });
      lines.append(border.path);
    }
    group.append(lines);
    gUnits.append(group);
    gLabels.append(labels);
    drawn.set(unit.id, { group: group, base: base, labels: labels });
  }

  function eraseKids(id) {
    const parts = drawn.get(id);
    parts.group.remove();
    parts.labels.remove();
    for (const kid of units.get(id).kids) {
      kid.path = null;
      kid.label = null;
    }
    for (const border of units.get(id).borders) border.path = null;
    drawn.delete(id);
  }

  /** Put the open branch on the map: the parts of each open unit (openBranch). */
  function syncOpen() {
    const branch = openBranch();
    for (const unit of branch) {
      if (unit.kids || unit.loading) continue;
      unit.loading = true;
      loadKids(unit).then(
        function () {
          unit.loading = false;
          tallies.delete(provinceIdOf(unit.id));
          if (wanted && wanted.on === unit.id) selectRegion(wanted.id, wanted.options);
          else if (chainOf(state.region).indexOf(unit) !== -1) applySelection();
          else if (openBranch().indexOf(unit) !== -1) refreshMap();
        },
        function (error) {
          unit.loading = false;
          unit.failed = true;
          console.warn(error.message);
          if (wanted && wanted.on === unit.id) wanted = null;
          if (chainOf(state.region).indexOf(unit) !== -1) applySelection();
          else if (openBranch().indexOf(unit) !== -1) refreshMap();
        }
      );
    }
    const keep = new Set(branch.filter((unit) => unit.kids).map((unit) => unit.id));
    for (const id of Array.from(drawn.keys())) if (!keep.has(id)) eraseKids(id);
    for (const unit of branch) if (unit.kids && !drawn.has(unit.id)) drawKids(unit);
  }

  // ---------- points ----------
  //
  // Dots are drawn for the open provinces only (openProvinces). A closed province shows a count
  // instead (see refreshCounts), so the whole map is not buried under thousands of dots.

  const points = new Map(); // record id -> { node, x, y, record, layer }, for the open provinces
  let pointsFor = new Set(); // the ids of the provinces whose dots are on the map
  for (const layer of LAYERS) {
    layer.group = svgEl('g', { class: 'layer layer-' + layer.key, 'data-layer': layer.key });
    gPoints.append(layer.group);
    layer.faint = svgEl('g', { class: 'layer layer-' + layer.key });
    gFaint.append(layer.faint);
  }

  /**
   * Where the i-th of n dots at one position goes, as an offset on screen in pixels.
   * Dots placed at the centre of a unit, for want of anything more exact, line up under the
   * unit's name, five to a row. Dots at the same exact position fan out in a spiral.
   */
  function offsetOf(i, n, approx) {
    if (approx) {
      const row = Math.floor(i / 5);
      const inRow = Math.min(5, n - row * 5);
      return [((i % 5) - (inRow - 1) / 2) * 11, 15 + row * 11];
    }
    if (i === 0) return [0, 0];
    const angle = i * 2.399963;
    const radius = 9 * Math.sqrt(i);
    return [Math.round(radius * Math.cos(angle)), Math.round(radius * Math.sin(angle))];
  }

  function drawPoints(list) {
    for (const entry of points.values()) entry.node.remove();
    points.clear();
    pointsFor = new Set(list.map((province) => province.id));
    refreshFaint();
    const stacks = new Map(); // position -> the records there
    for (const province of list) for (const layer of LAYERS) {
      for (const record of recordsOf(province.id, layer.key)) {
        if (!record.coord) continue;
        const key = record.coord[0] + ',' + record.coord[1];
        if (!stacks.has(key)) stacks.set(key, []);
        stacks.get(key).push({ record: record, layer: layer });
      }
    }
    for (const stack of stacks.values()) {
      const xy = projector.project(stack[0].record.coord[0], stack[0].record.coord[1]);
      // A near-zero-length line with round ends draws a dot whose size does not change with
      // zoom, because strokes are set not to scale. The line is short enough to stay a round
      // dot at the closest zoom.
      const d = 'M' + xy[0].toFixed(2) + ' ' + xy[1].toFixed(2) + 'h0.001';
      const approx = stack.every((item) => item.record.approx);
      stack.forEach(function (item, i) {
        // A dot that shares its position has a smaller area that answers to the pointer, so
        // that each dot in the group can be picked out.
        const node = svgEl('g', { class: stack.length > 1 ? 'pt is-stacked' : 'pt', 'data-id': item.record.id });
        node.append(svgEl('path', { class: 'pt-hit', d: d }), svgEl('path', { class: 'pt-ring', d: d }), svgEl('path', { class: 'pt-dot', d: d }));
        // --px is the size of one screen pixel in map units, kept current by applyView, so the
        // offset stays the same on screen at every zoom.
        const off = offsetOf(i, stack.length, approx);
        if (off[0] || off[1]) node.style.transform = 'translate(calc(var(--px) * ' + off[0] + '), calc(var(--px) * ' + off[1] + '))';
        item.layer.group.append(node);
        points.set(item.record.id, { node: node, x: xy[0], y: xy[1], record: item.record, layer: item.layer });
      });
    }
  }

  // ---------- faint dots ----------
  //
  // A province that is not open shows where its entries lie as small quiet dots that cannot be
  // picked, so the whole map is a picture of where things are. They come from one small file of
  // positions, fetched after the map is first drawn. All of a province's dots in one category
  // are a single path, so the map carries a hundred or so elements for them, not thousands.
  // The open province shows its real dots in their place. With the time axis on they are left
  // out, because the file holds no years.

  const faintOf = new Map(); // province id -> the paths of its faint dots
  // Each dot is a line too short to see, drawn with round ends. A mobile browser draws nothing
  // for a line whose length on screen falls below a tiny limit, so where the whole map is shown
  // very small (a narrow phone, zoomed out) the lines are ten times as long: still far under a
  // pixel there. Everywhere else they keep their usual length.
  const FAINT_SMALL = 0.6; // the scale (screen px per map unit) below which the longer lines are used
  const faintLines = []; // { path, usual, small }: each path's two forms
  let faintSmall = false;

  function drawFaint(file) {
    for (const layer of LAYERS) {
      for (const province of provinces) {
        const flat = (file[province.id] || {})[layer.key];
        if (!flat) continue;
        let usual = '';
        let small = '';
        for (let i = 0; i + 1 < flat.length; i += 2) {
          const xy = projector.project(flat[i], flat[i + 1]);
          const at = 'M' + xy[0].toFixed(1) + ' ' + xy[1].toFixed(1);
          usual += at + 'h0.001';
          small += at + 'h0.01';
        }
        const path = svgEl('path', { d: faintSmall ? small : usual });
        faintLines.push({ path: path, usual: usual, small: small });
        layer.faint.append(path);
        if (!faintOf.has(province.id)) faintOf.set(province.id, []);
        faintOf.get(province.id).push(path);
      }
    }
    refreshFaint();
  }

  /** Hide the faint dots of the provinces whose real dots are on the map. */
  function refreshFaint() {
    for (const [id, paths] of faintOf) {
      for (const path of paths) path.style.display = pointsFor.has(id) ? 'none' : '';
    }
  }

  function layerVisible(layer) {
    return !state.hidden.has(layer.key);
  }

  /** How many records of a category have a position on the map, across the country. */
  function placedCount(layer) {
    // The summary's figure holds while the time axis is off. With it on, every province has
    // been loaded (see the start-up code), so the records themselves can be counted.
    if (!timeline.enabled) return DATA.placed[layer.key];
    let n = 0;
    for (const own of store.values()) n += own[layer.key].filter((r) => r.coord && timeline.accepts(r)).length;
    return n;
  }

  /** Set the number under each closed province: its records in the categories switched on. */
  function refreshCounts() {
    const open = openProvinces();
    for (const p of provinces) {
      let n = 0;
      for (const layer of LAYERS) if (layerVisible(layer)) n += countOf(p, layer.key);
      const badge = p.badge;
      badge.shown = n > 0 && open.indexOf(p) === -1;
      badge.node.style.display = badge.shown ? '' : 'none';
      if (!badge.shown) continue;
      const text = String(n);
      badge.width = 0.62 * text.length + 0.9; // in em
      badge.number.textContent = text;
      badge.plate.setAttribute('x', (-badge.width / 2).toFixed(2) + 'em');
      badge.plate.setAttribute('width', badge.width.toFixed(2) + 'em');
    }
  }

  function refreshPoints() {
    for (const layer of LAYERS) {
      layer.group.style.display = layerVisible(layer) ? '' : 'none';
      layer.faint.style.display = layerVisible(layer) ? '' : 'none';
    }
    for (const entry of points.values()) {
      entry.node.style.display = timeline.accepts(entry.record) ? '' : 'none';
      entry.node.classList.toggle('is-focus', entry.record.id === state.focus);
    }
    if (state.focus && points.has(state.focus)) {
      const node = points.get(state.focus).node;
      node.parentNode.append(node); // draw the focused dot on top
    }
  }

  // ---------- camera ----------

  let size = { W: 1, H: 1, left: 0, top: 0 };
  let view = { cx: (full.x0 + full.x1) / 2, cy: (full.y0 + full.y1) / 2, w: full.x1 - full.x0 };
  let frameRequest = 0;
  let frameTimer = 0;
  let labelTimer = 0;
  let flight = 0;
  let flightTimer = 0;

  function measure() {
    const r = svg.getBoundingClientRect();
    size = { W: Math.max(1, r.width), H: Math.max(1, r.height), left: r.left, top: r.top };
  }

  function widthToFit(box, pad) {
    const aspect = size.H / size.W;
    return Math.max((box.x1 - box.x0) * (1 + pad), ((box.y1 - box.y0) * (1 + pad)) / aspect);
  }

  function setView(cx, cy, w) {
    const maxW = widthToFit(full, CONFIG.margin);
    const minW = (full.x1 - full.x0) / CONFIG.maxZoom;
    view = {
      cx: clamp(cx, full.x0, full.x1),
      cy: clamp(cy, full.y0, full.y1),
      w: clamp(w, minW, maxW),
    };
    // Browsers pause animation frames while a page is in the background, so apply at once there.
    if (document.hidden) {
      applyView();
    } else if (!frameRequest) {
      frameRequest = requestAnimationFrame(applyView);
      // A page embedded in a hidden pane can have its frames paused without being told it is
      // hidden. The timer makes sure the view is still applied.
      frameTimer = setTimeout(applyView, 150);
    }
  }

  function applyView() {
    cancelAnimationFrame(frameRequest);
    clearTimeout(frameTimer);
    frameRequest = 0;
    const h = view.w * (size.H / size.W);
    svg.setAttribute('viewBox', [view.cx - view.w / 2, view.cy - h / 2, view.w, h].map((v) => v.toFixed(3)).join(' '));
    // Keep label text the same size on screen at every zoom.
    const scale = size.W / view.w;
    gLabels.setAttribute('font-size', (12 / scale).toFixed(4));
    svg.style.setProperty('--px', (1 / scale).toFixed(5) + 'px');
    svg.classList.toggle('is-far', scale < 1.6);
    if (scale < FAINT_SMALL !== faintSmall) {
      faintSmall = scale < FAINT_SMALL;
      for (const line of faintLines) line.path.setAttribute('d', faintSmall ? line.small : line.usual);
    }
    clearTimeout(labelTimer);
    labelTimer = setTimeout(layoutLabels, 90);
  }

  /**
   * Show the names that have room. The parts of an open unit come first, and a part is named
   * only once it is large enough on screen to hold its name. Provinces follow. Within each
   * group, larger places are named before smaller ones.
   */
  function layoutLabels() {
    const scale = size.W / view.w;
    const placed = [];
    const clear = (box) => !placed.some((b) => box.x < b.x + b.w && box.x + box.w > b.x && box.y < b.y + b.h && box.y + box.h > b.y);
    const show = function (unit, charWidth, mustFit) {
      if (!unit.label) return false;
      const w = unit.short.length * charWidth + 4;
      let ok = true;
      if (mustFit && unit.frame) {
        ok = (unit.frame.x1 - unit.frame.x0) * scale >= w * 0.8 && (unit.frame.y1 - unit.frame.y0) * scale >= 15;
      }
      const box = { x: unit.anchor[0] * scale - w / 2, y: unit.anchor[1] * scale - 8, w: w, h: 16 };
      if (ok) ok = clear(box);
      unit.label.style.display = ok ? '' : 'none';
      if (ok) placed.push(box);
      return ok;
    };
    // An open unit shows either the names of its parts or its own name, never both. Its own
    // name stays until at least a third of its parts have room for theirs.
    const named = new Set();
    for (const id of Array.from(drawn.keys()).reverse()) {
      const kids = units.get(id).bySize.filter((kid) => kid.label);
      const before = placed.length;
      let shown = 0;
      for (const kid of kids) {
        if (named.has(kid.id)) kid.label.style.display = 'none';
        else if (show(kid, 12, true)) shown += 1;
      }
      if (shown && shown * 3 >= kids.length) {
        named.add(id);
      } else {
        for (const kid of kids) kid.label.style.display = 'none';
        placed.length = before;
      }
    }
    const shown = [];
    for (const p of labelOrder) {
      if (named.has(p.id)) p.label.style.display = 'none';
      else if (show(p, 13, false)) shown.push(p);
    }
    // Names come first. A province's count is added under its name only where that leaves
    // every name and every count already placed uncovered.
    for (const p of shown) {
      let counted = false;
      if (p.badge.shown) {
        const w = p.badge.width * 11 + 4;
        const box = { x: p.anchor[0] * scale - w / 2, y: p.anchor[1] * scale + 8, w: w, h: 17 };
        counted = clear(box);
        if (counted) placed.push(box);
      }
      p.label.classList.toggle('no-room', !counted);
    }
  }

  function stopFlight() {
    cancelAnimationFrame(flight);
    clearTimeout(flightTimer);
  }

  // The last box framed on purpose (by choosing, R, H, Shift and a digit), with the place it was
  // framed for, so that framing again for a new shape of the map (reframe) keeps it; and whether
  // the view has been moved by hand since (a drag, a pinch, the wheel, the zoom keys, the arrows).
  let lastFrame = null;
  let movedByHand = false;

  function fitBox(box, pad, animate) {
    lastFrame = { box: Object.assign({}, box), pad: pad, region: state.region };
    movedByHand = false;
    const target = { cx: (box.x0 + box.x1) / 2, cy: (box.y0 + box.y1) / 2, w: widthToFit(box, pad) };
    // With the phone's sheet raised over the map, fit the box into the part left in view above
    // it; with the wide screen's card over the map's right, into the part left of it.
    const cover = SHEET ? sheetCover() : 0;
    if (cover > 0 && cover < size.H * 0.8) {
      const seen = (size.H - cover) / size.W;
      target.w = Math.max((box.x1 - box.x0) * (1 + pad), ((box.y1 - box.y0) * (1 + pad)) / seen);
      target.cy += (cover / 2) * (target.w / size.W);
    }
    const side = SHEET ? cardCover() : 0;
    if (side > 0 && side < size.W * 0.8) {
      target.w = Math.max(((box.x1 - box.x0) * (1 + pad) * size.W) / (size.W - side), ((box.y1 - box.y0) * (1 + pad) * size.W) / size.H);
      target.cx += (side / 2) * (target.w / size.W);
    }
    stopFlight();
    const still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (!animate || document.hidden || still) {
      setView(target.cx, target.cy, target.w);
      return;
    }
    const from = Object.assign({}, view);
    const started = performance.now();
    const step = function (now) {
      const t = clamp((now - started) / 450, 0, 1);
      const e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      // Interpolate the width on a log scale so zooming feels even.
      const w = Math.exp(Math.log(from.w) + (Math.log(target.w) - Math.log(from.w)) * e);
      setView(from.cx + (target.cx - from.cx) * e, from.cy + (target.cy - from.cy) * e, w);
      if (t < 1) flight = requestAnimationFrame(step);
      else clearTimeout(flightTimer);
    };
    flight = requestAnimationFrame(step);
    // If frames are paused the flight never runs, so land on the target once it should be over.
    flightTimer = setTimeout(function () {
      cancelAnimationFrame(flight);
      setView(target.cx, target.cy, target.w);
    }, 900);
  }

  function zoomAt(clientX, clientY, factor) {
    stopFlight();
    movedByHand = true;
    const scale = size.W / view.w;
    const h = view.w * (size.H / size.W);
    const ux = view.cx - view.w / 2 + (clientX - size.left) / scale;
    const uy = view.cy - h / 2 + (clientY - size.top) / scale;
    const maxW = widthToFit(full, CONFIG.margin);
    const minW = (full.x1 - full.x0) / CONFIG.maxZoom;
    const w = clamp(view.w * factor, minW, maxW);
    const k = w / view.w;
    setView(ux + (view.cx - ux) * k, uy + (view.cy - uy) * k, w);
  }

  // ---------- pointer input ----------

  const pointers = new Map();
  let drag = null;

  svg.addEventListener('pointerdown', function (e) {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    stopFlight();
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.size === 1) {
      drag = { x: e.clientX, y: e.clientY, cx: view.cx, cy: view.cy, moved: false, target: e.target };
    } else if (pointers.size === 2) {
      const pts = Array.from(pointers.values());
      drag = {
        pinch: true,
        moved: true,
        dist: Math.max(10, Math.hypot(pts[1].x - pts[0].x, pts[1].y - pts[0].y)),
        w: view.w,
      };
    }
  });

  window.addEventListener('pointermove', function (e) {
    if (!pointers.has(e.pointerId) || !drag) return;
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (drag.pinch) {
      if (pointers.size < 2) return;
      const pts = Array.from(pointers.values());
      const dist = Math.max(10, Math.hypot(pts[1].x - pts[0].x, pts[1].y - pts[0].y));
      const wanted = drag.w * (drag.dist / dist);
      zoomAt((pts[0].x + pts[1].x) / 2, (pts[0].y + pts[1].y) / 2, wanted / view.w);
      return;
    }
    const dx = e.clientX - drag.x;
    const dy = e.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) < 4) return;
    drag.moved = true;
    svg.classList.add('is-dragging');
    hideTooltip();
    const scale = size.W / view.w;
    movedByHand = true;
    setView(drag.cx - dx / scale, drag.cy - dy / scale, view.w);
  });

  function endPointer(e) {
    if (!pointers.has(e.pointerId)) return;
    pointers.delete(e.pointerId);
    const finished = drag;
    if (pointers.size === 0) {
      drag = null;
      svg.classList.remove('is-dragging');
    }
    if (finished && !finished.moved && !finished.pinch && e.type === 'pointerup') activate(finished.target, clickMode(e));
  }
  window.addEventListener('pointerup', endPointer);
  window.addEventListener('pointercancel', endPointer);

  svg.addEventListener(
    'wheel',
    function (e) {
      e.preventDefault();
      const delta = e.deltaMode === 1 ? e.deltaY * 30 : e.deltaY;
      zoomAt(e.clientX, e.clientY, Math.exp(delta * (e.ctrlKey ? 0.01 : 0.0018)));
    },
    { passive: false }
  );

  // ---------- soft, view and background clicks ----------
  //
  // Four clicks on the map, and the same four presses of Enter on a place reached with Tab. A
  // click does three things: it moves the view to the place, opens it into its parts, and chooses
  // it. Each modifier keeps some of them: Shift keeps the view's move, Cmd or Ctrl the opening.
  //                         moves the view   opens its parts   chooses
  //   click (hard)                yes              yes             yes
  //   Shift + Cmd/Ctrl: soft      yes              yes             -     one; the next replaces it
  //   Shift: view click           yes              -               -
  //   Cmd/Ctrl: background        -                yes             -     many, adding up
  // On a dot, the view's move centres it and there is nothing to open: a soft or view click
  // centres it, a background click does nothing, a click opens its entry. A background or soft
  // click on an open place lands on one of its parts and opens that. Any hard choice clears what
  // soft and background clicks opened; so does Esc at the whole map. A view click leaves them.

  // Where Ctrl with a click is the right-click (some systems), the browser opens its menu for it
  // instead; such a press is then not a background click (menuOpened, kept from the press on).
  let menuOpened = false;
  svg.addEventListener('pointerdown', () => (menuOpened = false), true);
  svg.addEventListener('contextmenu', () => (menuOpened = true));

  /** Which click a press with these keys held is: 'soft', 'view', 'background', 'none' or null
   *  (hard). */
  function clickMode(e) {
    const command = e.metaKey || e.ctrlKey;
    if (command && e.ctrlKey && menuOpened) return 'none';
    if (e.shiftKey) return command ? 'soft' : 'view';
    return command ? 'background' : null;
  }

  function softOpen(shape) {
    const unit = units.get(shape.getAttribute('data-id'));
    if (!unit) return;
    peeks.soft = unit.id;
    refreshMap();
    viewShape(shape);
  }

  function backgroundOpen(shape) {
    const unit = units.get(shape.getAttribute('data-id'));
    if (!unit || !opens(unit)) return;
    peeks.background.add(unit.id);
    refreshMap();
  }

  // Keys that background-click many places at once (hidden: no button or tip names them):
  //   A        every province
  //   B        every second-level place of each province open on the map in any way: chosen,
  //            soft-clicked or background-clicked, itself or a place inside it. A then B opens
  //            every one on the map (heavy: about 330 files of shapes); B straight after A works,
  //            since A marks the provinces open at once and B waits for the same files.

  function openAllProvinces() {
    for (const p of provinces) if (opens(p)) peeks.background.add(p.id);
    refreshMap();
  }

  function openAllCities() {
    const list = openProvinces();
    const round = peeks.round;
    for (const p of list) {
      if (!opens(p)) continue;
      peeks.background.add(p.id); // the province itself too, where its places open no further
      // A province's places are known once its own file is in; a hard choice meanwhile wins.
      loadKids(p).then(
        function () {
          if (peeks.round !== round) return;
          for (const kid of p.kids || []) if (opens(kid)) peeks.background.add(kid.id);
          refreshMap();
        },
        (error) => console.warn(error.message)
      );
    }
  }

  function clearPeeks() {
    peeks.soft = null;
    peeks.background.clear();
    peeks.round += 1;
    refreshMap();
  }

  /** A press that did not turn into a drag: open whatever was under it, as `mode` says. */
  function activate(target, mode) {
    if (!target || !target.closest) return;
    if (mode) {
      const dot = target.closest('.pt');
      const shape = dot ? null : target.closest('.unit, .base, .prov');
      if (mode === 'none') return;
      if (dot && mode !== 'background') {
        const box = boxOfDot(dot.getAttribute('data-id'));
        if (box) fitBox(box, 0, true);
      } else if (shape && mode === 'soft') softOpen(shape);
      else if (shape && mode === 'view') viewShape(shape);
      else if (shape) backgroundOpen(shape);
      if (dot || shape) return;
    }
    const pt = target.closest('.pt');
    if (pt) {
      const entry = points.get(pt.getAttribute('data-id'));
      if (entry) {
        const current = units.get(state.region);
        // keepItem: a place whose city has not been opened is selected once that city's file is in,
        // and the entry opened below must still be open then.
        if (!current || !recordIn(entry.record, current)) selectRegion(homeOf(entry.record, current), { fly: false, keepItem: true });
        openItem(entry.record.id, { fly: false });
      }
      return;
    }
    const shape = target.closest('.unit, .base, .prov');
    if (shape) selectRegion(shape.getAttribute('data-id'), { fly: true });
  }

  /**
   * The unit to select so that a record is listed in the panel. It stays at the level being
   * browsed: with one city of a province selected, a dot in another city selects that city, and
   * with a county selected, the county the dot is in. A record that is placed no further down
   * than a city selects the city.
   */
  function homeOf(record, current) {
    if (current && current.depth > 1 && provinceIdOf(current.id) === record.region) {
      for (const area of record.areas || []) {
        const path = [];
        for (let at = area; at; at = parentOf(at)) path.unshift(at);
        // `path` runs from the province down to the record's place, if every name on the way
        // has loaded. The unit may not have its shape yet; selectRegion fetches it.
        if (path[0] !== record.region || path.length < 2) continue;
        return path[Math.min(current.depth, path.length) - 1];
      }
    }
    return record.region;
  }

  for (const group of [gProvinces, gUnits]) {
    group.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      const shape = e.target.closest('.unit, .prov');
      if (!shape) return;
      e.preventDefault();
      // Enter with Shift and/or Cmd/Ctrl is a soft, view or background Enter, as those clicks are.
      menuOpened = false; // a key press opens no menu
      const mode = e.key === 'Enter' ? clickMode(e) : null;
      if (mode === 'soft') softOpen(shape);
      else if (mode === 'view') viewShape(shape);
      else if (mode === 'background') backgroundOpen(shape);
      else selectRegion(shape.getAttribute('data-id'), { fly: true });
    });
  }

  /** Bring a shape's place into view without choosing or opening it (a view click). */
  function viewShape(shape) {
    const unit = units.get(shape.getAttribute('data-id'));
    if (unit && unit.frame) fitBox(unit.frame, 0.35, true);
  }

  // The buttons zoom about the middle of the map in view: above the phone's sheet or left of the
  // wide screen's card, where it covers part of the map, as fitBox frames places.
  function zoomMiddle(factor) {
    const cover = SHEET ? sheetCover() : 0;
    const seen = cover > 0 && cover < size.H * 0.8 ? size.H - cover : size.H;
    const side = SHEET ? cardCover() : 0;
    const seenW = side > 0 && side < size.W * 0.8 ? size.W - side : size.W;
    zoomAt(size.left + seenW / 2, size.top + seen / 2, factor);
  }
  document.getElementById('zoom-in').addEventListener('click', () => zoomMiddle(1 / 1.6));
  document.getElementById('zoom-out').addEventListener('click', () => zoomMiddle(1.6));
  document.getElementById('zoom-reset').addEventListener('click', () => fitBox(home, CONFIG.margin, true));

  // ---------- hover ----------

  function showTooltip(e, lines) {
    tooltip.textContent = '';
    lines.forEach(function (line, i) {
      tooltip.append(el(i === 0 ? 'strong' : 'span', { text: line }));
    });
    tooltip.hidden = false;
    const wrap = mapWrap.getBoundingClientRect();
    const box = tooltip.getBoundingClientRect();
    let x = e.clientX - wrap.left + 14;
    let y = e.clientY - wrap.top + 14;
    if (x + box.width > wrap.width - 8) x = e.clientX - wrap.left - box.width - 14;
    if (y + box.height > wrap.height - 8) y = e.clientY - wrap.top - box.height - 14;
    tooltip.style.transform = 'translate(' + Math.max(8, x) + 'px,' + Math.max(8, y) + 'px)';
  }

  function hideTooltip() {
    tooltip.hidden = true;
  }

  /**
   * Where a record is, as text, seen from a unit that contains it: the names of its places below
   * that unit. Places whose names have not loaded yet are left out.
   */
  function whereText(record, top) {
    const names = [];
    for (const area of record.areas || []) {
      const text = pathBelow(area, top);
      if (text) names.push(text);
    }
    if (names.length > 3) return t('where.more', { list: names.slice(0, 3).join('、'), n: names.length - 3, total: names.length });
    return names.join('、');
  }

  /**
   * The body a heritage entry is filed under, when it is an organisation. Most entries are filed
   * under a place, which `whereText` already gives.
   */
  function filedUnder(record) {
    return record.body ? record.place : '';
  }

  /**
   * The line under an entry's name in a list: where it is and who stands behind it. Every list
   * uses this, so an entry reads the same wherever it is met. `options.top` is the unit the
   * place is named from; `options.lead` goes in front; `options.kind` false leaves the kind out,
   * for a list whose entries are all of one kind.
   * A product's applicant is left out when it is the government of the place just named.
   */
  function detailLine(record, layer, options) {
    const o = options || {};
    const parts = [o.lead];
    if (layer && layer.key === 'heritage' && o.kind !== false) parts.push(kindName('heritage', record.kind));
    if (layer && o.top) parts.push(whereText(record, o.top));
    // A product's year is the earliest the sources give: the notice it replaces, or its own.
    if (layer && layer.key === 'products') parts.push(record.gov ? '' : record.applicant, record.earlier || record.since);
    if (layer && layer.key === 'heritage') parts.push(filedUnder(record), levelName(record), record.since);
    if (layer && layer.key === 'farm') parts.push(record.since);
    return parts.filter(Boolean).join(' · ');
  }

  /** The level of a heritage entry, named only where it is not the national register. */
  function levelName(record) {
    const key = 'heritage.level.' + record.level;
    return record.level && TEXT.has(key) ? t(key) : '';
  }

  function recordSummary(entry) {
    const r = entry.record;
    const lines = [r.title, entry.layer.one];
    lines.push(regionName(r.region) + whereText(r, r.region));
    if (filedUnder(r)) lines.push(filedUnder(r));
    if (levelName(r)) lines.push(levelName(r));
    // The bare year, as in the lists: for a product, the earliest the sources give.
    if (r.since) lines.push(String(r.earlier || r.since));
    return lines;
  }

  /**
   * One line per category that has records in a unit: "38 protected regional products". Only
   * the categories switched on are counted, so the lines match what the map shows.
   */
  function countLines(unit) {
    const lines = [];
    for (const layer of LAYERS) {
      if (!layerVisible(layer)) continue;
      const n = unit.depth === 1 ? countOf(unit, layer.key) : recordsIn(layer, unit).length;
      if (n) lines.push(t('layer.' + layer.key + '.count', { n: n }));
    }
    return lines.length ? lines : [t(state.hidden.size ? 'count.noneShown' : 'count.none')];
  }

  let hovered = { id: null, lines: [] }; // the last unit hovered, so its counts are worked out once

  svg.addEventListener('pointermove', function (e) {
    if (drag && drag.moved) return;
    const pt = e.target.closest ? e.target.closest('.pt') : null;
    if (pt) {
      const entry = points.get(pt.getAttribute('data-id'));
      if (entry) showTooltip(e, recordSummary(entry));
      return;
    }
    const part = e.target.closest ? e.target.closest('.unit') : null;
    if (part) {
      const unit = units.get(part.getAttribute('data-id'));
      if (hovered.id !== unit.id) hovered = { id: unit.id, lines: countLines(unit) };
      const lines = [fullName(unit)];
      const metric = currentMetric();
      if (metric) {
        // The numbers that shade the map exist for whole provinces only.
        const province = chainOf(unit.id)[0];
        const v = metric.values.get(province.id);
        lines.push(t('tip.whole', { place: province.name, value: v == null ? t('value.none') : t('value.kg', { v: formatNumber(v) }), food: foodName(metric.column) }));
      }
      showTooltip(e, lines.concat(hovered.lines));
      return;
    }
    const prov = e.target.closest ? e.target.closest('.prov') : null;
    if (prov) {
      const p = provinceById.get(prov.getAttribute('data-id'));
      if (hovered.id !== p.id) hovered = { id: p.id, lines: countLines(p) };
      const lines = [];
      const metric = currentMetric();
      if (metric) {
        const v = metric.values.get(p.id);
        lines.push(v == null ? t('value.noneCap') : t('value.kg', { v: formatNumber(v) }));
        lines.push(fullName(p) + ' · ' + foodName(metric.column));
      } else {
        lines.push(fullName(p));
      }
      showTooltip(e, lines.concat(hovered.lines, [t('tip.open')]));
      return;
    }
    hideTooltip();
  });
  svg.addEventListener('pointerleave', hideTooltip);

  // ---------- shading provinces by a number ----------

  function currentMetric() {
    if (!state.metric) return null;
    const columns = DATA.indicators.columns;
    const index = columns.findIndex((c) => c.key === state.metric);
    if (index < 0) return null;
    const values = new Map();
    let min = Infinity;
    let max = -Infinity;
    for (const p of provinces) {
      const row = DATA.indicators.rows[p.id];
      if (!row) continue;
      values.set(p.id, row[index]);
      if (row[index] < min) min = row[index];
      if (row[index] > max) max = row[index];
    }
    return { column: columns[index], index: index, values: values, min: min, max: max, national: DATA.indicators.national[index] };
  }

  function applyMetric() {
    const metric = currentMetric();
    for (const p of provinces) {
      let fill = '';
      let dark = false;
      let noData = false;
      if (metric) {
        const v = metric.values.get(p.id);
        if (v == null) {
          noData = true;
        } else {
          const t = metric.max > metric.min ? (v - metric.min) / (metric.max - metric.min) : 0.5;
          fill = rampColor(t);
          dark = t > 0.5;
        }
      }
      p.path.style.fill = fill;
      p.path.classList.toggle('no-data', noData);
      p.label.classList.toggle('on-dark', dark);
      p.dark = dark;
    }
    shadeOpen();
    svg.classList.toggle('has-metric', Boolean(metric));
  }

  /** An opened unit is drawn by its detailed outline, which takes on its province's shading. */
  function shadeOpen() {
    for (const [id, parts] of drawn) {
      const province = chainOf(id)[0];
      parts.labels.classList.toggle('on-dark', Boolean(province.dark));
      parts.base.style.fill = province.path.style.fill;
      parts.base.classList.toggle('no-data', province.path.classList.contains('no-data'));
    }
  }

  // ---------- legend ----------

  // On a phone the legend shows only the shading's scale, since the switches above the map already
  // show the colours of the dots, and the reader may fold it away.
  let legendFolded = false;

  function renderLegend() {
    legend.textContent = '';
    legend.classList.toggle('has-metric', Boolean(currentMetric()));
    legend.classList.toggle('is-folded', legendFolded);
    legend.append(
      el('button', {
        type: 'button',
        class: 'legend-fold',
        text: legendFolded ? t('legend.label') : t('legend.fold'),
        'aria-expanded': String(!legendFolded),
        onclick: function () {
          legendFolded = !legendFolded;
          renderLegend();
        },
      })
    );
    const list = el('ul', { class: 'legend-layers' });
    for (const layer of LAYERS) {
      const placed = placedCount(layer);
      const item = el(
        'li',
        { class: layerVisible(layer) ? '' : 'is-off' },
        el('span', { class: 'swatch swatch-' + layer.key }),
        el('span', { class: 'legend-name', text: layer.label }),
        el('span', { class: 'legend-count', text: String(placed) })
      );
      list.append(item);
    }
    legend.append(list);
    const metric = currentMetric();
    if (metric) {
      const block = el('div', { class: 'legend-metric' });
      block.append(el('div', { class: 'legend-title', text: t('legend.metric', { food: foodName(metric.column), year: DATA.indicators.year }) }));
      const bar = el('div', { class: 'ramp' });
      bar.style.background = 'linear-gradient(to right,' + RAMP.join(',') + ')';
      block.append(bar);
      block.append(el('div', { class: 'ramp-ends' }, el('span', { text: formatNumber(metric.min) }), el('span', { text: formatNumber(metric.max) })));
      block.append(el('div', { class: 'legend-nodata' }, el('span', { class: 'swatch swatch-nodata' }), el('span', { text: t('value.noneCap') })));
      legend.append(block);
    }
  }

  // ---------- side panel ----------

  function worksFor(records, extra) {
    const ids = new Set(extra || []);
    for (const r of records) for (const ref of r.refs || []) ids.add(ref.w);
    return Array.from(ids);
  }

  function sourceList(ids) {
    const list = el('ul', { class: 'sources' });
    for (const id of ids) {
      const w = DATA.works[id];
      if (!w) continue;
      const item = el('li');
      const title = CHINESE ? w.zh : w.en;
      const note = CHINESE ? w.noteZh : w.note;
      if (w.url) item.append(el('a', { href: w.url, target: '_blank', rel: 'noopener', text: title }));
      else item.append(el('span', { text: title }));
      if (note) item.append(el('span', { class: 'source-note', text: ' ' + note }));
      list.append(item);
    }
    return list;
  }

  function section(title, count) {
    const head = el('h3', null, el('span', { text: title }));
    if (count != null) head.append(el('span', { class: 'count', text: String(count) }));
    return el('section', { class: 'panel-section' }, head);
  }

  /**
   * A table of food supply per person from a food balance sheet (DATA.supply). `areas` is the
   * list of columns, each {key, label}. With `difference`, a last column sets the first area
   * against the second. These figures are for the panel only: the food names are plain text,
   * because the map is never shaded by them.
   */
  function supplyTable(table, areas, difference) {
    const out = el('table', { class: 'eat' });
    const head = el('tr', null, el('th', { text: t('eat.food') }));
    for (const area of areas) head.append(el('th', { class: 'num', text: area.label }));
    if (difference) head.append(el('th', { class: 'num', text: t('eat.difference') }));
    out.append(el('thead', null, head));
    const body = el('tbody');
    table.columns.forEach(function (c, i) {
      const tr = el('tr', { class: c.partOf ? 'sub' : '' }, el('td', { text: foodName(c) }));
      areas.forEach(function (area, at) {
        tr.append(el('td', { class: 'num' + (difference && at ? ' muted' : ''), text: formatNumber(table.areas[area.key][i]) }));
      });
      if (difference) {
        const own = table.areas[areas[0].key][i];
        const other = table.areas[areas[1].key][i];
        const diff = other ? Math.round(((own - other) / other) * 100) : 0;
        tr.append(el('td', { class: 'num', text: (diff > 0 ? '+' : diff < 0 ? '−' : '') + Math.abs(diff) + '%' }));
      }
      body.append(tr);
    });
    out.append(body);
    return out;
  }

  /** A place's name as the heading of a column of figures: short in Chinese, English otherwise. */
  function columnName(place) {
    return CHINESE || !place.en ? place.short : place.en;
  }

  /** The areas of the comparison table that are places on the map, in the table's own order. */
  function supplyAreas(table) {
    return Object.keys(table.areas).map(function (key) {
      const p = provinceById.get(key);
      return { key: key, label: p ? columnName(p) : t('supply.mainland') };
    });
  }

  function recordButton(record, meta) {
    const entry = points.get(record.id);
    const item = el('li', { class: record.id === state.focus ? 'is-focus' : '' });
    // An entry with no dot of its own (one placed only at its province, or at Hong Kong or Macau
    // as a whole) can still be picked: it is marked in the list and its place is framed.
    item.append(
      el('button', {
        type: 'button',
        class: 'rec',
        text: record.title,
        title: t(entry ? 'record.show' : 'record.show.unplaced'),
        onclick: () => openItem(record.id, { fly: true }),
      })
    );
    if (meta) item.append(el('span', { class: 'meta', text: meta }));
    return item;
  }

  function renderOverview() {
    panel.textContent = '';
    panel.append(el('h2', { text: t('overview.title') }));
    panel.append(
      el('p', {
        class: 'lede',
        text: t('overview.lede'),
      })
    );
    const stats = el('ul', { class: 'stats' });
    // Same names and the same order as the legend, with dishes first.
    const figures = [[nationalCount('dishes'), DISHES.label]].concat(LAYERS.map((layer) => [nationalCount(layer.key), layer.label]));
    for (const f of figures) stats.append(el('li', null, el('strong', { text: String(f[0]) }), el('span', { text: f[1].toLowerCase() })));
    panel.append(stats);

    const metric = currentMetric();
    if (metric) {
      const sec = section(t('overview.metric.title', { food: foodName(metric.column), year: DATA.indicators.year }), null);
      sec.append(el('p', { class: 'hint', text: t('overview.metric.hint', { v: formatNumber(metric.national) }) }));
      const table = el('table', { class: 'rank' });
      const body = el('tbody');
      const ranked = provinces.filter((p) => metric.values.has(p.id)).sort((a, b) => metric.values.get(b.id) - metric.values.get(a.id));
      ranked.forEach(function (p, i) {
        body.append(
          el(
            'tr',
            null,
            el('td', { class: 'num', text: String(i + 1) }),
            el('td', null, el('button', { type: 'button', class: 'rec', text: fullName(p), onclick: () => selectRegion(p.id, { fly: true }) })),
            el('td', { class: 'num', text: formatNumber(metric.values.get(p.id)) })
          )
        );
      });
      table.append(body);
      sec.append(table);
      panel.append(sec);
    }

    // The mainland, Hong Kong, Macau and Taiwan side by side, from one food balance sheet.
    const fao = DATA.supply.compared;
    const eat = section(t('eat.title'), null);
    eat.append(el('p', { class: 'hint', text: t('supply.compare.hint', { year: fao.year }) }));
    eat.append(supplyTable(fao, supplyAreas(fao), false));
    eat.append(el('p', { class: 'hint', text: t('supply.compare.note') }));
    panel.append(eat);

    const about = section(t('overview.about.title'), null);
    about.append(
      el('p', {
        class: 'hint',
        text: t('overview.about.text'),
      })
    );
    about.append(el('p', { class: 'hint', text: t('overview.about.disclaimer') }));
    about.append(
      el(
        'p',
        { class: 'hint' },
        t('overview.about.repo') + GAP,
        el('a', { href: CONFIG.repository, target: '_blank', rel: 'noopener', text: t('overview.about.repoLink') })
      )
    );
    panel.append(about);

    // Every source, in a section of its own, as on a place's panel and an entry's page.
    const sources = section(t('sources.title'), null);
    sources.append(sourceList(Object.keys(DATA.works)));
    panel.append(sources);
  }

  /** The places a unit divides into, each with the number of records there. */
  function placesSection(unit, province, records) {
    const sec = section(t('places.title'), unit.n);
    if (opens(unit) && !unit.kids) {
      sec.append(el('p', { class: 'hint', text: t('common.loading') }));
      return sec;
    }
    const parts = partsOf(unit);
    if (!parts.length) {
      sec.append(el('p', { class: 'hint', text: t('places.failed') }));
      return sec;
    }
    const counts = tallyOf(province);
    const list = el('ul', { class: 'places', lang: NAMES_TAG });
    for (const part of parts) {
      const n = counts.get(part.id) || 0;
      const name = el('span', { text: part.short });
      const count = el('span', { class: 'n', text: String(n) });
      // A place can be opened only if the page has its shape.
      const chip = units.has(part.id)
        ? el('button', { type: 'button', title: part.name, onclick: () => selectRegion(part.id, { fly: true }) }, name, count)
        : el('span', { title: part.name }, name, count);
      list.append(el('li', { class: n ? '' : 'is-empty' }, chip));
    }
    sec.append(list);
    const loose = records.filter((r) => (r.areas || []).every((area) => area === unit.id)).length;
    let note = t('places.note');
    if (loose) note += GAP + t('places.loose', { n: loose, place: unit.name });
    sec.append(el('p', { class: 'hint', text: note }));
    return sec;
  }

  /** The panel for a selected unit: a province, or a place inside one. */
  function renderPlace(unit) {
    const province = chainOf(unit.id)[0];
    const top = unit.depth === 1;
    const dishes = top ? recordsOf(unit.id, 'dishes') : [];
    const found = {};
    for (const layer of LAYERS) found[layer.key] = recordsIn(layer, unit);
    const all = found.products.concat(found.heritage, found.farm);
    placeCount = all.length;

    panel.textContent = '';
    const title = el('div', { class: 'panel-title' });
    if (!top) {
      const up = units.get(unit.parent);
      title.append(backLine(fullName(up), () => selectRegion(up.id, { fly: true })));
    }
    title.append(el('h2', null, el('span', { lang: NAMES_TAG, text: unit.name }), unit.en && !CHINESE ? el('span', { class: 'en', text: englishName(unit.en, unit.tag) }) : null));
    if (kindName('unit', unit.kind)) title.append(el('p', { class: 'kind', text: kindName('unit', unit.kind) }));
    panel.append(
      el('div', { class: 'panel-head' }, title, el('button', { type: 'button', class: 'close', 'aria-label': t('place.close'), onclick: () => selectRegion(null, { fly: false }) }, crossIcon()))
    );

    if (!store.has(province.id)) {
      // The province's records are still on their way. The panel is drawn again when they arrive.
      panel.append(el('p', { class: 'lede', text: province.noRecords ? t('place.failed', { place: province.name }) : t('common.loading') }));
      return;
    }

    if (unit.n) panel.append(placesSection(unit, province, all));
    if (!top && !all.length) panel.append(el('p', { class: 'lede', text: t('place.empty', { place: unit.name }) }));

    if (dishes.length) {
      const sec = section(DISHES.label, dishes.length);
      const list = el('ul', { class: 'chips', lang: NAMES_TAG });
      for (const d of dishes) list.append(el('li', null, el('button', { type: 'button', class: 'rec', text: d.title, onclick: () => openItem(d.id, { fly: false }) })));
      sec.append(list);
      sec.append(el('p', { class: 'hint', text: t('dishes.hint') }));
      panel.append(sec);
    }

    // The three dot categories follow, in the same order as the switches and the legend.
    if (found.products.length) {
      const sec = section(LAYER.products.label, found.products.length);
      const list = el('ul', { class: 'records', lang: NAMES_TAG });
      for (const r of found.products) list.append(recordButton(r, detailLine(r, LAYER.products, { top: unit.id })));
      sec.append(list);
      sec.append(el('p', { class: 'hint', text: t('products.hint') }));
      panel.append(sec);
    }

    if (found.heritage.length) {
      const sec = section(LAYER.heritage.label, found.heritage.length);
      const list = el('ul', { class: 'records', lang: NAMES_TAG });
      for (const r of found.heritage) list.append(recordButton(r, detailLine(r, LAYER.heritage, { top: unit.id })));
      sec.append(list);
      panel.append(sec);
    }

    if (found.farm.length) {
      const sec = section(LAYER.farm.label, found.farm.length);
      const list = el('ul', { class: 'records', lang: NAMES_TAG });
      for (const r of found.farm) list.append(recordButton(r, detailLine(r, LAYER.farm, { top: unit.id })));
      sec.append(list);
      panel.append(sec);
    }

    const row = top ? DATA.indicators.rows[unit.id] : null;
    if (top) {
      const eat = section(t('eat.title'), null);
      if (row) {
        eat.append(el('p', { class: 'hint', text: t('eat.hint', { year: DATA.indicators.year }) }));
        const table = el('table', { class: 'eat' });
        table.append(el('thead', null, el('tr', null, el('th', { text: t('eat.food') }), el('th', { class: 'num', text: columnName(unit) }), el('th', { class: 'num', text: t('eat.national') }), el('th', { class: 'num', text: t('eat.difference') }))));
        const body = el('tbody');
        DATA.indicators.columns.forEach(function (c, i) {
          const national = DATA.indicators.national[i];
          const diff = national ? Math.round(((row[i] - national) / national) * 100) : 0;
          const tr = el(
            'tr',
            { class: (c.partOf ? 'sub ' : '') + (c.key === state.metric ? 'is-metric' : '') },
            el('td', null, el('button', { type: 'button', class: 'rec', text: foodName(c), title: t('eat.shade'), onclick: () => setMetric(c.key) })),
            el('td', { class: 'num', text: formatNumber(row[i]) }),
            el('td', { class: 'num muted', text: formatNumber(national) }),
            el('td', { class: 'num', text: (diff > 0 ? '+' : diff < 0 ? '−' : '') + Math.abs(diff) + '%' })
          );
          body.append(tr);
        });
        table.append(body);
        eat.append(table);
      } else if (DATA.supply.taiwan.areas[unit.id]) {
        // Taiwan: its own food balance sheet.
        const own = DATA.supply.taiwan;
        eat.append(el('p', { class: 'hint', text: t('supply.taiwan.hint', { year: own.year }) }));
        eat.append(supplyTable(own, [{ key: unit.id, label: t('supply.kg') }], false));
        eat.append(el('p', { class: 'hint', text: t('supply.taiwan.note', { year: own.year }) }));
        eat.append(sourceList(own.refs.map((ref) => ref.w)));
      } else if (DATA.supply.compared.areas[unit.id]) {
        // Hong Kong and Macau: FAO's sheet, beside the mainland's figure from the same sheet.
        const fao = DATA.supply.compared;
        eat.append(el('p', { class: 'hint', text: t('supply.hint', { year: fao.year }) }));
        eat.append(supplyTable(fao, [{ key: unit.id, label: columnName(unit) }, { key: 'mainland', label: t('supply.mainland') }], true));
        eat.append(el('p', { class: 'hint', text: t('supply.note') }));
        eat.append(sourceList(fao.refs.map((ref) => ref.w)));
      } else {
        eat.append(el('p', { class: 'hint', text: t('eat.missing', { place: CHINESE ? unit.name : unit.en }) }));
      }
      panel.append(eat);
    } else {
      // What is recorded for a wider place applies here too, and is one step away.
      const up = units.get(unit.parent);
      if (up.depth > 1) {
        let wide = 0;
        for (const layer of LAYERS) wide += recordsIn(layer, up).filter((r) => (r.areas || []).indexOf(up.id) !== -1).length;
        if (wide) {
          panel.append(
            el(
              'p',
              { class: 'hint aside' },
              t('places.loose', { n: wide, place: up.name }) + GAP,
              el('button', { type: 'button', class: 'rec', text: t('place.see', { place: up.name }), onclick: () => selectRegion(up.id, { fly: true }) })
            )
          );
        }
      }
      // Dishes and the eating table are recorded for whole provinces only.
      panel.append(
        el(
          'p',
          { class: 'hint aside' },
          t('place.whole', { place: province.name }) + GAP,
          el('button', { type: 'button', class: 'rec', text: t('place.see', { place: fullName(province) }), onclick: () => selectRegion(province.id, { fly: true }) })
        )
      );
    }

    const src = section(t('sources.title'), null);
    src.append(sourceList(worksFor(dishes.concat(all), row ? ['nbs-yearbook-2025'] : [])));
    if (dishes.length || all.length || row) panel.append(src);
  }

  // ---------- an entry's own page ----------
  //
  // The page is a run of parts, each drawn only when the entry has something for it, so a new
  // part (a picture, a season) is one more block here and one more field in the data. An
  // introduction is already provided for: data/intros.json, which the build puts in the
  // province's file of details.

  const RELATED_SHOWN = 10;

  /** The places an entry belongs to, as buttons that open them. */
  function placeButtons(record) {
    const holder = el('span', { class: 'places', lang: NAMES_TAG });
    const province = provinceById.get(record.region);
    const add = (id, text) => holder.append(el('button', { type: 'button', class: 'rec', text: text, onclick: () => selectRegion(id, { fly: true }) }));
    for (const area of record.areas || []) {
      const text = area === record.region ? '' : pathBelow(area, record.region);
      if (text) add(area, text);
    }
    if (!holder.childNodes.length) add(province.id, fullName(province));
    return holder;
  }

  /** What to say about an entry's dot, where it is not simply the position its source gives. */
  function dotNote(entry) {
    const r = entry.record;
    if (!entry.layer) return '';
    if (!r.coord) return t('item.dot.none', { place: whereText(r, r.region) || regionName(r.region) });
    if (r.toward) {
      const named = place(r.toward);
      if (named) return t('item.dot.toward', { place: fullName(named, true) });
    }
    if (r.pulled) return t('item.dot.pulled');
    if (r.unused) return t('item.dot.unused');
    return r.approx ? t('item.dot.centre') : '';
  }

  /** A list of other entries, the first few of them, under a heading with their number. */
  function relatedSection(title, records, metaOf) {
    const sec = section(title, records.length);
    const list = el('ul', { class: 'records', lang: NAMES_TAG });
    for (const r of records.slice(0, RELATED_SHOWN)) list.append(recordButton(r, metaOf ? metaOf(r) : ''));
    sec.append(list);
    if (records.length > RELATED_SHOWN) sec.append(el('p', { class: 'hint', text: t('item.more', { n: records.length - RELATED_SHOWN }) }));
    return sec;
  }

  function renderItem(entry, from) {
    const r = entry.record;
    const layer = entry.layer;
    const own = store.get(r.region);
    const category = layer ? layer.one : DISHES.one;
    const kind = layer && layer.key === 'heritage' ? kindName('heritage', r.kind) : '';

    panel.textContent = '';
    const title = el('div', { class: 'panel-title' });
    title.append(backLine(fullName(from), closeItem));
    title.append(el('h2', null, el('span', { lang: NAMES_TAG, text: r.title })));
    title.append(el('p', { class: 'kind', text: kind ? category + ' · ' + kind : category }));
    panel.append(
      el('div', { class: 'panel-head' }, title, el('button', { type: 'button', class: 'close', 'aria-label': t('back.to', { place: fullName(from) }), onclick: closeItem }, crossIcon()))
    );

    // An introduction, when one has been written. It arrives with the details below.
    const intro = el('div');
    panel.append(intro);

    const facts = el('dl', { class: 'facts' });
    const fact = function (label, value) {
      if (value == null || value === '') return;
      facts.append(el('dt', { text: label }), typeof value === 'string' ? el('dd', { lang: NAMES_TAG, text: value }) : el('dd', null, value));
    };
    const year = r.since || r.listed;
    if (year) fact(t(layer && layer.key === 'products' ? 'item.since.products' : 'item.since'), String(year));
    if (r.earlier) fact(t('item.earlier'), String(r.earlier));
    if (layer && layer.key === 'heritage') fact(t('item.register'), levelName(r) || t('item.level.national'));
    if (r.batch) fact(t('item.batch'), t('item.batch.value', { n: r.batch }));
    fact(t('item.place'), placeButtons(r));
    if (r.place) fact(t('item.filed'), r.place);
    if (r.applicant) fact(t(r.id.indexOf('tw-mark:') === 0 ? 'item.holder' : 'item.applicant'), r.applicant);
    const written = sourceNames.get(r.id);
    // Shown where the source's wording is not what the page shows: a Traditional name in an
    // interface that writes Simplified.
    if (ownScript.has(r.id) && written !== r.title) facts.append(el('dt', { text: t('item.own') }), el('dd', { text: written }));
    fact(t('item.loc'), (r.refs || []).map((ref) => ref.loc).filter(Boolean).join('；'));
    panel.append(facts);

    const note = dotNote(entry);
    if (note) panel.append(el('p', { class: 'hint', text: note }));

    // Other entries in the same places, and of the same kind in the province.
    const here = (r.areas || []).filter((area) => area !== r.region);
    if (layer && here.length) {
      const near = [];
      for (const other of LAYERS) {
        for (const x of own[other.key]) {
          if (x !== r && timeline.accepts(x) && (x.areas || []).some((area) => here.indexOf(area) !== -1)) near.push({ record: x, layer: other });
        }
      }
      // The category leads, as the list mixes them. The place is named only for an entry that
      // is not in exactly the places of this one.
      const same = (x) => (x.areas || []).join() === (r.areas || []).join();
      const lines = new Map(near.map((x) => [x.record, detailLine(x.record, x.layer, { lead: x.layer.one, top: same(x.record) ? null : r.region })]));
      if (near.length) panel.append(relatedSection(t('item.near', { place: whereText(r, r.region) }), near.map((x) => x.record), (x) => lines.get(x)));
    }
    const key = layer ? layer.key : 'dishes';
    if (!layer || r.kind) {
      const alike = own[key].filter((x) => x !== r && (!layer || (x.kind === r.kind && timeline.accepts(x))));
      const where = (x) => detailLine(x, layer, { top: x.region, kind: false });
      if (alike.length) panel.append(relatedSection(t('item.alike', { place: regionName(r.region) }), alike, where));
    }

    const src = section(t('sources.title'), null);
    const sources = el('div');
    sources.append(sourceList(worksFor([r])));
    src.append(sources);
    panel.append(src);

    loadDetails(r.region).then(function (all) {
      const more = all[r.id];
      if (!more || state.item !== r.id || !facts.isConnected) return;
      if (more.intro) {
        const sec = section(t('item.intro'), null);
        sec.append(el('p', { class: 'lede', text: CHINESE ? more.intro.zh : more.intro.en }));
        intro.append(sec);
        sources.textContent = '';
        sources.append(sourceList(worksFor([r, more.intro])));
      }
      fact(t('item.listedBy'), r.listed_by || more.listed_by); // the record's own is as written, in English
      if (more.marks) {
        const list = el('ul', { class: 'plain' });
        for (const mark of more.marks) list.append(el('li', { text: mark }));
        fact(t('item.marks'), list);
      }
      fact(t('item.area'), more.area);
      fact(t('item.remark'), more.remark);
    });
  }

  /** Show an entry's own page, and mark the entry on the map as `focusRecord` does. */
  function openItem(id, options) {
    state.item = id;
    focusRecord(id, options);
    syncUrl();
  }

  /** Leave an entry's page for the place it was opened from. The entry stays marked. */
  function closeItem() {
    state.item = null;
    renderPanel();
    revealFocus();
    syncUrl();
  }

  /** The province of an entry, looked up by id in the search file. Rejects if it is not there. */
  function provinceOfItem(id) {
    loadSearch();
    return searchLoad.then(function () {
      const file = window.FOODMAP_SEARCH;
      for (const province of Object.keys((file && file.records) || {})) {
        if (file.records[province].some((row) => row[2] === id)) return province;
      }
      throw new Error('no entry ' + id);
    });
  }

  /**
   * The place an entry is shown at: the lowest unit that holds every unit it belongs to. An entry
   * in one county is shown at that county, one in several counties of a city at the city, and one
   * placed at its province only, such as a dish, at the province. Needs the province's file,
   * which says what each place lies in.
   */
  function placeOf(record) {
    const areas = record.areas || [];
    if (!areas.length) return record.region;
    for (let at = areas[0]; at; at = parentOf(at)) {
      if (areas.every((area) => within(area, at))) return at;
    }
    return record.region;
  }

  /**
   * Open the page of an entry by its id, from the address or from search. The place in the
   * address is tried first only because it says which province's file to fetch.
   * From the address, the place it names is kept if it holds the entry; otherwise, and always
   * from search, the entry's own place is selected (placeOf).
   */
  function showItem(id, options) {
    const fromSearch = Boolean(options && options.search);
    const settle = function (provinceId) {
      const province = provinceById.get(provinceId);
      if (!province) throw new Error('no entry ' + id);
      return loadRecords(province).then(function () {
        const entry = entryById.get(id);
        if (!entry || entry.record.region !== provinceId) throw new Error('no entry ' + id);
        // What each place lies in comes with the province's file. Without it, placeOf falls
        // back on the province.
        const unit = units.get(provinceId);
        return unit && opens(unit) ? loadKids(unit).catch(() => null) : null;
      });
    };
    const hinted = chainOf(state.region)[0];
    (hinted ? settle(hinted.id) : Promise.reject())
      .catch(() => provinceOfItem(id).then(settle))
      .then(
        function () {
          if (state.item !== id) return; // something else was picked meanwhile
          const record = entryById.get(id).record;
          const unit = units.get(state.region);
          if (fromSearch) {
            // A record with a dot moves the map to the dot, so the flight to its place is skipped.
            selectRegion(placeOf(record), { fly: !recordById.has(id), keepItem: true });
            openItem(id, { fly: true });
            return;
          }
          if (!unit || !recordIn(record, unit)) selectRegion(placeOf(record), { jump: true, keepItem: true });
          openItem(id, { fly: false });
        },
        function (error) {
          console.warn(error.message);
          if (state.item !== id) return;
          state.item = null;
          renderPanel();
          syncUrl();
        }
      );
  }

  let panelShows = null; // what the panel last showed, so a redraw of the same thing keeps its scroll position
  let listScroll = null; // { key, top }: where a place's panel was when an entry's page took its place

  function renderPanel() {
    const unit = units.get(state.region) || null;
    const entry = unit && state.item ? entryById.get(state.item) : null;
    const item = entry && entry.record.region === provinceIdOf(unit.id) ? entry : null;
    const key = item ? 'item ' + item.record.id : unit ? unit.id : '';
    const wasItem = typeof panelShows === 'string' && panelShows.indexOf('item ') === 0;
    if (item && panelShows !== null && !wasItem) listScroll = { key: panelShows, top: panel.scrollTop };
    let scroll = key === panelShows ? panel.scrollTop : 0;
    if (!item && wasItem && listScroll && listScroll.key === key) scroll = listScroll.top;
    if (item) renderItem(item, unit);
    else if (unit) renderPlace(unit);
    else renderOverview();
    panelShows = key;
    panel.scrollTop = scroll;
    barText = item ? item.record.title : unit ? t('bar.place', { name: fullName(unit, true), n: placeCount }) : '';
    syncBar();
  }

  /** Bring the focused record's row into view, where the panel scrolls on its own. */
  function revealFocus() {
    const row = panel.querySelector('li.is-focus');
    if (row && getComputedStyle(panel).overflowY !== 'visible') row.scrollIntoView({ block: 'nearest' });
  }

  function renderTrail() {
    const chain = chainOf(state.region);
    trail.textContent = '';
    trail.hidden = !chain.length;
    if (!chain.length) return;
    const list = el('ol');
    // Each item names its key (0 for China, then 1, 2, 3 down the levels; R for the last).
    list.append(el('li', null, el('button', { type: 'button', text: t('trail.root'), title: t('trail.go', { place: t('trail.root'), key: '0' }), onclick: () => selectRegion(null, { fly: true }) })));
    chain.forEach(function (unit, i) {
      // The place being shown has its full name; the places above it have their short ones.
      // Neither carries the tag of a shared English name: the trail itself shows where it is.
      if (i === chain.length - 1) {
        // A button too: it brings the view back to this place as it was first shown, after
        // the map has been moved or zoomed. The Reset button, by contrast, shows the whole map.
        list.append(
          el(
            'li',
            { 'aria-current': 'location' },
            el('button', {
              type: 'button',
              text: fullName(unit, true),
              title: t('trail.reframe', { place: fullName(unit, true) }),
              onclick: function () {
                if (unit.frame) fitBox(unit.frame, 0.35, true);
              },
            })
          )
        );
      } else {
        // Just above a place of the same name, or named like a province, a longer form tells
        // them apart (namesakeName). Provinces never have one: 吉林 Jilin above 吉林市.
        const label = chain[i + 1].namesake || unit.likeProvince ? namesakeName(unit) : briefName(unit);
        list.append(el('li', null, el('button', { type: 'button', text: label, title: t('trail.go', { place: label, key: String(i + 1) }), onclick: () => selectRegion(unit.id, { fly: true }) })));
      }
    });
    trail.append(list);
  }
  // ========== on a phone, and the modern layout ==========
  //
  // The sections from here to "actions" serve narrow screens, where the panel lies below or over
  // the map rather than beside it, and the modern layout on any screen: the bar between the map
  // and the panel (the simple layout on a phone), the modern layout (a sliding sheet on a phone, a
  // floating card on a wide screen), the options button and its layer, and the search button.
  // Elsewhere: fitBox and zoomMiddle (camera) frame and zoom in the part of the map the sheet or
  // the card leaves in view, and the legend (legend) folds on a phone. Comments that begin "a
  // mobile browser may" name behaviour of mobile browsers that the code works around.

  // ---------- phone: the bar between the map and the panel (simple layout) ----------

  // The panel lies below the map on a narrow screen. Once a place or an entry is chosen, a bar
  // between the two names it. Once the panel has been scrolled to, the bar is pinned to the head
  // of the screen and leads back to the map. On a wide screen it is not shown, as the panel
  // stands beside the map.
  //
  // The bar is pinned (class is-pinned) only while its own place is in the upper half of the
  // screen, never near the foot: a mobile browser may take the colour of a pinned element at the
  // foot of the screen, paint the strip around its address bar with it, hiding the page beneath,
  // and keep doing so until the page is reloaded.
  const panelBar = document.getElementById('panel-bar');
  let placeCount = 0;
  let barText = '';
  let barFrame = 0;

  /** Where the reader is: 'up' (the map mostly scrolled away) or 'here' (the bar in its own
   *  place between the map and the panel). */
  function barMode() {
    return mapWrap.getBoundingClientRect().bottom < window.innerHeight / 2 ? 'up' : 'here';
  }

  function syncBar() {
    cancelAnimationFrame(barFrame);
    if (SHEET) {
      panelBar.hidden = true;
      syncSheet();
      return;
    }
    panelBar.hidden = !barText;
    if (!barText) return;
    const mode = barMode();
    // The bar's own place is just above the panel, wherever the bar is pinned.
    const own = panel.getBoundingClientRect().top - panelBar.offsetHeight;
    panelBar.classList.toggle('is-pinned', own < window.innerHeight / 2);
    panelBar.setAttribute('data-mode', mode);
    panelBar.textContent = mode === 'up' ? t('bar.map') : barText;
    if (mode !== 'up') panelBar.lang = state.item ? NAMES_TAG : '';
    else panelBar.removeAttribute('lang');
  }

  function scrollToView(node) {
    const still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    node.scrollIntoView({ behavior: still ? 'auto' : 'smooth', block: 'start' });
  }

  panelBar.addEventListener('click', function () {
    syncBar(); // where the reader is now, not at the last frame drawn
    if (panelBar.getAttribute('data-mode') !== 'up') {
      scrollToView(panel);
      return;
    }
    scrollToView(mapWrap);
    if (state.item) focusRecord(state.item, { fly: true });
  });
  for (const type of ['scroll', 'resize']) {
    window.addEventListener(type, function () {
      if (SHEET) return; // no bar in the modern layout
      cancelAnimationFrame(barFrame);
      barFrame = requestAnimationFrame(syncBar);
    }, { passive: true });
  }

  // ---------- the modern layout: a sliding sheet on a phone, a floating card on a wide screen ----------

  // On a phone the panel lies over the map as a sheet, as in map apps. It is part of the page:
  // swiping it up scrolls the page, so the browser's own bars shrink and the page passes behind
  // them, as on any article. The top bar and the map are pinned by the styles (css/style.css says
  // how, and why the map stops short of the screen's foot). The page comes to rest at three stops,
  // marked for the browser's snapping: low, with the panel's heading showing; half way; and the
  // top, where the panel covers the title and search. The handle is dragged like the rest of the
  // panel, or tapped to move up a stop and back down from the top.
  //
  // On a wide screen the map fills the width, and the panel is a card of fixed width floating at
  // its right, below a row of the map buttons. The card scrolls its own contents and rests at
  // three heights: low, with its heading showing; a third of its room; and all of it. Places are
  // framed in the part of the map left of the card only at the top stop; at the lower two the map
  // above the card is free, so places are framed in the whole map.
  // Its handle is dragged with a mouse, a trackpad or a finger, or tapped as on a phone.
  //
  // Either way the panel stays where it is when an entry is chosen; going back to the whole map
  // lowers the phone's sheet. The handle and the panel sit in one element (.sheet-card), which on a
  // phone the styles leave out of the layout.
  const SHEET = window.FoodMapTheme ? window.FoodMapTheme.layout() === 'sheet' : false;
  const sheetCard = SHEET ? el('div', { class: 'sheet-card', 'data-stop': 'high' }) : null;
  const sheetHandle = SHEET ? el('button', { type: 'button', class: 'sheet-handle', 'aria-label': t('sheet.handle') }) : null;
  const sheetStops = SHEET ? ['low', 'half', 'high'].map((stop) => el('div', { class: 'sheet-stop ' + stop, 'aria-hidden': 'true' })) : [];
  let sheetShown = ''; // what the panel last showed, so the overview lowers the sheet once
  let sheetTopH = 0; // the pinned top bar's height, where the map begins
  let cardStop = 'high'; // where the card rests on a wide screen

  /** How much of the map the phone's sheet covers, in pixels: from the handle to the map's foot. */
  function sheetCover() {
    if (wide() || isImmersive()) return 0;
    return Math.max(0, mapWrap.getBoundingClientRect().bottom - sheetHandle.getBoundingClientRect().top);
  }

  /** How much of the map the wide screen's card covers from the right, with its gap, in pixels;
   *  none at its two lower stops, which leave the map above it free. */
  function cardCover() {
    if (!wide() || cardStop !== 'high' || isImmersive()) return 0;
    return Math.max(0, mapWrap.getBoundingClientRect().right - sheetCard.getBoundingClientRect().left + 16);
  }

  /** The page's scroll position at each stop (on a phone). */
  function sheetScrolls() {
    return sheetStops.map((stop) => Math.round(stop.getBoundingClientRect().top + window.scrollY));
  }

  // A mobile browser may snap a smooth scroll started by the script back to the stop it left, so
  // snapping is switched off while such a scroll runs, and on again once it has ended, on a stop.
  let sheetGlide = 0;
  function scrollSheetTo(index) {
    const still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const root = document.documentElement;
    const target = sheetScrolls()[index];
    root.style.scrollSnapType = 'none';
    const done = function () {
      clearTimeout(sheetGlide);
      window.removeEventListener('scroll', arrived);
      window.removeEventListener('scrollend', done);
      root.style.scrollSnapType = '';
    };
    // On again once the page is at the stop, or has stopped moving; at the latest after 2 s.
    const arrived = function () {
      if (Math.abs(window.scrollY - target) < 2) done();
    };
    clearTimeout(sheetGlide);
    window.addEventListener('scroll', arrived, { passive: true });
    window.addEventListener('scrollend', done);
    sheetGlide = setTimeout(done, 2000);
    window.scrollTo({ top: target, behavior: still ? 'auto' : 'smooth' });
  }

  /** The card's height at each stop (on a wide screen): low shows the handle and the heading,
   *  high reaches up to just below the row of map buttons, half (the middle stop) is a third of
   *  that. */
  function cardHeights() {
    const room = mapWrap.getBoundingClientRect();
    const tools = mapWrap.querySelector('.map-tools').getBoundingClientRect();
    const high = Math.max(0, Math.round(room.bottom - 16 - (tools.bottom + 12)));
    const head = panel.querySelector('.panel-head') || panel.querySelector('h2');
    const card = sheetCard.getBoundingClientRect();
    // 14 px below the heading, or less where the next row starts sooner, so none of it shows.
    const next = head && head.nextElementSibling;
    const foot = head ? Math.min(head.getBoundingClientRect().bottom + 14, next ? next.getBoundingClientRect().top : Infinity) : 0;
    const low = head ? Math.round(foot - card.top + panel.scrollTop) : sheetHandle.offsetHeight;
    return { low: Math.min(low, high), half: Math.min(Math.max(low, Math.round(high / 3)), high), high: high };
  }

  function setCard(stop, animate) {
    cardStop = stop;
    sheetCard.setAttribute('data-stop', stop);
    sheetCard.classList.toggle('is-moving', !animate);
    if (stop === 'low') panel.scrollTop = 0;
    document.documentElement.style.setProperty('--card-h', cardHeights()[stop] + 'px');
  }

  /** A measure for the styles: the pinned top bar's height, where the map begins (on a phone). */
  function syncSheetLayout() {
    if (!SHEET) return;
    const topH = document.querySelector('.topbar').offsetHeight;
    if (topH === sheetTopH) return;
    sheetTopH = topH;
    document.documentElement.style.setProperty('--top-h', topH + 'px');
  }

  function syncSheet() {
    if (!SHEET) return;
    const showing = state.item ? 'item ' + state.item : state.region || '';
    const changed = showing !== sheetShown;
    sheetShown = showing;
    if (wide()) {
      // New contents open from their heading; the low stop follows the heading's height.
      if (changed) panel.scrollTop = 0;
      setCard(cardStop, false);
      return;
    }
    syncSheetLayout();
    if (!changed) return;
    if (!state.region && !state.item && window.scrollY > 0) {
      scrollSheetTo(0);
    } else if (window.scrollY > sheetScrolls()[2]) {
      // New contents open from their heading, at the top stop, not where the old ones were read.
      window.scrollTo({ top: sheetScrolls()[2], behavior: 'auto' });
    }
  }

  if (SHEET) {
    document.documentElement.classList.add('sheet-layout');
    panel.parentNode.insertBefore(sheetCard, panel);
    sheetCard.append(sheetHandle, panel);
    document.body.append(...sheetStops);
    syncSheetLayout();
    if (wide()) setCard(cardStop, false);

    // On a wide screen the handle is dragged: the card follows, and on release settles at the
    // nearest stop, leaning the way a quick flick was going. A press that does not move is a tap.
    let cardDrag = null;
    let cardDragged = false;
    sheetHandle.addEventListener('pointerdown', function (e) {
      if (!wide()) return;
      cardDrag = { y: e.clientY, h: sheetCard.getBoundingClientRect().height, t: performance.now(), moved: false };
      sheetHandle.setPointerCapture(e.pointerId);
    });
    sheetHandle.addEventListener('pointermove', function (e) {
      if (!cardDrag) return;
      const dy = cardDrag.y - e.clientY;
      if (!cardDrag.moved && Math.abs(dy) <= 4) return;
      cardDrag.moved = true;
      sheetCard.classList.add('is-moving');
      const heights = cardHeights();
      document.documentElement.style.setProperty('--card-h', clamp(cardDrag.h + dy, heights.low, heights.high) + 'px');
    });
    const release = function () {
      if (!cardDrag) return;
      const was = cardDrag;
      cardDrag = null;
      if (!was.moved) return; // a tap: the click below moves the card
      cardDragged = true;
      setTimeout(() => (cardDragged = false), 0);
      const heights = cardHeights();
      const now = sheetCard.getBoundingClientRect().height;
      const aim = now + ((now - was.h) / Math.max(performance.now() - was.t, 1)) * 200;
      let best = 'low';
      for (const stop of ['low', 'half', 'high']) if (Math.abs(heights[stop] - aim) < Math.abs(heights[best] - aim)) best = stop;
      setCard(best, true);
    };
    sheetHandle.addEventListener('pointerup', release);
    sheetHandle.addEventListener('pointercancel', release);

    // A tap on the handle: up a stop, and from the top back down to the lowest.
    sheetHandle.addEventListener('click', function () {
      if (wide()) {
        if (!cardDragged) setCard(cardStop === 'low' ? 'half' : cardStop === 'half' ? 'high' : 'low', true);
        return;
      }
      const scrolls = sheetScrolls();
      let here = 0;
      scrolls.forEach((y, i) => {
        if (Math.abs(y - window.scrollY) < Math.abs(scrolls[here] - window.scrollY)) here = i;
      });
      scrollSheetTo(here === scrolls.length - 1 ? 0 : here + 1);
    });

    window.addEventListener(
      'scroll',
      function () {
        if (wide()) return;
        // From the top stop on, the reader is reading the panel: no snapping there, or a short
        // scroll would be pulled back to the stop (the class is-reading in css/style.css).
        document.documentElement.classList.toggle('is-reading', window.scrollY >= sheetScrolls()[2] - 1);
        // The map options would be hidden under the sheet at the top: close them.
        if (sheetHandle.getBoundingClientRect().top < sheetTopH) {
          openOptions(false);
        }
      },
      { passive: true }
    );
    window.addEventListener('resize', function () {
      if (wide()) setCard(cardStop, false);
      else syncSheetLayout();
    });
    window.addEventListener('load', () => syncSheetLayout());
    // Across the breakpoint: the wide card starts with the page at its top.
    onLayoutChange(function () {
      if (!wide()) return;
      window.scrollTo(0, 0);
      setCard(cardStop, false);
    });
  }

  // ---------- phone: the options button and its layer ----------

  /** The options button on a phone is marked while the shading or a hidden layer is in effect. */
  function syncOptionsToggle() {
    optionsToggle.classList.toggle('is-set', Boolean(state.metric) || state.hidden.size > 0);
  }

  const optionsToggle = document.getElementById('options-toggle');
  const filters = document.getElementById('filters');
  // On a phone the open options are a layer over the map, dropping from the top bar; the styles
  // place it from --options-top and move the trail and map buttons down by --options-h.
  function openOptions(open) {
    filters.classList.toggle('is-open', open);
    optionsToggle.setAttribute('aria-expanded', String(open));
    placeOptions();
  }
  function placeOptions() {
    const root = document.documentElement;
    const open = filters.classList.contains('is-open');
    const bar = document.querySelector('.topbar');
    root.style.setProperty('--options-top', Math.round(bar.offsetTop + bar.offsetHeight) + 'px');
    if (open) {
      // The labels' shared width: the wider one's own.
      root.style.removeProperty('--options-label');
      const labels = filters.querySelectorAll('.filter > label, .filter > .filter-label');
      const widest = Math.max(0, ...Array.from(labels, (label) => label.getBoundingClientRect().width));
      root.style.setProperty('--options-label', Math.ceil(widest) + 'px');
    }
    root.style.setProperty('--options-h', (open ? filters.offsetHeight : 0) + 'px');
  }
  window.addEventListener('resize', placeOptions);
  optionsToggle.addEventListener('click', function () {
    openOptions(!filters.classList.contains('is-open'));
  });
  // Esc folds the open options away, and nothing else, as it closes the switches' menus.
  document.addEventListener(
    'keydown',
    function (e) {
      if (e.key !== 'Escape' || !filters.classList.contains('is-open') || !optionsToggle.offsetParent) return;
      openOptions(false);
      optionsToggle.focus();
      e.stopPropagation();
    },
    true
  );

  // ---------- phone: the search button ----------

  // On a phone the search box is folded behind a button beside the title, and opens over the
  // title (the class is-searching on the top bar). It folds again when closed, when a result is
  // chosen, on Esc, and on a tap elsewhere while empty.
  const topbarEl = document.querySelector('.topbar');
  const searchToggle = document.getElementById('search-toggle');
  function openSearch(open) {
    topbarEl.classList.toggle('is-searching', open);
    searchToggle.setAttribute('aria-expanded', String(open));
    if (open) {
      searchInput.focus();
    } else {
      searchResults.hidden = true;
      searchInput.value = '';
      searchInput.blur();
    }
  }
  const searchFolded = () => getComputedStyle(searchToggle).display !== 'none';
  searchToggle.addEventListener('click', () => openSearch(true));
  document.getElementById('search-close').addEventListener('click', function () {
    openSearch(false);
    searchToggle.focus();
  });

  // ---------- actions ----------

  function syncUrl() {
    const q = new URLSearchParams();
    // A selection still waiting for its file keeps its own id in the address.
    const region = wanted ? wanted.id : state.region;
    if (region) q.set('region', region);
    if (state.item) q.set('item', state.item);
    if (state.metric) q.set('metric', state.metric);
    if (state.hidden.size) q.set('hide', Array.from(state.hidden).join(','));
    if (params.get('timeline') === '1') q.set('timeline', '1');
    if (TEXT.explicit) q.set('lang', TEXT.lang);
    // The entry's name, for whoever reads the address. The page itself goes by `item` alone.
    // It comes last, so that an address cut short still leads to the entry.
    const name = state.item ? sourceNames.get(state.item) || params.get('name') : null;
    if (name) q.set('name', name);
    const text = q.toString().replace(/%3A/g, ':').replace(/%2C/g, ',');
    // The tab names the entry or place shown, before the step is recorded, so that each step in
    // the browser's history carries its own name.
    const shown = state.item && entryById.get(state.item);
    const unit = units.get(state.region);
    const named = shown ? shown.record.title : unit ? fullName(unit, true) : '';
    document.title = named ? t('site.pageTitleOf', { name: named }) : t('site.pageTitle');
    // A new place or entry chosen by a click or a key is a step of its own for the browser's
    // back and forward. Anything else, and anything that follows in the same step once a file
    // has loaded, rewrites the current step.
    const here = new URLSearchParams(location.search);
    const moved = (here.get('region') || null) !== (region || null) || (here.get('item') || null) !== (state.item || null);
    if (moved && stepPending) {
      stepPending = false;
      history.pushState(null, '', text ? '?' + text : location.pathname);
    } else {
      history.replaceState(null, '', text ? '?' + text : location.pathname);
    }
    TEXT.refreshLinks(); // the language switch leads to this same view in another language
  }

  // Set by a press (the map acts on pointerup, before the click), a click or a key, and spent by the first change of place or entry it causes.
  let stepPending = false;
  for (const type of ['pointerup', 'click', 'keydown']) {
    document.addEventListener(type, function () {
      stepPending = true;
      setTimeout(function () { stepPending = false; }, 0);
    }, true);
  }

  /** Back or forward: show the place and entry the address names. The shading and the switches stay as they are. */
  window.addEventListener('popstate', function () {
    const at = new URLSearchParams(location.search);
    const region = at.get('region') || null;
    const item = at.get('item') || null;
    if (region === state.region && item === state.item) return;
    stepPending = false;
    state.item = item;
    selectRegion(region, { fly: true, keepItem: true });
    if (item) showItem(item);
  });

  /** Bring the map, the trail, the panel and the address in line with `state.region`. */
  function applySelection() {
    syncMap();
    renderTrail();
    renderPanel();
    refreshPoints();
    syncUrl();
    layoutLabels();
  }

  /** The map's part of a selection, also what places opened without choosing need. */
  function refreshMap() {
    syncMap();
    refreshPoints();
    layoutLabels();
  }

  function syncMap() {
    const chain = chainOf(state.region);
    const unit = chain.length ? chain[chain.length - 1] : null;
    const branch = openBranch();
    syncEnclaves(chain.length > 0 || branch.length > 0);
    syncOpen();
    for (const node of svg.querySelectorAll('.is-selected, .is-open')) node.classList.remove('is-selected', 'is-open');
    if (unit && unit.path) unit.path.classList.add('is-selected');
    for (const above of branch) {
      if (!above.path || !drawn.has(above.id)) continue;
      above.path.classList.add('is-open');
      // Its borders with its neighbours come from the same coarser file as its shape, so they
      // give way too: its detailed outline is drawn in their place.
      const around = units.get(above.parent);
      for (const border of around ? around.borders : []) {
        if (border.path && (border.a === above.id || border.b === above.id)) border.path.classList.add('is-open');
      }
    }
    if (unit && drawn.has(unit.id)) drawn.get(unit.id).base.classList.add('is-selected');
    shadeOpen();
    // A heavy line around the selected unit, and a lighter one around each unit it sits in and
    // around each place opened without choosing.
    selectionOutline.setAttribute('d', unit ? outlineOf(unit) : '');
    const extra = [peeks.soft].concat(Array.from(peeks.background)).map((id) => units.get(id)).filter(Boolean);
    openOutline.setAttribute('d', chain.slice(0, -1).concat(extra).map(outlineOf).join(''));
    // Dots are for the open provinces, once their records are here. Every other province shows a
    // count.
    const open = openProvinces();
    for (const province of open) requestRecords(province);
    const dotted = open.filter((province) => store.has(province.id));
    const same = dotted.length === pointsFor.size && dotted.every((province) => pointsFor.has(province.id));
    if (!same) drawPoints(dotted);
    refreshCounts();
  }

  /**
   * Select a unit by id, or nothing. `options.fly` moves the map to it with a short flight,
   * `options.jump` at once. An entry's page gives way to the place, unless `options.keepItem`.
   */
  function selectRegion(id, options) {
    const move = options || {};
    peeks.soft = null; // a hard choice clears the places opened without choosing
    peeks.background.clear();
    peeks.round += 1;
    wanted = null;
    wantedFocus = null;
    if (!move.keepItem) state.item = null;
    let unit = units.get(id) || null;
    if (!unit && id) {
      // Not loaded yet, or not a unit with a shape. Settle on the nearest unit above it, and
      // come back once the file that should describe it has arrived (see syncOpen).
      const low = lower.get(id);
      unit = units.get(low ? low.parent : provinceIdOf(id)) || null;
      if (unit && opens(unit) && !unit.kids) wanted = { id: id, options: options, on: unit.id };
    }
    state.region = unit ? unit.id : null;
    const marked = recordById.get(state.focus);
    if (!unit || !marked || !recordIn(marked.record, unit)) state.focus = null;
    applySelection();
    if (!unit) {
      if (move.fly) fitBox(home, CONFIG.margin, true);
    } else if (unit.frame && (move.jump || (move.fly && !wanted))) {
      fitBox(unit.frame, 0.35, !move.jump);
    }
  }

  /**
   * Mark one record of the open province: its dot on the map and its row in the panel.
   * `options.fly` moves the map to its dot, or to the selected unit if it has no dot.
   */
  /**
   * The box around the units a record belongs to, or null if none of them has a shape. A unit
   * whose shape has not loaded (a county of a city that has not been opened) or that has none
   * is stood in for by the nearest unit above it that has one.
   */
  function frameOfAreas(record) {
    let box = null;
    for (const area of record.areas || []) {
      const below = lower.get(area);
      let unit = units.get(area) || (below ? units.get(below.parent) : null);
      while (unit && !unit.frame) unit = units.get(unit.parent);
      if (!unit) continue;
      const f = unit.frame;
      box = box
        ? { x0: Math.min(box.x0, f.x0), x1: Math.max(box.x1, f.x1), y0: Math.min(box.y0, f.y0), y1: Math.max(box.y1, f.y1) }
        : { x0: f.x0, x1: f.x1, y0: f.y0, y1: f.y1 };
    }
    return box;
  }

  /**
   * The box that shows an entry's dot, or null if it has none. Its width is the narrowest of
   * three: the view as it is, a seventh of the whole map, and the units the entry belongs to
   * with room around them. So an entry in a small unit is shown close up, and one in a wide unit
   * is not shown from further away than before.
   */
  function boxOfDot(id) {
    const entry = points.get(id);
    const known = recordById.get(id);
    if (!entry || !known) return null;
    let width = Math.min(view.w, (full.x1 - full.x0) / 7);
    const home = frameOfAreas(known.record);
    if (home) width = Math.min(width, widthToFit(home, 0.5));
    const half = width / 2;
    return { x0: entry.x - half, x1: entry.x + half, y0: entry.y - half * 0.6, y1: entry.y + half * 0.6 };
  }

  /**
   * Frame again, at once, what is shown: the box last framed on purpose while the same place is
   * chosen (a view moved up a level with Shift stays there, with an entry opened or closed in
   * the meantime), otherwise the entry's dot, the place, or the whole map.
   */
  function reframe() {
    measure();
    const last = lastFrame;
    if (last && last.region === state.region) {
      fitBox(last.box, last.pad, false);
      return;
    }
    const box = state.focus ? boxOfDot(state.focus) : null;
    const unit = units.get(state.region);
    if (box) fitBox(box, 0, false);
    else if (unit && unit.frame) fitBox(unit.frame, 0.35, false);
    else if (!unit) fitBox(home, CONFIG.margin, false);
  }

  function focusRecord(id, options) {
    const province = chainOf(state.region)[0];
    if (province && !store.has(province.id)) {
      // Its province's records are still on their way. Come back when they are in.
      wantedFocus = { id: id, options: options };
      return;
    }
    const known = recordById.get(id);
    state.focus = known && province && known.record.region === province.id ? id : null;
    refreshPoints();
    renderPanel();
    revealFocus();
    if (!state.focus || !options || !options.fly) return;
    const entry = points.get(id);
    if (entry) {
      const fly = function () {
        if (state.focus !== id || !points.has(id)) return; // something else was picked meanwhile
        fitBox(boxOfDot(id), 0, true);
      };
      // A county's shape comes with its city's file, which is loaded when the city is first
      // opened. Fetch the files that are missing first, so the view fits the county itself.
      // An entry spread over many cities is shown wide in any case, and their own boxes do.
      const cities = new Set();
      for (const area of known.record.areas || []) {
        const below = lower.get(area);
        const city = !units.has(area) && below ? units.get(below.parent) : null;
        if (city && !city.kids) cities.add(city);
      }
      if (cities.size && cities.size <= 4) {
        Promise.all(Array.from(cities, loadKids)).then(fly, fly);
      } else {
        fly();
      }
    } else {
      const unit = units.get(state.region);
      if (unit.frame) fitBox(unit.frame, 0.35, true);
    }
  }

  function setMetric(key) {
    state.metric = key || '';
    metricSelect.value = state.metric;
    applyMetric();
    renderLegend();
    renderPanel();
    syncOptionsToggle();
    syncUrl();
  }

  function setLayerHidden(key, hidden) {
    if (hidden) state.hidden.add(key);
    else state.hidden.delete(key);
    hovered.id = null;
    refreshPoints();
    refreshCounts();
    layoutLabels();
    renderLegend();
    syncOptionsToggle();
    syncUrl();
  }

  // ---------- immersive view ----------
  //
  // The map over the whole page, for looking at it alone: the top bar, the options and the panel
  // are hidden (class is-immersive on the root; css/style.css), in either layout and on any
  // screen. It lasts until the page is left, neither remembered nor in the address, so the page
  // never opens without them. The map works as usual, and the hidden panel keeps up, so leaving
  // shows it for what is selected. Esc leaves it only from the whole map; while a place or an
  // entry is chosen, Esc steps back out as always (see search, below).

  const immersiveButton = document.getElementById('immersive');
  // Four corners, pointing out to enter and in to leave.
  const CORNERS_OUT = 'M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4';
  const CORNERS_IN = 'M6 2v4H2M14 6h-4V2M10 14v-4h4M2 10h4v4';

  function setImmersive(on) {
    if (on) {
      if (filters.classList.contains('is-open')) openOptions(false);
      if (topbarEl.classList.contains('is-searching')) openSearch(false);
      searchResults.hidden = true;
      if (SHEET && !wide()) window.scrollTo(0, 0); // the phone's sheet back down, out of sight
    }
    if (!on) fullscreenMadeImmersive = false; // left by hand: full screen no longer owns it
    document.documentElement.classList.toggle('is-immersive', on);
    immersiveButton.setAttribute('aria-label', t(on ? 'map.immersive.off' : 'map.immersive'));
    immersiveButton.title = t(on ? 'map.immersive.off.tip' : 'map.immersive.tip');
    immersiveButton.querySelector('path').setAttribute('d', on ? CORNERS_IN : CORNERS_OUT);
    if (!on && SHEET) {
      if (wide()) setCard(cardStop, false);
      else syncSheetLayout();
    }
    // The map has changed size: what is shown is framed again for it, once it is laid out.
    setTimeout(reframe, 0);
  }

  immersiveButton.addEventListener('click', () => setImmersive(!isImmersive()));

  // ---------- views by key alone ----------
  //
  // Three more ways to see more of the map, with keys only (mapKey, below) and no button. Like
  // immersive view, none is remembered or in the address. Each is a class on the root that
  // css/style.css reads.
  //   P  the panel's next height: in the modern layout low, middle, high, then hidden (Shift+P
  //      the other way); in the simple layout shown or hidden. Hidden, the map takes the panel's room, keeping its
  //      centre and zoom.
  //   L  the legend off and on.
  //   C  a clean map: the trail, the map buttons and the legend off and on.

  function setPanelOff(off) {
    document.documentElement.classList.toggle('is-panel-off', off);
    if (!off && SHEET) {
      if (wide()) setCard(cardStop, false);
      else syncSheetLayout();
    }
    if (off && SHEET && !wide()) window.scrollTo(0, 0);
    // The map is not framed again: it keeps its centre and zoom and simply gets more room, as
    // when the panel moves between its stops.
  }

  /** The panel's next height, or with `back` (Shift+P) the one before: low, middle, high, hidden. */
  function cyclePanel(back) {
    if (isImmersive()) return; // the panel is hidden there already
    const off = document.documentElement.classList.contains('is-panel-off');
    const order = ['low', 'half', 'high'];
    if (off) {
      // Out of hidden: forward to low, back to high.
      if (SHEET && wide()) setCard(back ? 'high' : 'low', false);
      setPanelOff(false);
      if (SHEET && !wide() && back) scrollSheetTo(2);
      return;
    }
    if (!SHEET) {
      setPanelOff(true);
      return;
    }
    let here = order.indexOf(cardStop);
    if (!wide()) {
      const scrolls = sheetScrolls();
      here = 0;
      scrolls.forEach((y, i) => {
        if (Math.abs(y - window.scrollY) < Math.abs(scrolls[here] - window.scrollY)) here = i;
      });
    }
    const next = here + (back ? -1 : 1);
    if (next < 0 || next > 2) setPanelOff(true);
    else if (wide()) setCard(order[next], true);
    else scrollSheetTo(next);
  }

  const toggleRootClass = (name) => document.documentElement.classList.toggle(name);

  // ---------- full screen ----------
  //
  // F asks the browser for full screen, with immersive view if it is not on already, and F again
  // leaves both, back to how the page was: immersive view stays if it was on before. A browser
  // usually ends full screen at one press of Esc, before the page sees it. Where it can, the page
  // keeps Esc for itself (Keyboard Lock, Chromium on a computer): a short press works on the map
  // as everywhere, holding it leaves full screen, and the browser says so. Esc at the whole map,
  // in immersive view, leaves full screen too. Where the browser has no full screen for a page
  // (a phone), F turns immersive view on and off.

  let fullscreenMadeImmersive = false;
  const fullscreenNow = () => Boolean(document.fullscreenElement || document.webkitFullscreenElement);

  function exitFullscreen() {
    const exit = document.exitFullscreen || document.webkitExitFullscreen;
    if (exit) exit.call(document);
  }

  function toggleFullscreen() {
    if (fullscreenNow()) {
      exitFullscreen();
      return;
    }
    const root = document.documentElement;
    const request = root.requestFullscreen || root.webkitRequestFullscreen;
    if (!request) {
      setImmersive(!isImmersive());
      return;
    }
    if (!isImmersive()) {
      setImmersive(true);
      fullscreenMadeImmersive = true;
    }
    const asked = request.call(root);
    const lockEsc = function () {
      if (navigator.keyboard && navigator.keyboard.lock) navigator.keyboard.lock(['Escape']).catch(() => {});
    };
    if (asked && asked.then) asked.then(lockEsc, () => {});
    else lockEsc();
  }

  for (const type of ['fullscreenchange', 'webkitfullscreenchange']) {
    document.addEventListener(type, function () {
      // The screen has a new shape, which a browser may give the page only after saying so:
      // what is shown is framed again now, and once more at the first resize within a second.
      const settle = function () {
        window.removeEventListener('resize', settle);
        setTimeout(reframe, 0);
      };
      window.addEventListener('resize', settle);
      setTimeout(() => window.removeEventListener('resize', settle), 1000); // or not at all
      setTimeout(reframe, 0);
      if (fullscreenNow()) return;
      if (navigator.keyboard && navigator.keyboard.unlock) navigator.keyboard.unlock();
      if (fullscreenMadeImmersive) setImmersive(false);
    });
  }

  // ---------- controls ----------

  // The title fades out at its end only where it is cut short (class is-cut): on a phone beside
  // its buttons, on a narrow wide screen under the search box. It is never narrower than its
  // first part, the name in the page's language, with room after it for the fade when a second
  // part follows (--title-min on its holder; the fade is 32 px, in css/style.css).
  const titleEl = document.querySelector('.brand h1');
  if (titleEl && window.ResizeObserver) {
    const first = titleEl.firstElementChild;
    const syncTitle = function () {
      const pad = parseFloat(getComputedStyle(titleEl).paddingLeft) || 0;
      const second = first.nextElementSibling;
      const fade = second && !second.hidden ? 32 : 0;
      titleEl.parentNode.style.setProperty('--title-min', Math.ceil(first.offsetWidth + pad + fade) + 'px');
      titleEl.classList.toggle('is-cut', titleEl.scrollWidth > titleEl.clientWidth + 1);
    };
    new ResizeObserver(syncTitle).observe(titleEl);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(syncTitle);
  }

  metricSelect.append(el('option', { value: '', text: t('metric.none') }));
  for (const c of DATA.indicators.columns) {
    metricSelect.append(el('option', { value: c.key, text: (c.partOf ? '– ' : '') + t('metric.option', { food: foodName(c) }) }));
  }
  metricSelect.addEventListener('change', () => setMetric(metricSelect.value));

  for (const layer of LAYERS) {
    // The switch shows the short name; the full name is its hover tip and its spoken label.
    const box = el('input', { type: 'checkbox', id: 'layer-' + layer.key, 'aria-label': layer.label });
    box.checked = true;
    box.addEventListener('change', () => setLayerHidden(layer.key, !box.checked));
    layer.checkbox = box;
    layerToggles.append(
      el('label', { class: 'toggle', for: 'layer-' + layer.key, 'data-tip': layer.label }, box, el('span', { class: 'swatch swatch-' + layer.key }), el('span', { text: layer.short }))
    );
  }

  // ---------- search ----------
  //
  // The list of titles and place names is a file of its own, loaded the first time the search
  // box is used.

  let searchIndex = null; // [{ names, label, sub, region, record }], once the file has loaded
  let searchLoad = null;
  let searchFailed = false;
  let alike = null; // Map: a character -> the one that stands for its group, from the search file

  /**
   * A text as the search compares it: in lower case, and with each Chinese character replaced by
   * the one that stands for its group, so that 发, 發 and 髮 are the same. A search typed in
   * Simplified or in Traditional Chinese then finds the same things, in any interface.
   */
  function plain(text) {
    text = text.toLowerCase();
    if (!alike) return text;
    let out = '';
    for (const char of text) out += alike.get(char) || char;
    return out;
  }

  /**
   * A name or a search as it is compared: `plain`, and for letters without accents, spaces,
   * apostrophes or hyphens, with ü and v as u. So "Hua Lian", "zoige" and "lvliang" find 花蓮縣,
   * Zoigê and Lüliang.
   */
  function fold(text) {
    return plain(text).normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/v/g, 'u').replace(/[\s'’.\-]/g, '');
  }

  function loadSearch() {
    if (searchLoad) return;
    searchLoad = loadScript('js/data/search.js?v=' + DATA.searchVersion).then(
      function () {
        const file = window.FOODMAP_SEARCH;
        alike = new Map();
        for (const group of (file.alike || '').split(' ')) {
          const chars = Array.from(group);
          for (const char of chars.slice(1)) alike.set(char, chars[0]);
        }
        TEXT.localise(file);
        const index = [];
        const names = (list) => list.filter(Boolean).map(fold);
        for (const p of provinces) {
          const other = (file.provinces && file.provinces[p.id]) || [];
          index.push({ names: names([p.name, p.short, p.en].concat(other)), label: fullName(p), sub: t('search.province'), region: p.id });
        }
        // Places come in the order of the divisions table, so a third-level place belongs to
        // the nearest second-level one above it.
        let above = null;
        for (const row of file.places) {
          if (row[2] === 2) above = row;
          // In the English interface a name from a Traditional source is shown as written there.
          const path = regionName(provinceIdOf(row[0])) + (row[2] === 3 && above ? TEXT.writtenAs(above[0], 'name', above[1]) : '');
          // row: id, name, depth, English name, its tag, other names (matched, never shown).
          const label = TEXT.writtenAs(row[0], 'name', row[1]) + (row[3] && !CHINESE ? ' ' + englishName(row[3], row[4]) : '');
          index.push({ names: names([row[1], row[3]].concat(row[5] || [])), label: label, sub: t('search.place', { path: path }), region: row[0] });
        }
        for (const id of Object.keys(file.records)) {
          for (const row of file.records[id]) {
            const key = file.kinds[row[1]];
            const one = LAYER[key] ? LAYER[key].one : DISHES.one;
            index.push({ names: names([row[0]]), label: TEXT.writtenAs(row[2], 'title', row[0]), sub: one + ' · ' + regionName(id), region: id, record: row[2] || null });
          }
        }
        searchIndex = index;
        runSearch();
      },
      function (error) {
        searchFailed = true;
        console.warn(error.message);
        runSearch();
      }
    );
  }

  function runSearch() {
    const q = fold(searchInput.value.trim());
    searchResults.textContent = '';
    if (!q) {
      searchResults.hidden = true;
      return;
    }
    searchResults.hidden = false;
    if (!searchIndex) {
      loadSearch();
      searchResults.append(el('li', { class: 'empty', text: searchFailed ? t('search.failed') : t('common.loading') }));
      return;
    }
    // Whole-name matches first, then names that start with what was typed, then the rest. Each
    // of a thing's names counts (Chinese, English, pinyin), so "suzhou" puts 苏州市, 宿州市 and
    // 肃州区 first. Within each group the order is provinces, places, dishes and other records.
    const hits = [];
    for (const item of searchIndex) {
      let rank = 3;
      for (const name of item.names) {
        if (name === q) {
          rank = 0;
          break;
        }
        if (name.startsWith(q)) rank = Math.min(rank, 1);
        else if (name.includes(q)) rank = Math.min(rank, 2);
      }
      if (rank < 3) hits.push({ item: item, rank: rank });
    }
    hits.sort((a, b) => a.rank - b.rank);
    if (!hits.length) {
      searchResults.append(el('li', { class: 'empty', text: t('search.none') }));
    }
    for (const found of hits.slice(0, 12)) {
      const hit = found.item;
      const button = el('button', { type: 'button' }, el('span', { class: 'hit-label', text: hit.label }), el('span', { class: 'hit-sub', text: hit.sub }));
      button.addEventListener('click', function () {
        searchResults.hidden = true;
        searchInput.value = '';
        if (topbarEl.classList.contains('is-searching')) openSearch(false);
        if (hit.record) {
          // The entry's province is selected at once, then its own place once the files are in.
          selectRegion(hit.region, { fly: false });
          state.item = hit.record;
          showItem(hit.record, { search: true });
        } else {
          selectRegion(hit.region, { fly: true });
        }
      });
      searchResults.append(el('li', null, button));
    }
  }
  searchInput.addEventListener('input', runSearch);
  searchInput.addEventListener('focus', function () {
    loadSearch();
    runSearch();
  });
  document.addEventListener('pointerdown', function (e) {
    if (!e.target.closest || !e.target.closest('.search')) {
      searchResults.hidden = true;
      // An empty search opened on a phone folds away again on a tap elsewhere.
      if (topbarEl.classList.contains('is-searching') && !searchInput.value && !e.target.closest('.topbar')) openSearch(false);
    }
  });

  document.addEventListener('keydown', function (e) {
    const typing = /^(input|select|textarea)$/i.test(e.target.tagName || '');
    if (e.key === '/' && !typing) {
      e.preventDefault();
      if (searchFolded()) openSearch(true);
      else searchInput.focus();
    } else if (e.key === 'Escape') {
      if (topbarEl.classList.contains('is-searching')) {
        openSearch(false);
        searchToggle.focus();
      } else if (!searchResults.hidden) {
        searchResults.hidden = true;
        searchInput.blur();
      } else if (state.item) {
        closeItem();
      } else if (state.region) {
        // Step back out one level: a city to its province, a province to the whole map.
        selectRegion(parentOf(state.region), { fly: true });
      } else if (peeks.soft || peeks.background.size) {
        // At the whole map, Esc first closes what soft and background clicks opened ...
        clearPeeks();
      } else if (fullscreenNow()) {
        // ... then leaves full screen (and the immersive view F brought with it) ...
        exitFullscreen();
      } else if (isImmersive()) {
        // ... or immersive view.
        setImmersive(false);
      }
    } else if (!typing && !e.ctrlKey && !e.metaKey && !e.altKey) {
      mapKey(e);
    }
  });

  // Single keys for the map, where no field is being typed in and no modifier is held, so the
  // browser's own shortcuts (Cmd + for the page's zoom) are left alone. The hover tips name them.
  //   + (or =)  zoom in            − (or _)  zoom out            H  the whole map in view (the house)
  //   0  China, nothing chosen      1, 2, 3  the place at that level of the trail, as a click on it
  //   R  the place shown back in view (the trail's last item)
  //   Shift+0 to Shift+3  that level's place in view, without choosing it (Shift+0 is H); read
  //      by the key's position, as Shift turns the digits into other characters
  //   M  map only (immersive view)  F  full screen, with the map only
  //   P  the panel's next height, or hidden   L  the legend   C  the trail, buttons and legend
  //      (no button shows these three; see "views by key alone")
  //   A  every province opened in the background   B  every city of the open provinces
  //      (also hidden; see "soft, view and background clicks")
  //   arrows  move the map while it has the focus (Tab to a place on it), or after a click on
  //           it while nothing else has the focus (a click that opens a place replaces the
  //           shape clicked, and the focus falls back to the page), so they never take over
  //           the scrolling of the panel or the page
  let mapClickedLast = false;
  document.addEventListener('pointerdown', (e) => (mapClickedLast = Boolean(e.target.closest && e.target.closest('#map'))), true);
  document.addEventListener('focusin', (e) => (mapClickedLast = mapClickedLast && Boolean(e.target.closest && e.target.closest('#map'))));
  const mapHasKeys = (e) => (e.target.closest && e.target.closest('#map')) || (mapClickedLast && e.target === document.body);

  /**
   * A key for the trail does what a click on its item does: 0 is China, 1 to 3 the levels below
   * it, R the last item. A level the trail does not reach is ignored. With nothing chosen, there
   * is no trail: 0 still chooses the whole map, closing what soft and background clicks opened,
   * and R shows it.
   */
  function trailKey(key) {
    const items = trail.hidden ? [] : trail.querySelectorAll('li > button');
    if (!items.length) {
      if (key === '0') selectRegion(null, { fly: true });
      else if (key === 'r' || key === 'R') fitBox(home, CONFIG.margin, true);
      return;
    }
    const item = key === 'r' || key === 'R' ? items[items.length - 1] : items[Number(key)];
    if (item) item.click();
  }

  /** Frame the place at a level of the trail (0 is the whole map) without choosing it. */
  function viewLevel(level) {
    if (level === 0) {
      fitBox(home, CONFIG.margin, true);
      return;
    }
    const unit = chainOf(state.region)[level - 1];
    if (unit && unit.frame) fitBox(unit.frame, 0.35, true);
  }

  function mapKey(e) {
    const key = e.key;
    let done = true;
    if (key === '+' || key === '=') zoomMiddle(1 / 1.6);
    else if (key === '-' || key === '_' || key === '−') zoomMiddle(1.6);
    else if (key === 'h' || key === 'H') fitBox(home, CONFIG.margin, true);
    else if (/^[0-3]$/.test(key) || key === 'r' || key === 'R') trailKey(key);
    else if (e.shiftKey && /^Digit[0-3]$/.test(e.code)) viewLevel(Number(e.code.slice(5)));
    else if (key === 'm' || key === 'M') setImmersive(!isImmersive());
    else if (key === 'f' || key === 'F') toggleFullscreen();
    else if (key === 'p' || key === 'P') cyclePanel(e.shiftKey);
    else if (key === 'l' || key === 'L') toggleRootClass('is-legend-off');
    else if (key === 'c' || key === 'C') toggleRootClass('is-bare');
    else if (key === 'a' || key === 'A') openAllProvinces();
    else if (key === 'b' || key === 'B') openAllCities();
    else if (key.slice(0, 5) === 'Arrow' && mapHasKeys(e)) {
      // A tenth of the map in view per press.
      const h = view.w * (size.H / size.W);
      const dx = key === 'ArrowLeft' ? -1 : key === 'ArrowRight' ? 1 : 0;
      const dy = key === 'ArrowUp' ? -1 : key === 'ArrowDown' ? 1 : 0;
      stopFlight();
      movedByHand = true;
      setView(view.cx + (dx * view.w) / 10, view.cy + (dy * h) / 10, view.w);
    } else done = false;
    if (done) e.preventDefault();
  }

  // ---------- the view across a switch of layout or language ----------
  //
  // Both switches load the page again (js/i18n.js says so with the event foodmap:switch just
  // before). The view goes along, in this tab's session storage, for the next load only: a view
  // framed on purpose is framed again for the new layout, one moved by hand keeps its centre and
  // zoom. Any other load (a reload, back, a link) frames the place afresh.

  const CARRY_KEY = 'foodmap-view';

  document.addEventListener('foodmap:switch', function () {
    const saved = {
      region: state.region,
      item: state.item,
      view: { cx: view.cx, cy: view.cy, w: view.w },
      frame: !movedByHand && lastFrame && lastFrame.region === state.region ? { box: lastFrame.box, pad: lastFrame.pad } : null,
    };
    try {
      sessionStorage.setItem(CARRY_KEY, JSON.stringify(saved));
    } catch (error) {
      // Without storage the new page frames the place afresh.
    }
  });

  /** The view saved by a switch, if this load opens on the same place and entry; used once. */
  function takeCarriedView() {
    let saved = null;
    try {
      saved = JSON.parse(sessionStorage.getItem(CARRY_KEY) || 'null');
      sessionStorage.removeItem(CARRY_KEY);
    } catch (error) {
      return null;
    }
    if (!saved || !saved.view) return null;
    const region = params.get('region') || null;
    const item = params.get('item') || null;
    return saved.region === region && saved.item === item ? saved : null;
  }

  // ---------- start ----------

  if (timeline.enabled) {
    // The time axis needs every record's year, so with it on, every province is loaded at once.
    Promise.all(provinces.map(loadRecords)).then(
      function () {
        const all = [];
        for (const own of store.values()) for (const layer of LAYERS) for (const record of own[layer.key]) all.push(record);
        timeline.setRecords(all);
        applySelection();
        renderLegend();
      },
      (error) => console.warn(error.message)
    );
  }

  const hide = (params.get('hide') || '').split(',').filter(Boolean);
  for (const layer of LAYERS) {
    if (hide.indexOf(layer.key) !== -1) {
      state.hidden.add(layer.key);
      layer.checkbox.checked = false;
    }
  }
  const startMetric = params.get('metric') || '';
  if (DATA.indicators.columns.some((c) => c.key === startMetric)) state.metric = startMetric;
  metricSelect.value = state.metric;

  measure();
  fitBox(home, CONFIG.margin, false);
  applyMetric();
  renderLegend();
  syncOptionsToggle();
  refreshCounts();
  refreshPoints();
  state.item = params.get('item') || null;
  // A switch of layout or language reloads the page; it saves the view first (below), and the
  // page takes it back, once, if it opens on the same place and entry.
  const carried = takeCarriedView();
  selectRegion(params.get('region'), { jump: !carried, keepItem: true });
  if (state.item) showItem(state.item);
  if (carried) {
    measure();
    if (carried.frame) fitBox(carried.frame.box, carried.frame.pad, false);
    else {
      setView(carried.view.cx, carried.view.cy, carried.view.w);
      movedByHand = true;
    }
  }

  if (!timeline.enabled) {
    loadScript('js/data/dots.js?v=' + DATA.dotsVersion).then(
      () => drawFaint(window.FOODMAP_DOTS || {}),
      (error) => console.warn(error.message)
    );
  }

  if (typeof ResizeObserver !== 'undefined') {
    new ResizeObserver(function () {
      measure();
      setView(view.cx, view.cy, view.w);
    }).observe(svg);
  }
  window.addEventListener('scroll', measure, { passive: true });
  // Across the breakpoint the map changes size and the panel moves, so what was framed is framed
  // again for the new layout, once it is laid out (after the modern layout's own step, above).
  onLayoutChange(() => setTimeout(reframe, 0));

  // The shading is painted by this script, so it is painted again when the theme changes.
  THEME.onChange(function (scheme) {
    RAMP = RAMPS[scheme];
    applyMetric();
    renderLegend();
  });

  // A small handle for trying things from the browser console.
  window.foodMap = {
    state: state,
    config: CONFIG,
    units: units,
    selectRegion: selectRegion,
    setMetric: setMetric,
    focusRecord: focusRecord,
    openItem: openItem,
    view: () => Object.assign({ pixelsPerUnit: size.W / view.w }, view),
  };
});
