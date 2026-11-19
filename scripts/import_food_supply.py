#!/usr/bin/env python3
"""Import food supply per person for the mainland, Hong Kong, Macau and Taiwan.

Sources:
  research/downloads/fao-fbs/FoodBalanceSheets_E_Asia.csv
      FAO's Food Balance Sheets, the file for Asia, from https://www.fao.org/faostat/en/#data/FBS
      (released October 2025, years 2010 to 2023). The element taken is 645, "Food supply
      quantity (kg/capita/yr)", for four areas: China, mainland (41), China, Hong Kong SAR (96),
      China, Macao SAR (128) and China, Taiwan Province of (214).
  research/downloads/taiwan-food/BB_B01_114.ods
      糧食平衡表, table 1 of Taiwan's Ministry of Agriculture yearly report 糧食供需年報, the
      edition of 114 (2025), from https://agrstat.moa.gov.tw/moasdweb/book/Book.aspx. One sheet
      per year, 2016 to 2025; the last is read. The column taken is 每人純糧食供給量 每年, in
      kilograms. (The open-data file moa-food-balance.csv in the same folder stops at 2015 and
      is no longer read.)

Outputs:
  data/supply.json         the four areas side by side, latest year of the FAO file
  data/supply_taiwan.json  Taiwan's own sheet, latest year of the report

A food balance sheet measures supply: production plus imports, less exports, feed, seed,
processing and losses, divided by the population. It is not what households say they bought,
which is what the mainland's yearbook table measures, so the two are never set side by side.

Usage: python3 -I scripts/import_food_supply.py
"""
import csv
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA_DIR, DOWNLOADS_DIR, write_json  # noqa: E402

FAO = os.path.join(DOWNLOADS_DIR, "fao-fbs", "FoodBalanceSheets_E_Asia.csv")
MOA = os.path.join(DOWNLOADS_DIR, "taiwan-food", "BB_B01_114.ods")
ELEMENT = "645"

# FAO area code -> the key used in the data. The mainland has no region id of its own.
AREAS = {"41": "mainland", "96": "cn:810000", "128": "cn:820000", "214": "cn:710000"}

# (key, FAO item code, Chinese, English, the group it is part of)
FAO_COLUMNS = [
    ("cereals", "2905", "谷物", "Cereals", None),
    ("rice", "2807", "稻米", "Rice", "cereals"),
    ("wheat", "2511", "小麦", "Wheat", "cereals"),
    ("roots", "2907", "薯类", "Starchy roots", None),
    ("veg_oil", "2914", "植物油", "Vegetable oils", None),
    ("vegetables", "2918", "蔬菜", "Vegetables", None),
    ("fruit", "2919", "水果", "Fruit", None),
    ("meat", "2943", "肉类", "Meat", None),
    ("pork", "2733", "猪肉", "Pork", "meat"),
    ("beef", "2731", "牛肉", "Beef", "meat"),
    ("mutton", "2732", "羊肉", "Mutton and goat", "meat"),
    ("poultry", "2734", "禽肉", "Poultry", "meat"),
    ("aquatic", "2960", "水产品", "Fish and seafood", None),
    ("eggs", "2949", "蛋类", "Eggs", None),
    ("dairy", "2948", "奶类", "Milk", None),
    ("sugar", "2909", "糖及甜味剂", "Sugar and sweeteners", None),
]

# (key, the sheet's own name, Chinese, English, the group it is part of). A name after a slash is
# a row under that group.
MOA_COLUMNS = [
    ("cereals", "穀類", "谷类", "Cereals", None),
    ("rice", "穀類/米", "米", "Rice", "cereals"),
    ("wheat", "穀類/小麥", "小麦", "Wheat", "cereals"),
    ("roots", "薯類", "薯类", "Starchy roots", None),
    ("sugar", "糖及蜂蜜", "糖及蜂蜜", "Sugar and honey", None),
    ("oilseeds", "子仁及油籽類", "子仁及油籽类", "Pulses, nuts and oilseeds", None),
    ("vegetables", "蔬菜類", "蔬菜类", "Vegetables", None),
    ("fruit", "果品類", "果品类", "Fruit", None),
    ("meat", "肉類", "肉类", "Meat", None),
    ("pork", "肉類/豬肉", "猪肉", "Pork", "meat"),
    ("beef", "肉類/牛肉", "牛肉", "Beef", "meat"),
    ("mutton", "肉類/羊肉", "羊肉", "Mutton and goat", "meat"),
    ("poultry", "肉類/家禽肉", "家禽肉", "Poultry", "meat"),
    ("eggs", "蛋類", "蛋类", "Eggs", None),
    ("aquatic", "水產類", "水产类", "Fish and seafood", None),
    ("dairy", "乳品類", "乳品类", "Dairy", None),
    ("oil", "油脂類", "油脂类", "Oils and fats", None),
    ("veg_oil", "油脂類/植物油脂", "植物油脂", "Vegetable oils", "oil"),
]

TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
PARAGRAPH = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}p"


def columns(spec):
    out = []
    for key, _, zh, en, part_of in spec:
        column = {"key": key, "zh": zh, "en": en}
        if part_of:
            column["partOf"] = part_of
        out.append(column)
    return out


def fao():
    with open(FAO, encoding="latin-1", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r["Element Code"] == ELEMENT and r["Area Code"] in AREAS]
    years = sorted(int(name[1:]) for name in rows[0] if name[1:].isdigit() and name.startswith("Y"))
    year = years[-1]
    # An item code can appear twice with two names (2948 and 2848 are both milk); codes are unique.
    found = {(r["Area Code"], r["Item Code"]): r["Y%d" % year] for r in rows}
    areas = {}
    for code, key in AREAS.items():
        values = []
        for _, item, zh, _, _ in FAO_COLUMNS:
            text = found.get((code, item), "")
            if text == "":
                sys.exit("FAO file: no %d figure for %s in area %s" % (year, zh, code))
            values.append(round(float(text), 1))
        areas[key] = values
    return {
        "year": year,
        "unit": "kg per person per year",
        "refs": [{"w": "fao-fbs", "loc": "Food supply quantity (kg/capita/yr), %d" % year}],
        "columns": columns(FAO_COLUMNS),
        "areas": areas,
    }


def sheet_rows(sheet):
    """The rows of one sheet of an .ods file, each a list of cell texts without spaces."""
    rows = []
    for row in sheet.iter(TABLE + "table-row"):
        cells = []
        for cell in row:
            if not cell.tag.endswith("table-cell"):
                continue
            text = "".join("".join(p.itertext()) for p in cell.iter(PARAGRAPH))
            text = text.replace("\u3000", "").strip()
            cells += [text] * min(int(cell.get(TABLE + "number-columns-repeated", "1")), 40)
        rows.append(cells)
    return rows


def moa():
    with zipfile.ZipFile(MOA) as archive:
        root = ET.fromstring(archive.read("content.xml"))
    rows = sheet_rows(list(root.iter(TABLE + "table"))[-1])
    title = next(cell for row in rows for cell in row if re.search(r"民國\d+年糧食平衡表", cell))
    year = int(re.search(r"民國(\d+)年", title).group(1)) + 1911
    # The sheet is two pages side by side; the second repeats the row names before its figures.
    header = next(row for row in rows if "每年" in row)
    per_year = header.index("每年")
    names = per_year - 3
    figures, group = {}, None
    for row in rows:
        if len(row) <= per_year:
            continue
        main = re.match(r"\d+\.(.+)", row[names])
        if main:
            group = main.group(1)
            figures[group] = row[per_year]
        elif group and row[names + 1].startswith("(") and row[names + 2]:
            figures[group + "/" + row[names + 2]] = row[per_year]
    values = []
    for _, name, _, _, _ in MOA_COLUMNS:
        if name not in figures:
            sys.exit("Taiwan's sheet: no row %s for %d" % (name, year))
        values.append(round(float(figures[name].replace(",", "")), 1))
    return {
        "year": year,
        "unit": "kg per person per year",
        "refs": [{"w": "moa-food-balance", "loc": "表1，民国%d年" % (year - 1911)}],
        "columns": columns(MOA_COLUMNS),
        "areas": {"cn:710000": values},
    }


def main():
    supply, taiwan = fao(), moa()
    write_json(os.path.join(DATA_DIR, "supply.json"), supply)
    write_json(os.path.join(DATA_DIR, "supply_taiwan.json"), taiwan)
    print("FAO, %d" % supply["year"])
    print("  %-22s" % "" + "".join("%10s" % key[-8:] for key in supply["areas"]))
    for i, column in enumerate(supply["columns"]):
        print("  %-22s" % column["en"] + "".join("%10.1f" % supply["areas"][key][i] for key in supply["areas"]))
    print("Taiwan's sheet, %d" % taiwan["year"])
    for i, column in enumerate(taiwan["columns"]):
        print("  %-26s%8.1f" % (column["en"], taiwan["areas"]["cn:710000"][i]))


if __name__ == "__main__":
    main()
