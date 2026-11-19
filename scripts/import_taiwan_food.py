#!/usr/bin/env python3
"""Import Taiwan's food records: its registered place marks and its heritage listings.

Sources (downloaded into research/downloads/taiwan-food/):
  tipo-origin-marks.csv  臺灣產地標章註冊資訊, the Intellectual Property Office's list of place marks
  tipo-records.json      the office's record of each domestic mark, read from its search system:
                         the mark's name, holder, registration date and statement of origin
  boch-5.1.json          the Bureau of Cultural Heritage's register, category 民俗
  boch-5.3.json          the same register, category 傳統知識與實踐

Outputs:
  data/products/tipo-marks.json  one product per place-named product, as a protected product
  data/heritage_taiwan.json      the heritage entries chosen below

Place marks. Taiwan protects a place-named product as a trademark, a 產地證明標章 or a
產地團體商標. The list has 132 marks: 54 belong to foreign holders and are left out, one domestic
mark is not food, and 77 are food. A mark's registered name is the wording of its picture
(台灣台東鹿野鄉鹿野米 LUYE 及圖), so the product's name is set by hand in MARKS below, in words
taken from the mark's name or its statement of origin. Several products have two marks; they are
one product here, dated from the first. A product is placed at the unit of its holder, which is
a township office, a farmers' association or a county government, unless PLACES says otherwise.

Heritage. Taiwan's register has two levels. None of the entries designated nationally (重要) is
food, so the entries here are city and county listings, marked "level": "local". They were
chosen by reading the names of all 494 entries in three categories; HERITAGE lists them.

Names. The sources write Traditional Chinese. `title` and `applicant` are converted to
Simplified, like the rest of the data, and `hant` keeps the source's own wording, which the
page shows as it stands.

Usage: python3 -I scripts/import_taiwan_food.py
"""
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA_DIR, DOWNLOADS_DIR, read_json, write_json  # noqa: E402
from import_taiwan import T2S, simplified_chinese  # noqa: E402
from product_kinds import classify  # noqa: E402

SOURCE = os.path.join(DOWNLOADS_DIR, "taiwan-food")
TAIWAN = "cn:710000"

# Row number in the office's list -> the product's name. Rows that share a name are one product.
MARKS = {
    1: "池上米", 2: "池上米", 3: "西螺濁水米", 4: "三星米", 5: "關山米", 6: "玉里米", 7: "鹿野米",
    8: "富里米", 9: "長濱米", 10: "光復米", 11: "鹿野米", 12: "豐濱米", 13: "霧峰香米", 14: "竹塘米",
    15: "恆春米",
    17: "鹿谷凍頂烏龍茶", 18: "阿里山高山茶", 19: "文山包種茶", 20: "杉林溪茶", 21: "北埔膨風茶",
    22: "日月潭紅茶", 23: "合歡山高冷茶", 24: "鹿野紅烏龍茶", 25: "南投市青山茶", 26: "苗栗縣東方美人茶",
    27: "峨眉東方美人茶", 28: "梨山茶", 29: "日月潭紅茶", 30: "瑞穗天鶴茶", 31: "拉拉山高山茶",
    56: "南投梅", 57: "太麻里鄉釋迦", 58: "三灣梨", 59: "拉拉山水蜜桃", 60: "關廟鳳梨", 61: "鶴岡文旦",
    62: "麻豆文旦", 63: "玉井芒果", 64: "斗六文旦", 65: "麻豆文旦", 66: "枋山芒果", 67: "獅子芒果",
    68: "關廟鳳梨", 69: "下營文旦",
    74: "國姓咖啡", 75: "日月潭精品咖啡", 76: "東山咖啡", 77: "古坑咖啡",
    78: "澎湖優鮮水產品", 79: "金門酒糟牛", 80: "金門酒糟牛肉",
    89: "竹山甘藷", 90: "西衛手作澎湖麵線", 91: "苗栗芋頭", 92: "五峰鄉桂竹筍", 93: "水林番薯",
    94: "苗栗泰安桂竹筍", 95: "臺東南迴小米", 96: "善化胡麻", 97: "西港胡麻", 98: "官田菱角",
    99: "大甲芋頭", 100: "白河蓮子", 101: "銅鑼杭菊", 102: "公館紅棗", 103: "白河蓮藕粉", 104: "大安蔥",
    105: "公館芋頭", 106: "萬丹紅豆", 107: "下營黑豆", 108: "滿州黑豆", 109: "美濃豆", 110: "恆春洋蔥",
    111: "車城洋蔥", 112: "枋山洋蔥", 113: "恆春胡麻", 114: "美濃野蓮",
}
NOT_FOOD = {122: "北投溫泉湯花"}  # hot-spring mineral deposits

