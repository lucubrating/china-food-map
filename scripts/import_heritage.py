#!/usr/bin/env python3
"""Import food and drink entries from the national intangible cultural heritage register.

Source: research/downloads/ihchina-register/, all ten categories of https://www.ihchina.cn/project.html
as served by its data feed: crafts-page-*.json is category Ⅷ, 传统技艺 (traditional craftsmanship),
and type-N-page-*.json the other nine.
Output: data/heritage.json

The register has no food category, so the food and drink items are listed here by item number
(FOOD_ITEMS), chosen by reading the names of all 289 items in the category. Every entry of a
listed item is kept. The names of every item in the other nine categories were read as well, and
the few entries there that are food or drink are listed one by one (OTHER_ENTRIES), by item number
and a word of the title. The register's descriptive prose is not kept.

Usage: python3 scripts/import_heritage.py
"""
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA_DIR, DOWNLOADS_DIR, PROVINCES, read_json, region_id, write_json  # noqa: E402
from divisions import Divisions  # noqa: E402

# Kind of food or drink, tested in this order against the title.
KINDS = [
    ("tea", r"茶(?!具|壶|罐|盘)"),
    ("liquor", r"酒(?!具|器)|酿造技艺（.*酒|蒸馏酒|黄酒"),
    ("condiment", r"醋|酱油|豆豉|豆瓣|腐乳|酱(?!釉)|制盐|晒盐|井盐|盐(?=制作|生产)|食用油|香油|麻油|茶油|榨油|糖(?!画|塑|人)"),
    ("cuisine", r"烹饪|烹制|菜(?!刀)|宴|素食|小吃|火锅"),
    ("meat", r"火腿|烤鸭|烧鸡|扒鸡|板鸭|牛肉|羊肉|肉(?!桂)|腊味|熏鱼|鱼(?=制作|烹)"),
    ("staple", r"面食|面条|拉面|饸饹|刀削|米粉|粉丝|粉条|饼|糕|月饼|粽|汤圆|元宵|饺|馍|馒头|包子|豆腐|泡菜|榨菜|酸菜|咸菜|奶|乳(?!胶)|蜜饯|凉果"),
]
# Item numbers in category Ⅷ that are food or drink. Left out on purpose: Ⅷ-47 (a water mill),
# Ⅷ-85 (fish-skin clothing) and Ⅷ-143 (plant-ash alkali).
FOOD_ITEMS = set(list(range(57, 65)) + [89] + list(range(144, 174)) + list(range(203, 208))
                 + list(range(226, 236)) + list(range(266, 281)))
# Kinds for items whose titles the word rules above cannot sort.
ITEM_KINDS = {63: "tea", 171: "staple", 172: "cuisine", 173: "cuisine", 204: "cuisine", 229: "condiment",
              235: "staple", 278: "staple"}
ROMAN = {"Ⅰ": "I", "Ⅱ": "II", "Ⅲ": "III", "Ⅳ": "IV", "Ⅴ": "V", "Ⅵ": "VI", "Ⅶ": "VII", "Ⅷ": "VIII", "Ⅸ": "IX", "Ⅹ": "X"}


# Entries outside category Ⅷ: (item number, a word the title must hold or "" for every entry of
# the item, kind). In three groups: food and drink customs
# (Ⅹ), edible things listed as fine art (Ⅶ), and food-like things listed as medicine (Ⅸ).
OTHER_ENTRIES = [
    ("Ⅹ-107", "", "tea"),            # 潮州工夫茶艺, 白族三道茶, 瑶族油茶习俗
    ("Ⅹ-140", "", "tea"),            # 径山茶宴
    ("Ⅹ-84", "赶茶场", "tea"),
    ("Ⅹ-150", "", "cuisine"),        # 仡佬族三幺台习俗
    ("Ⅹ-179", "", "cuisine"),        # 徐州伏羊食俗
    ("Ⅹ-180", "", "cuisine"),        # 德都蒙古全席
    ("Ⅹ-181", "", "cuisine"),        # 尖扎达顿宴
    ("Ⅹ-71", "敛巧饭", "cuisine"),
    ("Ⅶ-53", "", "staple"),          # 面花, ritual breads
    ("Ⅶ-88", "", "staple"),          # 糖塑, sugar figures
    ("Ⅸ-10", "药膳八珍汤", "cuisine"),
    ("Ⅸ-10", "万应茶", "tea"),        # 灵源万应茶, 永定万应茶
    ("Ⅸ-3", "新会陈皮", "condiment"),
    ("Ⅸ-21", "食物疗法", "cuisine"),
    ("Ⅸ-21", "和田药茶", "tea"),
    ("Ⅸ-15", "九节茶药", "tea"),
]
OTHER_COUNT = 27  # how many entries the list above should find; the run stops if it differs


