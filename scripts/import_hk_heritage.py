#!/usr/bin/env python3
"""Write Hong Kong's food heritage entries from its own inventory.

Source: 香港非物質文化遺產清單（2024年12月更新版）, the Intangible Cultural Heritage Office's
inventory of 507 items, a PDF (research/downloads/hk-heritage/ich_inventory_2024_cn.pdf). Each
item has a number, a name and a short description; none is tied to a district. All names were
read, and the food items are typed in below by their number, because the numbering in the PDF's
text is broken in places.

Taken: the main items about making food and drink, food customs, two medicine-like drinks, and
catching, farming and harvest, which take the kind "farming". Sub-items (飛機欖 under 涼果,
灰水糭 under 糭) are not listed separately, except 蛇酒 and 甘和茶/盒仔茶, whose main items
(傳統中醫藥文化, 中醫傳統製劑方法) are not about food.

Left out:
  4.1.1 涼茶, already on the map from the national register (Ⅷ-89);
  5.59 麵塑技藝, 5.90 漁網編織技藝, and the makers' tools 5.78 砧板, 5.79 蒸籠 and 5.80 餅模.

The inventory was first published in 2014. Items entered by the update of 2024 are dated 2024
(the office's list of that update, items_for_inclusion_ich_inventory_cn.pdf). LISTED marks the
items on Hong Kong's Representative List (代表作名錄).

Names. The inventory writes Traditional Chinese. `title` is converted to Simplified, like the
rest of the data, and `hant` keeps the inventory's own wording, shown as it stands.

Output: data/heritage_hongkong.json

Usage: python3 -I scripts/import_hk_heritage.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA_DIR, write_json  # noqa: E402
from import_taiwan import T2S, simplified_chinese  # noqa: E402

HONG_KONG = "cn:810000"

# Number in the inventory -> (name, kind).
ITEMS = {
    "3.57": ("菜茶", "cuisine"),
    "3.58": ("食山頭", "cuisine"),
    "3.59": ("盆菜", "cuisine"),
    "3.79": ("坐月薑醋", "cuisine"),
    "4.1.2": ("蛇酒", "liquor"),
    "4.1.4.1": ("甘和茶/盒仔茶", "tea"),
    "5.1": ("豆豉製作技藝", "condiment"),
    "5.2": ("豆品製作技藝", "staple"),
    "5.3": ("海鮮醬製作技藝", "condiment"),
    "5.4": ("涼果製作技藝", "staple"),
    "5.5": ("豉油釀製技藝（本地醬園）", "condiment"),
    "5.6": ("麻油製作技藝", "condiment"),
    "5.7": ("魚膠製作技藝", "meat"),
    "5.8": ("蝦膏蝦醬製作技藝", "condiment"),
    "5.9": ("醃菜製作技藝", "condiment"),
    "5.10": ("醬油釀製技藝（福建醬園）", "condiment"),
    "5.11": ("臘味製作技藝", "meat"),
    "5.12": ("糯米酒釀製技藝", "liquor"),
    "5.13": ("蠔豉蠔油製作技藝", "condiment"),
    "5.14": ("麵豉製作技藝", "condiment"),
    "5.15": ("鹹魚製作技藝", "meat"),
    "5.16": ("月餅製作技藝", "staple"),
    "5.17": ("瓜子製作技藝", "staple"),
    "5.18": ("婚嫁禮餅製作技藝", "staple"),
    "5.19": ("潮州食品製作技藝", "staple"),
    "5.21": ("糭製作技藝", "staple"),
    "5.22": ("手粉製作技藝", "staple"),
    "5.23": ("石榴仔製作技藝", "staple"),
    "5.24": ("茶粿製作技藝", "staple"),
    "5.25": ("清明仔製作技藝", "staple"),
    "5.26": ("蕃薯餅製作技藝", "staple"),
    "5.27": ("客家菜菜式", "cuisine"),
    "5.28": ("粵菜菜式", "cuisine"),
    "5.29": ("茶樓點心製作技藝", "staple"),
    "5.30": ("潮州滷水食品製作技藝", "cuisine"),
    "5.31": ("水餃製作技藝", "staple"),
    "5.32": ("打麵技藝", "staple"),
    "5.33": ("蛋撻製作技藝", "staple"),
    "5.34": ("菠蘿包製作技藝", "staple"),
    "5.35": ("雲吞製作技藝", "staple"),
    "5.36": ("港式奶茶製作技藝", "tea"),
    "5.37": ("鴛鴦製作技藝", "tea"),
    "5.38": ("叮叮糖製作技藝", "staple"),
    "5.39": ("吹糖技藝", "staple"),
    "5.40": ("龍鬚糖技藝", "staple"),
    "5.89": ("捕魚技藝", "farming"),
    "5.91": ("海水魚養殖技藝", "farming"),
    "5.92": ("基圍操作技藝", "farming"),
    "5.93": ("淡水魚養殖技藝", "farming"),
    "5.94": ("蠔養殖技藝", "farming"),
    "5.95": ("稻米種植技藝", "farming"),
    "5.96": ("蔬菜種植技藝", "farming"),
    "5.97": ("鹽曬製技藝", "farming"),
    "5.98": ("蜂蜜製作技藝", "farming"),
    "5.99": ("豬隻飼養技藝", "farming"),
    "5.100": ("雞隻飼養技藝", "farming"),
    "5.102": ("炒米餅製作技藝", "staple"),
    "5.103": ("炒米通製作技藝", "staple"),
    "5.104": ("潮州工夫茶藝", "tea"),
}

# Entered by the update of 2024; the rest date from the first inventory, of 2014.
NEW_IN_2024 = {"3.79", "4.1.4.1", "5.102", "5.103", "5.104"}

# On the Representative List: 食盆 (the inventory's 盆菜) and 港式奶茶製作技藝.
LISTED = {"3.59", "5.36"}


def number_key(number):
    return [int(part) for part in number.split(".")]


def main():
    table = {}
    with open(T2S, encoding="utf-8") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) >= 2:
                table[parts[0]] = parts[1]
    # 糭 (5.21) is left as it is: the table has no Simplified form for this variant, and Macau's
    # inventory writes the same title with 糉, so the two cannot share one Simplified title.
    records = []
    for number in sorted(ITEMS, key=number_key):
        name, kind = ITEMS[number]
        year = 2024 if number in NEW_IN_2024 else 2014
        loc = "清单第%s项" % number
        if number in LISTED:
            loc += "；已列入代表作名录"
        records.append({
            "id": "heritage:hk:" + number,
            "title": simplified_chinese(name, table),
            "hant": {"title": name},
            "kind": kind,
            "level": "regional",
            "region": HONG_KONG,
            "areas": [HONG_KONG],
            "refs": [{"w": "hk-ich-inventory", "loc": loc}],
            "since": year,
        })
    write_json(os.path.join(DATA_DIR, "heritage_hongkong.json"), records)
    print("heritage entries: %d" % len(records))
    for record in records:
        print("  %s  %s" % (record["id"], record["title"]))


if __name__ == "__main__":
    main()
