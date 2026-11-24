"""English names and pinyin readings for the places in the divisions table.

Used by scripts/import_divisions.py, which calls find_names() just before it writes
data/divisions.json, and by the build script, which asks english_short() for the trail's short
English names.

Sources (downloaded into research/downloads/):
  wikidata-names/names.csv   Wikidata items carrying a six-digit division code (P442 or P13971),
                             with their English and Chinese labels, fetched for the table's own
                             codes by fetch.py beside it.
  pinyin-data/pinyin.txt     the readings of each Chinese character, from mozillazg/pinyin-data

English names. Only places on the mainland below the first level take one from Wikidata; Taiwan's,
Hong Kong's and Macau's already have their official English names. An item is used when its code
is the place's code, it has not been dissolved, and either its Chinese label is the place's name
or its English name spells one reading of the place's name (so a slip in a Chinese label does not
lose a good English name, and an item filed under the wrong code is not used). Wikipedia-style
additions are dropped: "Ningjin County, Hebei" becomes "Ningjin County", but a comma inside a name
is kept ("Zhenyuan Yi, Hani and Lahu Autonomous County"). A city at the second level
is named without "City", as most are in Wikidata already ("Ordos City" becomes "Ordos"), unless the
bare name is a province's: 吉林市 stays "Jilin City".

Pinyin. For searching only, never shown. It is the reading of the name without its kind (成都 for
成都市, 红河 for 红河哈尼族彝族自治州), in toneless syllables separated by spaces, with ü kept.
A one-character name keeps its kind (道县 is "dao xian"). Many characters have several readings,
and place names often use the less common one (长沙, 蚌埠, 六安). Each character's reading is
chosen in this order:
  1. a reading given for the place, or for the character, in data/overrides/pinyin.json
     (a place's reading is either a correction or one read through and found right);
  2. the reading that spells the place's English name, where that name is pinyin;
  3. the reading the character has in most of the names settled by step 2;
  4. the table's first reading.
Names where steps 3 or 4 decided a character with several readings, and where the evidence is
weak or missing, are listed so they can be read through. A name is settled for good by giving
its reading in the corrections file, under "names" with a reason, or under "checked" when the
reading found was right.

Old names. For searching only, never shown: old romanizations of a place's name and a few
well-known old names (Pe-king and Peiping for Beijing, Amoy for Xiamen, Canton for Guangzhou),
chosen by hand from Wikidata's English aliases and listed in data/overrides/old-names.json. Each is
checked against the aliases download (wikidata-names/aliases.csv, by fetch_aliases.py), when it is
there, and must not be another place's name or pinyin.
"""
import collections
import csv
import itertools
import os
import re
import unicodedata

from common import DATA_DIR, DOWNLOADS_DIR, read_json

NAMES_CSV = os.path.join(DOWNLOADS_DIR, "wikidata-names", "names.csv")
PINYIN_TXT = os.path.join(DOWNLOADS_DIR, "pinyin-data", "pinyin.txt")
OVERRIDES = os.path.join(DATA_DIR, "overrides", "pinyin.json")
OLD_NAMES = os.path.join(DATA_DIR, "overrides", "old-names.json")
FORMER_NAMES = os.path.join(DATA_DIR, "overrides", "former-names.json")
ALIASES_CSV = os.path.join(DOWNLOADS_DIR, "wikidata-names", "aliases.csv")

# The kind at the end of a name, left out of its reading. Longest first.
GROUPS = ("汉|蒙古|蒙|回|藏|维吾尔|苗|彝|壮|布依|朝鲜|满|侗|瑶|白|土家|哈尼|哈萨克|傣|黎|傈僳|佤|畲|高山|拉祜|水|"
          "东乡|纳西|景颇|柯尔克孜|土|达斡尔|仫佬|羌|布朗|撒拉|毛南|仡佬|锡伯|阿昌|普米|塔吉克|怒|乌孜别克|"
          "俄罗斯|鄂温克|德昂|保安|裕固|京|塔塔尔|独龙|鄂伦春|赫哲|门巴|珞巴|基诺|各")
# The peoples named before 自治 (满族, 布依族苗族, 各族), or before 区 in an ethnic district.
ETHNIC = re.compile(r"((%s)族)*自治(州|县|旗|区)$|((%s)族)+区$|锡伯自治县$" % (GROUPS, GROUPS))
KINDS = ("特别行政区", "行政委员会", "工矿特区", "特别市", "直辖市", "工矿区", "堂区", "新区", "矿区", "林区", "特区",
         "地区", "专区", "盟", "旗", "县", "市", "区", "镇", "乡")
# Words that end an English name and say what kind of place it is.
EN_KIND = re.compile(r"\s+(Autonomous|Mining|New|Forestry|Special|District|County|City|Prefecture|"
                     r"League|Banner|Township|Town|Area|Region)\b.*$")
