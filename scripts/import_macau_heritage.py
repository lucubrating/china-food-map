#!/usr/bin/env python3
"""Write Macau's food heritage entries from its own inventory.

Source: the inventory of intangible cultural heritage (非物質文化遺產清單) kept by Macau's
Cultural Affairs Bureau, as listed on https://www.culturalheritage.mo/detail/102318, as of
August 2026. The page is a table of 98 items with the year each was entered (2017, 2020 or
2026). There is no file to download, so the food items are typed in below, by their number on
the page. All 98 names were read.

Left out:
  12 涼茶配製 and 14 土生葡人美食烹飪技藝, which are already on the map from the national
     register (Ⅷ-89 and Ⅷ-280);
  25 栗子節, a feast day, and 57 麵塑技藝, a craft whose product is not eaten.

Twelve of the inventory's items were raised to Macau's list (名錄) in 2019 and twelve more in
2025; LISTED marks the food ones among them, and the record's reference says so.

Names. The page writes Traditional Chinese. `title` is converted to Simplified, like the rest
of the data, and `hant` keeps the page's own wording, which the page of the map shows as it
stands.

Output: data/heritage_macau.json

Usage: python3 -I scripts/import_macau_heritage.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA_DIR, read_json, write_json  # noqa: E402
from import_taiwan import T2S, simplified_chinese  # noqa: E402

MACAU = "cn:820000"

# Number on the page -> (name, year entered, kind).
ITEMS = {
    62: ("土生葡人美食烹飪技藝－牛油糕製作技藝", 2020, "staple"),
    63: ("葡撻製作技藝", 2020, "staple"),
    64: ("龍鬚糖製作技藝", 2020, "staple"),
    65: ("唐餅製作技藝", 2020, "staple"),
    66: ("杏仁餅製作技藝", 2020, "staple"),
    67: ("嫁喜禮餅製作技藝", 2020, "staple"),
    68: ("醬料釀造技藝", 2020, "condiment"),
    69: ("涼果製作技藝", 2020, "staple"),
    70: ("竹昇麵製作技藝", 2020, "staple"),
    76: ("土生葡人肥茶習俗", 2026, "cuisine"),
    77: ("飲茶習俗", 2026, "tea"),
    85: ("燒味製作技藝", 2026, "meat"),
    86: ("糉製作技藝", 2026, "staple"),
    87: ("花生糖製作技藝", 2026, "staple"),
    88: ("西餅製作技藝", 2026, "staple"),
    89: ("緬甸麵食製作技藝", 2026, "staple"),
    90: ("印尼糕點小食製作技藝", 2026, "staple"),
    91: ("客家茶粿製作技藝", 2026, "staple"),
    92: ("冷糕製作技藝", 2026, "staple"),
    93: ("豬扒包製作技藝", 2026, "staple"),
    94: ("奶茶製作技藝", 2026, "tea"),
}

# Items also on Macau's list (名錄), by the Chief Executive's order 114/2025.
LISTED = {63, 66, 67, 70}


def main():
    table = {}
    with open(T2S, encoding="utf-8") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) >= 2:
                table[parts[0]] = parts[1]
    records = []
    for number, (name, year, kind) in sorted(ITEMS.items()):
        loc = "清单第%d项（%d年）" % (number, year)
        if number in LISTED:
            loc += "；2025年列入名录"
        records.append({
            "id": "heritage:mo:%d" % number,
            "title": simplified_chinese(name, table),
            "hant": {"title": name},
            "kind": kind,
            "level": "regional",
            "region": MACAU,
            "areas": [MACAU],
            "refs": [{"w": "macau-ich-inventory", "loc": loc}],
            "since": year,
        })
    write_json(os.path.join(DATA_DIR, "heritage_macau.json"), records)
    print("heritage entries: %d" % len(records))
    for record in records:
        print("  %s  %s" % (record["id"], record["title"]))


if __name__ == "__main__":
    main()