# Products placed by their statement of origin, where the holder's own unit is not the place.
PLACES = {
    "獅子芒果": [("屏東縣", "獅子鄉")],  # held by the 枋山 farmers' association; "產製於屏東縣獅子鄉之芒果"
    "臺東南迴小米": [("臺東縣", "太麻里鄉"), ("臺東縣", "金峰鄉"), ("臺東縣", "大武鄉"), ("臺東縣", "達仁鄉")],
    "西衛手作澎湖麵線": [("澎湖縣", "馬公市")],  # held by the county; made in 西衛里 of 馬公市
}

# Heritage entries chosen by name: the register's case number -> the kind of food. Entries about
# catching and harvest take the kind "farming".
HERITAGE = {
    # 傳統知識與實踐
    "20190418000001": "tea",      # 傳統手工製茶-名間埔中茶
    "20220619000001": "tea",      # 傳統手工製茶-鹿谷烏龍茶
    "20251211000002": "liquor",   # 馬祖老酒文化
    "20191220000004": "farming",     # 臺東新港鏢旗魚
    "20200723000001": "farming",     # 芳苑潮間帶牛車採蚵
    "20260302000002": "farming",     # 竹南后厝仔牽罟
    # 民俗
    "20141111000001": "cuisine",  # 馬鳴山五年千歲吃飯擔
    "20180102000001": "cuisine",  # 新化大坑尾擔飯擔
    "20090115000001": "staple",   # 永康廣興宮境內擔餅節
    "20131021000001": "meat",     # 太陽公生及九豬十六羊祭品
    "20160203000004": "cuisine",  # 忠順聖王會食祖佛酒迎陳聖祖
    "20090902000002": "cuisine",  # 竹山社寮紫南宮吃丁酒
    "20150116000002": "staple",   # 大路關四孤搶粄(高樹)
    "20111215000003": "staple",   # 中秋搏餅
    "20250716000001": "staple",   # 澎湖上元乞龜
    "20111213000001": "farming",     # 雅美(達悟)族飛魚祭
    "20121226000005": "farming",     # 卑南族婦女工團小米祭
    "20220110000001": "farming",     # 卡那卡那富族Mikongu（米貢祭）
    "20150916000001": "farming",     # 金山磺火捕魚蹦火仔
}
CATEGORY = {"5.1": "民俗", "5.3": "传统知识与实践"}


class Units:
    """Taiwan's units, found by the names the sources use."""

    def __init__(self):
        rows = [u for u in read_json(os.path.join(DATA_DIR, "divisions.json"))["units"] if u["id"].startswith("tw:")]
        self.by_id = {u["id"]: u for u in rows}
        self.counties = {u["hant"]: u for u in rows if u["depth"] == 2}
        self.towns = {(self.by_id[u["parent"]]["hant"], u["hant"]): u for u in rows if u["depth"] == 3}

    def find(self, county, town=None):
        county = county.replace("台", "臺") if county.replace("台", "臺") in self.counties else county
        if not town:
            return self.counties[county]["id"]
        return self.towns[(county, town)]["id"]

    def of_holder(self, holder):
        """The unit a mark's holder belongs to: 屏東縣枋山地區農會 gives 枋山鄉 of 屏東縣."""
        rest = re.sub(r"(公所|農會|政府)$", "", holder).replace("地區", "").replace("台", "臺")
        for county in self.counties:
            if rest.startswith(county):
                town = rest[len(county):]
                if not town:
                    return self.counties[county]["id"]
                fits = [u for (c, t), u in self.towns.items() if c == county and (t == town or t[:-1] == town)]
                if len(fits) == 1:
                    return fits[0]["id"]
        fits = [u for (c, t), u in self.towns.items() if t == rest]  # 南投市公所
        if len(fits) == 1:
            return fits[0]["id"]
        raise ValueError("cannot place the holder %s" % holder)

    def centre(self, unit_id):
        return self.by_id[unit_id]["centre"]


def year(roc_date):
    """098/02/01, a date in the Minguo calendar, gives 2009."""
    return int(roc_date.split("/")[0]) + 1911