def item_number(num):
    match = re.fullmatch(r"Ⅷ-(\d+)", num or "")
    return int(match.group(1)) if match else None


def kind_of(title, num):
    """The kind of a register entry, or None if its item is not food or drink."""
    for other, word, kind in OTHER_ENTRIES:
        if num == other and word in title:
            return kind
    item = item_number(num)
    if item not in FOOD_ITEMS:
        return None
    if item in ITEM_KINDS:
        return ITEM_KINDS[item]
    for kind, pattern in KINDS:
        if re.search(pattern, title):
            return kind
    sys.exit("no kind for %s %s: add it to ITEM_KINDS" % (num, title))


def is_code(value):
    return bool(re.fullmatch(r"\d{6}", value or ""))


def main():
    folder = os.path.join(DOWNLOADS_DIR, "ihchina-register")
    pages = sorted(glob.glob(os.path.join(folder, "crafts-page-*.json"))) + sorted(glob.glob(os.path.join(folder, "type-*-page-*.json")))
    rows = []
    for path in pages:
        rows.extend(read_json(path).get("list") or [])
    divisions = Divisions()

    province_codes = {code for code, _full, _short, _en in PROVINCES}
    records, seen, national = [], set(), []
    placed_by = {}
    for row in rows:
        title = re.sub(r"\s+", "", row.get("title") or "")
        kind = kind_of(title, row.get("num"))
        if not kind:
            continue
        if not is_code(row.get("address")):
            # Two rows have no province code but do have a city code, which begins with it.
            lower = row.get("city") if is_code(row.get("city")) else row.get("area")
            if not is_code(lower):
                sys.exit("no place codes for %s %s" % (row.get("num"), title))
            row["address"] = lower[:2] + "0000"
        if row["address"] not in province_codes:
            # Declared by a national body, not a place, so it cannot be put on the map.
            national.append("%s（%s）" % (title, re.sub(r"\s+", "", row.get("unit") or "")))
            continue
        num = row.get("num") or ""
        num_ascii = "".join(ROMAN.get(ch, ch) for ch in num)
        place_code = row.get("area") if is_code(row.get("area")) else (row.get("city") if is_code(row.get("city")) else row["address"])
        rid = "heritage:%s:%s" % (num_ascii, place_code)
        if rid in seen:
            rid += ":%s" % row.get("id")
        seen.add(rid)
        year = re.search(r"(\d{4})", row.get("rx_time") or "")
        record = {
            "id": rid,
            "title": title,
            "kind": kind,
            "level": "national",
            "region": region_id(row["address"]),
            "place": re.sub(r"\s+", "", row.get("unit") or row.get("province") or ""),
            "refs": [{"w": "ich-national", "loc": num}],
        }
        if year:
            record["since"] = int(year.group(1))
        # Where the entry belongs, as exactly as the register says: its district code, then the
        # places named in its declaring unit, then its city code. Codes in the register are those
        # of the year of listing, so some are no longer in use; names catch most of those.
        region = record["region"]
        areas, how = [], "province"
        for key, label in (("area", "district code"), ("unit", "name"), ("city", "city code")):
            if key == "unit":
                found = divisions.locate(record["place"], region)
            else:
                unit_id = region_id(row.get(key) or "")
                found = [unit_id] if divisions.get(unit_id) and unit_id != region and divisions.inside(unit_id, region) else []
            if found:
                areas, how = found, label
                break
        record["areas"] = areas or [region]
        placed_by[how] = placed_by.get(how, 0) + 1
        centre = divisions.centre_of(areas)
        if centre:
            record["coord"] = centre
            record["approx"] = True  # a unit's centre, not a stated position
        records.append(record)

    others = sum(1 for r in records if not r["refs"][0]["loc"].startswith("Ⅷ"))
    if others != OTHER_COUNT:
        sys.exit("entries from the other categories: %d found, %d expected" % (others, OTHER_COUNT))
    records.sort(key=lambda r: r["id"])
    out = write_json(os.path.join(DATA_DIR, "heritage.json"), records)
    by_kind = {}
    for r in records:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
    print("register rows read: %d | food and drink entries kept: %d" % (len(rows), len(records)))
    print("by kind:", by_kind)
    depth = {}
    for r in records:
        level = max(divisions.get(a)["depth"] for a in r["areas"])
        depth[level] = depth.get(level, 0) + 1
    print("provinces: %d | placed at third level: %d, second level: %d, province only: %d" % (
        len({r["region"] for r in records}), depth.get(3, 0), depth.get(2, 0), depth.get(1, 0)))
    print("placed by:", placed_by)
    if national:
        print("left out, declared by a national body:", "、".join(national))
    print("titles:", "、".join(sorted({re.sub(r"（.*", "", r["title"]) for r in records})))
    print("wrote", os.path.relpath(out))


if __name__ == "__main__":
    main()
