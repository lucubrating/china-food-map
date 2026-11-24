# China Food Map · 中国美食地图

A map of regional food across Greater China: signature dishes, protected regional products, heritage food traditions, farm heritage systems, and what people eat, by province. It covers mainland China, Hong Kong, Macau and Taiwan.

It brings together the whole dish list, all eight farm heritage batches, the food entries of the national heritage register and of Hong Kong's, Macau's and Taiwan's own lists, and the product notices from 2021 to 2026. What each layer holds is set out under "What is in it".

The map is offered as it is. It may contain mistakes or be out of date, and no responsibility is taken for the accuracy, completeness or currency of its information.

## Run it

No install step. Serve the folder with any static file server and open it in a browser:

```bash
python3 -m http.server 8765
```

Then open http://localhost:8765.

## What it does

- **Map:** one SVG of the 34 province-level units. Drag to pan, scroll or pinch to zoom. The number under a province's name counts its entries in the categories switched on.
- **Opening a province:** click a province and it opens into the units directly under it: cities, prefectures, or districts in the case of Beijing, Shanghai, Tianjin, Chongqing, Hong Kong and Macau. The other provinces stay closed. Click a city and it opens in the same way, into its districts and counties, which can be selected in turn. A trail at the top left of the map steps back out, and so does Esc. The trail gives the place shown its full name and the places above it their short names (四川 Sichuan › 阿坝 Ngawa › 马尔康市 Barkam). Provinces always keep their short names. On the mainland, a place just above one that shares its name takes a longer form, so the two are told apart: 湖南 Hunan › 长沙市 Changsha City › 长沙县 Changsha County, 四川 Sichuan › 阿坝州 Ngawa Prefecture › 阿坝县 Ngawa County. So does a place whose short name is a province's, wherever it is in the trail: 青海 Qinghai › 海南州 Hainan Prefecture › 共和县 Gonghe County.
- **Dots:** the open province shows its protected regional products, heritage food traditions and farm heritage systems as dots, each category in its own colour. Hover for details, click to see the entry in the panel. Entries placed at the centre of a district or county line up in rows under its name.
- **Category names:** each category has one official name, used in the panel, legend, search and hover details. The switches above the map use a short form (Products, Traditions, Farm systems) and show the full name on hover. Signature dishes have no dots, because a dish is tied to a province, not a point.
- **Panel:** a selected province shows its places with a count for each, its dishes, products, heritage entries, farm heritage and a table of what people there eat. A selected city, district or county shows the entries inside it, and says how many more are recorded for the place it sits in as a whole.
- **Shading:** pick a food in "Shade provinces by" to colour provinces by how much of it people eat. The panel then lists every province in order.
- **Search:** type the name of a dish, a product, a province, or a city, district or county. Simplified or Traditional Chinese finds the same things, in any interface, and so do a place's English name and the pinyin of its name, without tones: "Hualien" and "hualian" both find 花蓮縣, "Zoigê" and "ruoergai" both find 若尔盖县. Provinces and big cities are also found by their old spellings and a few old names: "Peking", "Tientsin", "Amoy", "Szechwan", "Canton", "Mukden". Places are also found by former Chinese names and their pinyin: 郫县 and "pixian" find 郫都区, 襄樊 finds 襄阳市. Search shows only the present name. Case, spaces, apostrophes, accents and ü, u or v do not matter. Names that match whole come first.
- **Languages:** English, Simplified Chinese and Traditional Chinese, chosen with the switch at the top right. The English interface is mixed: it keeps the Chinese names of places and records, in Simplified, except names whose source writes them in Traditional (Taiwan's places and registers, Hong Kong's and Macau's districts and heritage lists), which it shows as written there. Beside a place's Chinese name it shows the place's English name. Where several places share an English name, the name carries its province in brackets, or its city when two are in one province: Suzhou (Jiangsu) and Suzhou (Anhui), Gulou District (Nanjing). The trail on the map leaves the brackets out, since it shows the province and city itself. The two Chinese interfaces have no English in them. The Traditional one is converted from the Simplified by the build, names included, in Taiwan's character forms.
- **Entry pages:** clicking an entry opens its own page in the panel: its facts, a note on how its dot was placed, related entries and its source.
- **Faint dots:** the provinces that are not open show their entries as small faint dots, so the whole map shows where things lie.
- **Light and dark:** a switch beside the language switch follows the system's setting or holds light or dark. It is remembered on the device and is not part of the address.
- **Shareable address:** the address bar records the selected place at any level, the open entry, the shading and the hidden layers. The language is in the address only when chosen on the switch; otherwise the page follows the browser's language.

## How it is put together

A static site with no framework, no map library and no server code.

```
index.html            page shell
css/style.css         all styling
js/geo.js             boundary decoding and map projection
js/timeline.js        the time axis (switched off, see below)
js/theme.js           light or dark, chosen before the page is drawn
js/i18n.js            picks the language, fills in the page's text, draws the language and theme switches
js/app.js             everything else: drawing, camera, panel, search
js/data/              generated files the page loads (do not edit)
js/data/units/        the places inside one province or city, loaded when it is opened
js/data/dots.js       the position of every placed entry, for the faint dots of the whole map
js/data/records/      the records of one province, loaded when it is opened
js/data/details/      what an entry's own page shows beyond its record, one file per province
js/data/names/        names for one language each, loaded in that language only: how to write them in
                      Traditional Chinese, and for English, the names as their Traditional sources write them
data/                 the editable data, as JSON and GeoJSON
scripts/              the build script (build.py) and its helpers, and the importers that made data/
```

Data flows one way:

```
data/  ──build.py──▶  js/data/
clean, editable       compact files
records               the page loads
```

**What the page loads.** At the start it loads only the province shapes (`regions.js`) and a summary (`summary.js`): the sources, the eating table and a count of records per province, about 100 KB together. Opening a province fetches two more files, its places and its records. The search list (`search.js`: titles, and place names in Chinese, English and pinyin) is fetched the first time the search box is used. The first load therefore stays small however many records are added later. In Traditional Chinese the page loads one more file at the start, a table for converting names (`names/zh-hant.js`, 13 KB).

**Faint dots.** A province that is not open shows its entries as small quiet dots that cannot be picked, so the whole map shows where things lie. They come from `js/data/dots.js` (44 KB: positions by province and category, nothing else), fetched after the map is first drawn. Each province's dots in one category are a single path. The open province shows its real dots in their place. They follow the category switches, and are left out when the time axis is on, because the file holds no years.

**Light and dark.** `js/theme.js` runs in the head, before the styles, and sets `data-scheme="light"` or `"dark"` on the root element: the choice on the switch (the system's setting, light, or dark), resolved. The choice is remembered on the device and is not in the address. `css/style.css` gives every colour as a variable, once in `:root` and once in `:root[data-scheme="dark"]`; no rule below those two lists names a colour. The shading scale for provinces is painted by `js/app.js`, which keeps one scale per theme (`RAMPS`) and repaints when the theme changes: the light scale runs from pale to deep and the dark one from near the land's colour to bright, so a low figure is quiet in both. Printing always uses the light theme.

**An entry's own page.** A click on a dot, an entry in a list, a dish or a search result fills the panel with that entry's page (`renderItem` in `js/app.js`): its facts, a note on its dot where the dot is not the position its source states, other entries in the same places and of the same kind, and its source. The page is a run of parts, each drawn only when the entry has something for it. The long fields (`area`, `remark`, `marks`, `listed_by`) are not in the province's record file but in `js/data/details/`, fetched when a page is first opened in that province; a converted language has its own copies under `js/data/details/zh-hant/`, converted by the build.

The address of a page is `?region=…&item=…&name=…`. Only `item`, the entry's id, is read to find the entry. `region` is the place the page was opened from, and is put right if it does not hold the entry. `name` is for the reader: the entry's title in its source's script, Simplified for the mainland's sources and Traditional for Hong Kong's, Macau's and Taiwan's. An address with `item` alone works: the page finds the entry's province in the search file.

To give an entry a short introduction, create `data/intros.json` as `{"intros": {"<entry id>": {"en": "…", "zh": "…", "refs": [{"w": "<work id>"}]}}}`. The build checks each one and puts it in the details file, and the page shows it above the facts. It must be written fresh, with its source cited, never taken from a source's prose.

### Interface text

No display text is written into the scripts. Every piece is an entry in `data/text.json`, with English and Simplified Chinese written by hand. The Traditional Chinese text is converted from the Simplified, as described in the next section.

```json
"places.loose": {
  "en": { "one": "{n} entry is recorded for {place} as a whole.", "other": "{n} entries are recorded for {place} as a whole." },
  "zh": "另有 {n} 项条目登记在{place}整体名下。"
}
```

- **A value is a text, or two forms** chosen by the number `{n}`: one, or any other number.
- **Names in braces are filled in by the page.** They must be the same in each language, unless the entry lists them under `vars`.
- **The scripts ask for a text by its key:** `t('places.loose', { n: 2, place: '成都市' })`. Text written into `index.html` carries its key in a `data-t` attribute.
- **`build.py` compiles the table into `js/data/text.js`** and stops if an entry lacks a language, or if the page asks for a key that is not in the table.
- **The language** comes from `?lang=` in the address (`en`, `zh-hans` or `zh-hant`), or else from the language last clicked on the switch on the device, or else from the browser's languages, or else it is English. The globe on the switch means "the browser's language": it leaves `lang=` out of the address and forgets the remembered one. A language clicked on the switch always shows as `lang=`, so an address with it is a link to that language and one without is a link to each reader's own. A `lang=` that arrives in a link is shown but not remembered.
- **Taiwan's wording.** An entry in `data/text.json` may give its Traditional text in full under `zh-hant`, where Taiwan uses other words and not only other characters (預設 for 默认). That text is used as it stands. This is the only Traditional Chinese written by hand; every name is converted. An entry with a `zh-hant` text no longer follows its Simplified text: when one is edited, edit the other.
- **Sources and food names** have their Chinese forms in `data/works.json` (`zh`, `noteZh`) and `data/indicators.json` (`zh`).

### Traditional Chinese

The data and the Chinese interface text are kept in Simplified Chinese only. The build converts them, so nothing is stored twice and nothing has to be kept in step by hand.

- **Why it needs care.** Most Simplified characters have one Traditional form, but a few hundred have several, and the right one depends on the word. 干 is 乾 in 豆腐乾, stays 干 in the county 餘干, and is 幹 in 樹幹. Food and place names are full of these.
- **The converter** is `scripts/hant.py`. It reads a text from left to right, converts the longest phrase it knows at each point, and gives any other character its usual form. Then it puts the result into the character forms of one place: Taiwan's (`tw`) or Hong Kong's (`hk`). Try it with `python3 scripts/hant.py 豆腐干 余干县`, which also says what decided each character.
- **The tables** are in `data/hant.json`: 4,012 characters and 49,277 phrases from the [OpenCC](https://github.com/BYVoid/OpenCC) project, under the Apache 2.0 licence.
- **Corrections** go in `data/overrides/hant.json`, in three strengths: the usual form of a character, a phrase, or a whole text. The file says why each one is there.
- **Which language is converted** is set in `data/text.json`: a language with `"forms": "tw"` is made from the language named in `"from"`. Changing `tw` to `hk` and rebuilding gives Hong Kong's forms.
- **What the page gets.** The interface text arrives already converted, in `js/data/text.js`. The names in the data arrive as a small table, `js/data/names/zh-hant.js`: the form most names want for each character, and in full the names that would come out wrong that way. The page converts each file of data with it once, as the file arrives, and shows exactly what the converter decided. Hong Kong and Macau districts use their official Traditional names from `data/divisions.json`.
- **Reading the results.** A name with one of the several-form characters is worth reading once. `python3 scripts/build.py --names` lists the ones not yet read, grouped by character and by what decided it. After reading them and adding any corrections, `python3 scripts/build.py --names-read` records them in `data/hant-read.json`. A name whose conversion later changes is listed again. The ordinary build says how many are waiting.
- **Two checks in the build.** It stops if a converted text still holds a character found only in Simplified Chinese, which catches a correction typed in the wrong script. It also stops if the interface text is incomplete, as before.
- **Search** uses groups of characters that are forms of one another (发, 發 and 髮), sent with the search list. A search and the names it is compared with are both reduced to one character per group, so either script finds the same things.

### Building

Everything is plain Python 3 with no packages to install. The build reads `data/` and writes `js/data/`, and refreshes the asset hashes in `index.html`.

```bash
python3 scripts/build.py                    # data/ → js/data/, and refresh asset hashes
python3 scripts/build.py --check            # fail if the bundles are out of date
python3 scripts/build.py --names            # list converted names not yet read through
python3 scripts/build.py --names-read       # record them as read
```

`build.py` checks that every record points to a known province, known places and a known source, and stops if not. Run it after changing anything in `data/`, `css/` or `js/`.

### Data format

Every record names its province with a region id, `cn:` plus the six-digit administrative division code (`cn:510000` is Sichuan). The prefix leaves room for other countries' codes later. `areas` lists the units the record belongs to, at the finest level its source states; a product made in three counties lists all three. `coord` is where its dot goes, and `approx` marks a dot that sits at the centre of a unit because the source gives no position. Every record also cites its source through `refs`, which point into `data/works.json`. A record from a source written in Traditional Chinese (Taiwan's registers, and Hong Kong's and Macau's heritage lists) keeps the source's wording under `hant`, field by field; the Traditional and English interfaces show that wording as it stands, and `title` holds the Simplified form.

```json
{
  "id": "gi:625-46",
  "title": "大通湖大米",
  "kind": "grain",
  "region": "cn:430000",
  "areas": ["cn:430921"],
  "coord": [112.4792, 29.1715],
  "since": 2025,
  "refs": [{ "w": "cnipa-notice-625", "loc": "附件1 序号46" }]
}
```

### Administrative units

`data/divisions.json` lists every unit at the three levels the map is meant to show: 34 province-level units, 499 units directly under them, and 3,096 under those. Each row has an id, its parent, its depth, names and a centre point.

- **A unit's level is its depth in the tree, not the shape of its code.** A Beijing district has a six-digit county code but sits at depth 2, directly under the municipality.
- **Ids** are `cn:` plus the division code. Hong Kong and Macau districts use ids such as `hk:wan-chai`, because the national standard has no codes for them. For the same reason the units inside Taiwan use `tw:` plus the code Taiwan's surveying centre gives them: `tw:63000` is Taipei and `tw:10014060` is 池上乡.
- **Taiwan.** Taiwan's 22 cities and counties and 368 townships and districts, with their shapes, come from the township boundary file of Taiwan's National Land Surveying and Mapping Center (version of March 2023, Open Government Data License). A city or county's shape is made from its townships. The file's names are in Traditional Chinese: each is kept as `hant` and shown as it stands, and `name` is its Simplified form. The file also gives English names. Islands that lie far from their unit are left out of its shape: those the file gives to 頭城鎮 east of 123°E and to 旗津區 south of 21.5°N.
- **English names and pinyin.** `en` is a place's official English name: Taiwan's from the same boundary file, Hong Kong's and Macau's their well-known official names, and the mainland's from [Wikidata](https://www.wikidata.org/), matched by division code and checked against the Chinese name. A city at the second level is named without "City" ("Changsha", "Ordos"), unless the bare name is a province's ("Jilin City"). `pinyin` is the reading of the name without its kind, in toneless syllables with ü kept (成都市 is `cheng du`, 红河哈尼族彝族自治州 is `hong he`). It is searched but never shown. So is `old`: old romanizations of a province's or a second-level place's name, and a few well-known old names (北京: Pe-king, Pekin, Pei-ching, Peiping; 广州: Kwangchow, Canton), each chosen by hand from the place's English aliases on Wikidata and listed in `data/overrides/old-names.json`. The readings come from the character table of [pinyin-data](https://github.com/mozillazg/pinyin-data). Where a character has several readings, the one that spells the place's English name is taken. The rest were read through, and those set by hand are recorded with their reasons in `data/overrides/pinyin.json`. Both are worked out when the table is generated, by `scripts/place_names.py`.
- **Former names.** `was` holds the names a place had before (郫县 for 郫都区, 闸北区 for 静安区), which the record files were placed by and which search matches, but the page never shows. Besides the changes in the corrections, it holds names chosen from Wikidata: a place's dated official names since 1949 and the places it replaced, listed in `data/overrides/former-names.json`. Names that a place has now anywhere, that two places in a province had, or that are generic are left out. Their pinyin joins `old`.
- **The table was generated** from the source lists. The corrections applied to them are recorded in `data/overrides/divisions.json`.
- **`scripts/divisions.py`** looks units up by id and finds the units named in a piece of text, such as 四川省成都市蒲江县.

- **Framing.** When a unit is selected the page frames its largest piece and what lies close to it, so a stray island does not shrink the view. A unit that is a group of islands with no main body is marked `"frame": "all"` in `data/divisions.json` and is framed with every piece: 連江縣 and 澎湖縣.

**How the page uses it.** `build.py` writes one file into `js/data/units/` for every unit that opens: 34 provinces and 351 cities and counties. A file holds the shapes of the units directly under that unit and a detailed outline of it, made from the outer borders of its parts. A province's file also holds the names of its districts and counties, so that every record in the province can be given its place before any city is opened. The page loads a file the first time its unit is opened. Each unit in a file carries its English name, and a `tag` where another place shares that name: the build compares all English names below the provinces, kind included (so "Suzhou District" is not tagged), and tags each place sharing one with its province's English name, or its city's where two are in one province. For the trail, a mainland place below the provinces that has places under it also carries `enShort` where its English name shortens with its Chinese one ("Ngawa" for 阿坝, from "Ngawa Tibetan and Qiang Autonomous Prefecture"), a place whose short name would be its parent's carries `namesake` (长沙县 under 长沙市), and a place whose short name is a province's carries `likeProvince` (海南藏族自治州). The page makes the parent's longer form from its kind, with the `trail.long.` texts in `data/text.json`.

An open unit is drawn with its detailed outline, because its own shape comes from a coarser file and does not follow its parts exactly. For the same reason the page draws each border between two units once, as a line of its own, and hides the borders of a unit while it is open: the detailed outline takes their place.

## What is in it

| Layer | Records | Source | How complete |
| --- | --- | --- | --- |
| Signature dishes | 340 | China Cuisine Association list, 2018 | The whole list, ten per province-level unit |
| Heritage food traditions | 195 | National intangible cultural heritage register, all ten categories | The names of every item in all ten categories were read. Category Ⅷ, traditional craftsmanship, gives 168 entries: 69 of its 289 items are food or drink, listed by item number in `scripts/import_heritage.py`, and every entry of a chosen item is kept. The other categories give 27, listed there one by one: 10 food and drink customs (Ⅹ), 10 ritual breads and sugar figures listed as fine art (Ⅶ), and 7 food-like entries listed as medicine (Ⅸ). So not every entry is a technique. One entry declared by a national body has no place and is left out. The national register only; no provincial registers |
| Protected regional products | 2,810 | CNIPA recognition notices: twenty from 2021 to 2024 (414 to 601), seven from 2025 (619 to 657) and three from 2026 (663, 677, 687) | From 2025 the notices carry a product list, read as a table. The earlier ones do not: their products are read from the running text of each product's 保护要求 section, and the importer stops if the names read differ from the names the notice gives. Notices 588 to 601, 619 and 637 only name their products, so the details come from the preliminary notices they cite. 53 products are not food and are left out, as are the notices that hold only crafts, stones or European products (407, 538, 578, 658, 666). Six products that a later notice publishes again, saying it replaces the earlier entry, are counted once, in the later form with the earlier year. Places are read from the area text: neighbours named only to describe the border are left out, a city's counties listed by their stems are taken, and where a text names towns but no county, the counties of those towns are used. Where a stated position falls just outside the units the product names, the dot is moved inside their border; where it falls far outside, the dot is put at the unit's centre. Not in: notice 550 (三亚芒果, which notice 632 replaces, so its year shows as 2025), and notices 277, 331, 380, 390 and 401 (35 products), whose pages on the office's site are empty. **Not yet in: products recognised before 2021 and not republished since.** The office's 2025 statistics give 4,854 domestic products, so roughly 2,000 are missing; this is an estimate, as the two counts may not be defined alike. |
| Farm heritage systems | 277 | Agriculture ministry: topic page for batches 1 to 4, notices for batches 5 to 8 | All eight batches, 2013 to 2026. The count for each batch matches the ministry's. One entry is an extension of an earlier system to a second area |
| What people eat | 31 provinces, 15 foods | China Statistical Yearbook 2025, table 6-22 | The whole table, typed in by hand |
| Protected regional products, Taiwan | 72 | Taiwan Intellectual Property Office, register of place marks (產地證明標章 and 產地團體商標) | All 77 food marks of domestic holders, which make 72 products because five products have two marks. The 54 marks of foreign holders and one non-food mark are left out. Product names are set by hand from each mark's wording, in `scripts/import_taiwan_food.py`. Each is placed at its holder's township or county |
| Heritage food traditions, Taiwan | 19 | Bureau of Cultural Heritage register, categories 民俗 and 傳統知識與實踐 | City and county listings, shown with that label. The names of all 494 entries in three categories were read; none of the 47 nationally designated ones is about food, and 傳統工藝 has no food entry. So Taiwan's entries are at a lower level than the mainland's, which are national only |
| Heritage food traditions, Macau | 21 | Macau Cultural Affairs Bureau, inventory of intangible cultural heritage (98 items as of August 2026) | Food items chosen by reading every name, typed into `scripts/import_macau_heritage.py`. The two already on the national register are not repeated. Shown with the label "The region's own inventory". The build reads every `data/heritage_*.json` |
| Heritage food traditions, Hong Kong | 59 | Intangible Cultural Heritage Office, inventory of December 2024 (507 items) | Main items about food, chosen by reading every name, typed into `scripts/import_hk_heritage.py`: making food and drink, food customs, two medicine-like drinks, and catching and farming, which take the kind "Farming and fishing". 涼茶, already on the national register, is not repeated. No item is tied to a district |
| Food supply per person | 4 areas, 16 foods; Taiwan, 18 foods | FAO Food Balance Sheets, 2023 (mainland, Hong Kong, Macau, Taiwan); Taiwan's own 糧食平衡表 for 2025, from the ministry's yearly report (an .ods file, read with the standard library) | `data/supply.json` and `data/supply_taiwan.json`, written by `scripts/import_food_supply.py`. Shown under "What people eat" in the panel only: the four areas side by side on the overview, Hong Kong and Macau beside the mainland, and Taiwan's own sheet on Taiwan's panel. Never used for shading, because supply is not the household survey behind the provinces' figures |
| Boundaries | 34 provinces, 497 units under them, 3,096 under those (the table lists 499 under the provinces: 新星市 and 白杨市 have no shape in the source) | DataV GeoAtlas, dated 2021; inside Taiwan, the surveying centre's file of 2023 | Three levels drawn. The islands of Kinmen and Matsu are drawn for Taiwan only. Taiwan's own outline, drawn while it is closed, is still DataV's. 36 cities and counties that sit directly under a province have no level below them |

## Things to know before going further

- **Typed-in statistics.** The consumption table is published only as an image. The figures in `data/indicators.json` were typed in from it and checked once against a fresh reading of the whole image, with no differences found.
- **Approximate picks.** Products are sorted into kinds by the endings of their names, with hand corrections, recorded in `data/overrides/product-kinds.json`; those that are not food are left out.
- **Approximate places.** Most products sit at the midpoint of the coordinate range in their notice, moved just inside their unit's border where that midpoint falls slightly outside it. Heritage and farm entries, and products without coordinates, sit at the centre of the unit they belong to. Entries known only to province level have no dot and appear only in the panel.
- **Counts do not always add up.** An entry that spans several places is counted in each of them, so a province's places can add up to more than its total.
- **Boundaries at three levels of detail.** Each level comes from a separate file of the source, and the coarser files do not follow the finer ones exactly. An open province or city is therefore drawn from its parts. Where it meets a closed neighbour, the lines can be up to a few pixels apart at close zoom.
- **Traditional Chinese is converted, not written.** Names keep the mainland's wording in Traditional characters; only the interface text uses Taiwan's wording where it differs (搜尋, 資料). Quotation marks stay as “ ”. Official names are converted character by character and never reworded. Names with a character that has several Traditional forms were read through, and the corrections are listed in `data/overrides/hant.json`; a few are judgements, marked as such. No native reader of Traditional Chinese has reviewed the result.
- **The original source files are not included.** Some are marked as not for copying. `data/` holds what was taken from them.
- **The dish list is one association's selection,** not a government register.

## Switched off for now

- **Time axis.** All content is treated as current. The code is in `js/timeline.js` and records already carry a `since` year where the source gives one. Turn it on by setting `CONFIG.features.timeline` in `js/app.js`, or add `?timeline=1` to the address to try it.
- **Other countries.** The map window is set in `CONFIG.bounds` in `js/app.js`, and region ids carry a code-system prefix, so another country can be added without reworking the data. Nothing beyond Greater China is built.

## Sources

Each source used is listed with its link in `data/works.json`. The conversion to Traditional Chinese uses the dictionaries of the OpenCC project (Apache 2.0), credited in `data/hant.json`. The English names of mainland places and the old spellings come from Wikidata, and the pinyin readings from pinyin-data; both are credited in `data/works.json`.

## Licence

Copyright (C) 2026 the China Food Map contributors.

- **Code** (`index.html`, `css/`, the scripts in `js/` other than `js/data/`, and `scripts/`): the GNU General Public License, version 3. See `LICENSE`.
- **Data** (`data/`, and the files built from it in `js/data/`): Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International. You may share and adapt it for non-commercial purposes, if you credit China Food Map and share your adaptations under the same licence. See `LICENSE-DATA`.
- **Exception:** the conversion tables in `data/hant.json`, and the table built from them in `js/data/names/zh-hant.js`, come from the [OpenCC](https://github.com/BYVoid/OpenCC) project and remain under the Apache License 2.0. See `LICENSE-OPENCC`.

These licences cover this project's own work. The facts it draws on come from the sources listed in `data/works.json` and shown in the page's source lists. Material from Taiwan's open government data is used under the Open Government Data License, version 1.0, with the attribution given there.