def main():
    table = {}
    with open(T2S, encoding="utf-8") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) >= 2:
                table[parts[0]] = parts[1]

    def simp(text):
        return simplified_chinese(text, table)

    units = Units()

    # ---- place marks ----
    with open(os.path.join(SOURCE, "tipo-origin-marks.csv"), encoding="utf-8-sig") as fh:
        rows = [row for row in list(csv.reader(fh))[1:] if row and row[0].strip()]
    records = read_json(os.path.join(SOURCE, "tipo-records.json"))
    domestic = [row for row in rows if row[2].startswith("國內")]
    unlisted = [row[0] for row in domestic if int(row[0]) not in MARKS and int(row[0]) not in NOT_FOOD]
    if unlisted:
        sys.exit("domestic marks with no product name in MARKS: rows %s" % ", ".join(unlisted))

    products = {}
    for row in domestic:
        number = int(row[0])
        if number not in MARKS:
            continue
        record = records[row[0]]["record"]
        mark, holder = record["scn2"]["tmarkName"], record["scn3"][0]["nameC"]
        title = MARKS[number]
        if not all(char in mark + record["scn7"][0]["classGoodsName"] + holder for char in title):
            sys.exit("row %d: the name %s is not in the mark's words" % (number, title))
        entry = products.setdefault(title, {"marks": [], "numbers": [], "holder": holder, "years": []})
        if entry["holder"] != holder:
            sys.exit("%s has two holders" % title)
        entry["marks"].append(mark)
        entry["numbers"].append(record["scn2"]["examNo"])
        entry["years"].append(year(record["scn2"]["regDate"]))

    out = []
    for title, entry in products.items():
        if title in PLACES:
            areas, placed_by = [units.find(*place) for place in PLACES[title]], "hand"
        else:
            areas, placed_by = [units.of_holder(entry["holder"])], "holder"
        numbers = "、".join(simp(number) for number in entry["numbers"])
        out.append({
            "id": "tw-mark:" + re.sub(r"\D", "", entry["numbers"][0]),
            "title": simp(title),
            "hant": {"title": title, "applicant": entry["holder"]},
            "kind": classify(simp(title)),
            "region": TAIWAN,
            "areas": areas,
            "placed_by": placed_by,
            "applicant": simp(entry["holder"]),
            "marks": entry["marks"],
            "since": min(entry["years"]),
            "refs": [{"w": "tipo-origin-marks", "loc": numbers}],
            "coord": units.centre(areas[0]),
            "approx": True,
        })
    write_json(os.path.join(DATA_DIR, "products", "tipo-marks.json"), out)

    # ---- heritage ----
    heritage, seen = [], set()
    for category in ("5.3", "5.1"):
        for case in read_json(os.path.join(SOURCE, "boch-%s.json" % category)):
            if case["caseId"] not in HERITAGE:
                continue
            if "重要" in case["assetsClassifyName"]:
                sys.exit("%s is a national entry; this list is of local ones" % case["caseName"])
            seen.add(case["caseId"])
            title = case["caseName"].strip()
            areas = []
            for address in case["addresses"]:
                unit = units.find(address["cityName"], address.get("distName"))
                if unit not in areas:
                    areas.append(unit)
            # The year of the first listing. A few entries carry only later amendments, and
            # then the earliest of those is the best the file gives.
            listed = ([a["registerDate"] for a in case["announcementList"] if a["classification"] == "指定/登錄"]
                      or [a["registerDate"] for a in case["announcementList"]])
            item = {
                "id": "heritage:tw:" + case["caseId"],
                "title": simp(title),
                "hant": {"title": title, "listed_by": case["govInstitutionName"]},
            }
            if HERITAGE[case["caseId"]]:
                item["kind"] = HERITAGE[case["caseId"]]
            item.update({
                "level": "local",
                "listed_by": simp(case["govInstitutionName"]),
                "region": TAIWAN,
                "areas": areas,
                "refs": [{"w": "boch-register", "loc": "%s %s" % (CATEGORY[category], case["caseId"])}],
                "since": int(min(listed)[:4]),
                "coord": units.centre(areas[0]),
                "approx": True,
            })
            heritage.append(item)
    missing = set(HERITAGE) - seen
    if missing:
        sys.exit("heritage entries not found in the register files: %s" % sorted(missing))
    write_json(os.path.join(DATA_DIR, "heritage_taiwan.json"), heritage)

    print("marks: %d in the list, %d domestic, %d food, %d not food" % (len(rows), len(domestic), sum(len(e["marks"]) for e in products.values()), len(NOT_FOOD)))
    print("products: %d" % len(out))
    for record in out:
        print("  %-10s %s  %s  %d  %s" % (record["kind"], record["title"], "、".join(units.by_id[a]["name"] for a in record["areas"]), record["since"], record["placed_by"]))
    print("heritage entries: %d" % len(heritage))
    for record in heritage:
        print("  %-8s %s  %s  %d" % (record.get("kind", "-"), record["title"], "、".join(units.by_id[a]["name"] for a in record["areas"]), record["since"]))


if __name__ == "__main__":
    main()