# Places whose official English names the divisions table already has: Taiwan's, Hong Kong's, Macau's.
LOCAL_EN = ("tw:", "hk:", "mo:", "cn:71", "cn:81", "cn:82")




def letters(text):
    """Lower-case ASCII letters only: "Chang'an District" -> "changandistrict", ü -> u."""
    text = unicodedata.normalize("NFD", text.lower())
    return re.sub(r"[^a-z]", "", text)


def read_readings():
    """{character: [toneless readings, most common first as the table orders them]}."""
    table = {}
    with open(PINYIN_TXT, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#") or ":" not in line:
                continue
            code, rest = line.split(":", 1)
            readings = []
            for reading in rest.split("#")[0].strip().split(","):
                plain = "".join(c for c in unicodedata.normalize("NFD", reading.strip())
                                if not unicodedata.combining(c) or c == "̈")
                plain = unicodedata.normalize("NFC", plain)
                if plain and plain not in readings:
                    readings.append(plain)
            table[chr(int(code[2:], 16))] = readings
    return table


def core(unit):
    """The part of a name that is read: without its kind, unless that leaves one character.

    A province is read by its short name (内蒙古, 新疆, 香港).
    """
    name = unit["name"]
    if unit["depth"] == 1:
        return unit["short"]
    bare = ETHNIC.sub("", name)
    if not bare:  # the people is the name: 鄂温克族自治旗, 东乡族自治县
        bare = re.sub(r"族自治(州|县|旗|区)$", "", name)
    if bare == name:
        # The longest kind that still leaves two characters: 杉林区 is 杉林, not 杉 of a 林区.
        for kind in KINDS:
            if name.endswith(kind) and len(name) - len(kind) > 1:
                bare = name[:-len(kind)]
                break
    return bare if len(bare) > 1 else name


def wikidata_items():
    """{code: [rows]} from the Wikidata download, codes without their spaces."""
    items = collections.defaultdict(list)
    with open(NAMES_CSV, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            items[row["raw"].replace(" ", "")].append(row)
    return items


# A comma after one of these words starts an addition that tells places apart ("Ningjin County,
# Hebei"); any other comma is part of the name ("Zhenyuan Yi, Hani and Lahu Autonomous County").
ADDITION = re.compile(r"\b(County|District|City|Prefecture|Banner|League),.*$")


def plain_english(label):
    """Wikidata's English label without additions made to tell places apart, and without a comma
    before the last "and" of a list of peoples, which Wikidata writes only sometimes: "Jinping
    Miao, Yao and Dai Autonomous County", like "Yuanjiang Hani, Yi and Dai Autonomous County"."""
    label = re.sub(r"\s*\(.*\)$", "", ADDITION.sub(r"\1", label)).strip()
    return label.replace(", and ", " and ")


def spells(chars, readings, english):
    """The readings of `chars` that spell the start of `english`, or None."""
    target = letters(EN_KIND.sub("", english)) or letters(english)
    options = [[r for r in readings.get(c, [])] or ["?"] for c in chars]
    if any(len(o) > 6 for o in options) or sum(len(o) for o in options) > 40:
        return None
    for combo in itertools.product(*options):
        if letters("".join(combo)) == target:
            return list(combo)
    return None


# Peoples named in English before "Autonomous", in the spellings Wikidata uses.
EN_PEOPLES = ("Tibetan|Qiang|Yi|Hani|Miao|Dong|Zhuang|Hui|Mongol|Mongolian|Manchu|Korean|Uyghur|Uygur|"
              "Kazakh|Kazak|Kyrgyz|Kirgiz|Dai|Bai|Naxi|Lisu|Lahu|Va|Wa|Jingpo|Blang|Bulang|Tujia|Bouyei|"
              "Buyei|She|Li|Yao|Mulao|Maonan|Gelao|Shui|Sui|Salar|Bonan|Dongxiang|Yugur|Tu|Xibe|Daur|"
              "Evenki|Ewenki|Oroqen|Pumi|Nu|Derung|Drung|Tajik|Russian")
EN_TRAIL_KIND = re.compile(r"\s+(Autonomous (Prefecture|County|Banner|Region)|Prefecture|County|District|"
                           r"City|League)$", re.IGNORECASE)
EN_TRAIL_PEOPLES = re.compile(r"(\s*(,\s*and|,|and)?\s*\b(%s)\b)+$" % EN_PEOPLES)


def english_short(en):
    """The English counterpart of a Chinese short name, for the trail: the official name without
    its kind, and for an autonomous unit without the peoples named before "Autonomous".

    "Ngawa Tibetan and Qiang Autonomous Prefecture" -> "Ngawa", "Aksu Prefecture" -> "Aksu".
    A name that would be left empty keeps its peoples ("Dongxiang Autonomous County" ->
    "Dongxiang"), and a name without a kind at its end is returned as it is.
    """
    bare = EN_TRAIL_KIND.sub("", en)
    if bare != en and re.search(r"\bAutonomous\b", en):
        fewer = EN_TRAIL_PEOPLES.sub("", bare).strip(" ,")
        bare = fewer or bare
    return bare.strip() or en


def old_names(units, english, pinyin):
    """The old names of data/overrides/old-names.json, checked: ({id: [names]}, problems)."""
    listed = read_json(OLD_NAMES)["names"]
    by_id = {unit["id"]: unit for unit in units}
    problems = []
    aliases = collections.defaultdict(set)
    if os.path.exists(ALIASES_CSV):
        with open(ALIASES_CSV, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                aliases["cn:" + row["raw"].replace(" ", "")].add(row["alias"])
    # Every name a place is found by already, as search compares them.
    taken = collections.defaultdict(set)
    for unit in units:
        for name in (english.get(unit["id"]) or unit.get("en", ""), pinyin.get(unit["id"], ""), unit["short"]):
            if letters(name):
                taken[letters(name)].add(unit["id"])
    for uid, names in listed.items():
        if uid not in by_id:
            problems.append("old names: %s is not in the divisions table" % uid)
            continue
        for name in names:
            if aliases and name not in aliases.get(uid, ()):
                problems.append("old names: %r is not among %s's aliases on Wikidata" % (name, uid))
            others = taken.get(letters(name), set()) - {uid}
            if others:
                problems.append("old names: %r of %s is also the name of %s" % (name, uid, ", ".join(sorted(others))))
    return listed, problems


def former_names(units):
    """The former names of data/overrides/former-names.json, checked: ({id: [names]}, problems).

    A former name must not be a name some place has now, anywhere, and must belong to one place in
    its province, so that a text naming it is never placed wrongly and a search for it is not
    misled. Places in two provinces may share one (南市区 in Baoding and in Shanghai).
    """
    listed = read_json(FORMER_NAMES)["names"]
    by_id = {unit["id"]: unit for unit in units}
    current = collections.defaultdict(set)
    for unit in units:
        current[unit["name"]].add(unit["id"])
    problems, owner = [], {}

    def province(uid):
        while by_id[uid]["depth"] > 1:
            uid = by_id[uid]["parent"]
        return uid

    for uid, names in listed.items():
        if uid not in by_id:
            problems.append("former names: %s is not in the divisions table" % uid)
            continue
        for name in names:
            if current.get(name):
                problems.append("former names: %s, listed for %s, is the name of %s now" % (
                    name, uid, ", ".join(sorted(current[name]))))
            key = (province(uid), name)
            if key in owner and owner[key] != uid:
                problems.append("former names: %s is listed for both %s and %s" % (name, owner[key], uid))
            owner[key] = uid
    return listed, problems


def find_names(units):
    """English names, pinyin and old names for `units`, the rows of the divisions table about to
    be written.

    Returns ({id: English name}, {id: pinyin}, {id: [old names]}, {id: [former Chinese names]},
    {id: [readings of those]}, report lines, problems). The English names are only those taken
    from Wikidata; names already in a row are left to it.
    """
    missing = [os.path.relpath(path, os.path.dirname(DATA_DIR)) for path in (NAMES_CSV, PINYIN_TXT) if not os.path.exists(path)]
    if missing:
        return {}, {}, {}, {}, {}, [], ["place names: missing download %s" % path for path in missing]
    readings = read_readings()
    fixes = read_json(OVERRIDES)
    by_id = {unit["id"]: unit for unit in units}
    fixed_chars, fixed_en = fixes.get("chars", {}), fixes.get("en", {})
    # Readings read through and found right ("checked") are kept as they are, like corrections.
    fixed_names = dict(fixes.get("checked", {}), **fixes.get("names", {}))
    items = wikidata_items()
    problems, notes = [], []

    # English names from Wikidata, for mainland places below the first level.
    provinces_en = {unit["en"].lower() for unit in units if unit["depth"] == 1 and unit.get("en")}
    english = {}
    for unit in units:
        uid = unit["id"]
        # An English name already in the table counts only for the places listed in LOCAL_EN and
        # the provinces: any other came from an earlier run of this script and is looked up again.
        if unit["depth"] == 1 or uid.startswith(LOCAL_EN):
            continue
        if uid in fixed_en:
            english[uid] = fixed_en[uid]
            continue
        rows = items.get(uid.split(":")[1], [])
        live = [r for r in rows if r["en"] and not r["dissolved"]] or [r for r in rows if r["en"]]
        chosen = None
        for row in live:
            name = plain_english(row["en"])
            if row["zh"] == unit["name"] or spells(core(unit), readings, name):
                chosen = name
                break
        if chosen and unit["depth"] == 2 and unit["name"].endswith("市") and chosen.endswith(" City"):
            # A city at the second level is named without "City", as most already are in Wikidata
            # (Changsha, Ordos), unless the bare name is a province's (Jilin City, not Jilin).
            if chosen[:-len(" City")].lower() not in provinces_en:
                chosen = chosen[:-len(" City")]
        if chosen:
            english[uid] = chosen
        else:
            notes.append("no English name for %s %s (Wikidata: %s)" % (
                uid, unit["name"], "; ".join("%s %s" % (r["zh"], r["en"]) for r in live) or "nothing"))

    # Readings settled by an English name that is pinyin.
    settled, learned = {}, collections.defaultdict(collections.Counter)
    for unit in units:
        name = english.get(unit["id"]) or unit.get("en")
        chars = core(unit)
        combo = spells(chars, readings, name) if name else None
        if combo:
            settled[unit["id"]] = combo
            for char, reading in zip(chars, combo):
                learned[char][reading] += 1

    def read_chars(chars, label):
        """A reading for `chars` from the corrections, the readings learned above and the table:
        (syllables, the characters decided on weak evidence)."""
        combo, weak = [], []
        for char in chars:
            options = readings.get(char)
            if not options:
                problems.append("%s: no reading for %s" % (label, char))
                options = ["?"]
            if char in fixed_chars:
                combo.append(fixed_chars[char])
                continue
            seen = learned.get(char)
            if seen:
                reading, count = seen.most_common(1)[0]
                combo.append(reading)
                if len(options) > 1 and count < 0.9 * sum(seen.values()):
                    weak.append("%s: %s" % (char, ", ".join("%s %d" % kv for kv in seen.most_common())))
            else:
                combo.append(options[0])
                if len(options) > 1:
                    weak.append("%s: %s (no evidence)" % (char, "/".join(options[:4])))
        return combo, weak

    # Every place's reading.
    pinyin, doubtful = {}, []
    for unit in units:
        uid, chars = unit["id"], core(unit)
        if uid in fixed_names:
            pinyin[uid] = fixed_names[uid]
            continue
        combo = list(settled.get(uid) or [])
        weak = []
        if not combo:
            combo, weak = read_chars(chars, "%s %s" % (uid, unit["name"]))
        else:
            # A correction for a character still wins over an English name that happens to spell
            # another reading; such a clash is reported.
            for i, char in enumerate(chars):
                if char in fixed_chars and fixed_chars[char] != combo[i]:
                    notes.append("%s %s: English name reads %s as %s, corrections say %s" % (
                        uid, unit["name"], char, combo[i], fixed_chars[char]))
        pinyin[uid] = " ".join(combo)
        if weak:
            doubtful.append("%s %s -> %s   [%s]" % (uid, unit["name"], pinyin[uid], "; ".join(weak)))

    for uid in sorted(set(fixed_names) - {u["id"] for u in units}):
        problems.append("pinyin corrections name %s, which is not in the divisions table" % uid)
    report = ["place names: English names from Wikidata %d | readings settled by an English name %d | "
              "corrected %d | checked %d" % (len(english), len(settled), len(fixes.get("names", {})),
                                             len(fixes.get("checked", {})))]
    report += ["  ? " + note for note in notes]
    report.append("readings to read through: %d" % len(doubtful))
    report += ["    " + line for line in doubtful]
    old, old_problems = old_names(units, english, pinyin)
    problems += old_problems
    report.append("old names: %d for %d places" % (sum(len(v) for v in old.values()), len(old)))

    # Former Chinese names, with a reading of each for searching (see former_names).
    former, former_problems = former_names(units)
    problems += former_problems
    fixed_former = fixes.get("former", {})
    former_pinyin, former_doubtful = {}, []
    for uid, names in former.items():
        for name in names:
            if name in fixed_former:
                reading = fixed_former[name]
            else:
                combo, weak = read_chars(core({"name": name, "depth": 3, "short": name}), "former name %s" % name)
                reading = " ".join(combo)
                if weak:
                    former_doubtful.append("%s %s (now %s) -> %s   [%s]" % (uid, name, by_id[uid]["name"], reading, "; ".join(weak)))
            former_pinyin.setdefault(uid, []).append(reading)
    report.append("former names: %d for %d places | readings to read through: %d" % (
        sum(len(v) for v in former.values()), len(former), len(former_doubtful)))
    report += ["    " + line for line in former_doubtful]
    return english, pinyin, old, former, former_pinyin, report, problems
