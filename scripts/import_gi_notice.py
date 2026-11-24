#!/usr/bin/env python3
"""Import a geographical indication product list published with a CNIPA recognition notice.

Source: research/downloads/cnipa-gi-notices/notice-<n>/notice-<n>-product-list.pdf
Output: data/products/notice-<n>.json

The lists are tagged PDFs made in Word, so `pdfinfo -struct-text` (poppler) prints the table
row by row and cell by cell. That is exact, unlike plain text extraction, which mixes columns.
It is also slow: the 686-page list takes about 20 minutes. The rows are therefore kept in
rows.json beside the PDF, and later runs read that file. Use --reread to read the PDF again.

Notices from 2021 to 2024 have no list at all; their products are read from the running text of
their "保护要求" sections. See FROM_REQUIREMENTS.

Two notices of 2025 have no list of their own. Their pages name the products and point back to
the preliminary notice that published the details, so those are read from the preliminary
notice's file, and only the products the recognition notice names are kept. See FROM_PRELIMINARY.

Each product gets:
  areas  the units its production area names, as specific as the text allows
  kind   the kind of food, from its name (see product_kinds.py)
  coord  the middle of its stated coordinate range when that lies in one of its units, moved just
         inside them when it lies a little outside, and otherwise, or when no range is stated, the
         centre of its areas

Usage:
  python3 scripts/import_gi_notice.py 625
  python3 scripts/import_gi_notice.py 687 --reread
  python3 scripts/import_gi_notice.py 599
"""
import argparse
import collections
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA_DIR, DOWNLOADS_DIR, province_code, region_id, write_json  # noqa: E402
from divisions import Divisions  # noqa: E402
from towns import Towns  # noqa: E402
from product_kinds import classify, load_overrides  # noqa: E402
from shapes import Shapes  # noqa: E402

COLUMNS = ["seq", "name", "province", "applicant", "area", "remark"]
# Rough extent used to reject coordinates that were misread.
LON_RANGE = (73.0, 136.0)
LAT_RANGE = (3.0, 54.0)
# A stated coordinate further than this from every unit the product is placed in is not trusted.
MAX_OFFSET = 3.0  # degrees


# Recognition notices whose details sit in a preliminary notice: the file to read, how to cite
# a row, and the products the recognition notice names (its page is the work's url). A product
# in the preliminary list that is not named there was not recognised and is left out.
FROM_PRELIMINARY = {
    "619": {
        "file": "notice-611-preliminary.pdf",
        "loc": "第611号公告 序号%s",
        "names": "行唐大枣、安达奶酪、益阳松花皮蛋",
    },
    "637": {
        "file": "notice-626-preliminary-product-list.pdf",
        "loc": "第626号公告 附件1 序号%s",
        "names": "陵川连翘、怀仁绿豆、舟山带鱼、夹沟香稻米、雷官板鸭、霍山断血流、会昌酱干、巨野大蒜、定陶玫瑰、武陵酒、"
                 "阳西红心鸭蛋、柳城云片糕、屯昌香鸡、白庙血橙、瓮安黄粑、水城脆桃、镇远陈年道菜、印江苕粉、盘州头花蓼、"
                 "水城黄精、永德诃子、巧家小碗红糖、禄劝板栗、江川大头鱼、伽师新梅",
    },
}


# Notices from before the lists began (2021 to 2024). They have no table of products. Each product
# has a "保护要求" section in running text, whose first three headings give its name, the applicant
# and the production area. The sections are in the notice itself, in one file per product, or, for
# the 2024 notices, in the preliminary notice the recognition notice points back to.
#   files  {file name: number of its first section}, the numbers being the attachment numbers
#   loc    how to cite a section
#   names  the products the notice itself names, in order; the sections read must match exactly
#   rows   a notice whose text is on its page and not in a file: the three facts, typed in from it
def _requirements(year, names, files=None, loc="附件%s", rows=None):
    return {"year": year, "names": names.split("、"), "files": files, "loc": loc, "rows": rows}


FROM_REQUIREMENTS = {
    "414": _requirements(2021, "贯头山酒、赫章红花山茶油", {"notice-414.pdf": 1}),
    "424": _requirements(2021, "桐城水芹、伦教糕、马关草果", {"notice-424.pdf": 1}),
    "444": _requirements(2021, "潮州手拉朱泥壶、陆川铁锅、老厂竹根水、普洱咖啡", {"notice-444.pdf": 1}),
    "452": _requirements(2021, "阜平大枣、怀仁陶瓷、鹤岗白酒、顺德红米酒、且末红枣", {"notice-452.pdf": 1}),
    "459": _requirements(2021, "望江风酿酱油、乳山牡蛎、比德大米", {"notice-459.pdf": 1}),
    "473": _requirements(2022, "滦南虾酱、滦南虾油、祥云红梨", {"notice-473.pdf": 1}),
    "494": _requirements(2022, "亳菊、即墨黄酒", {"notice-494.pdf": 1}),
    "512": _requirements(2023, "紫云春茶、故城龙凤贡面", {"notice-512.pdf": 1}),
    "535": _requirements(2023, "合阳远志", loc="附件", rows=[
        ("合阳远志", "陕西省渭南市合阳县人民政府",
         "陕西省渭南市合阳县城关街道、和家庄镇、新池镇、坊镇、王村镇、路井镇共6个镇、街道现辖行政区域")]),
    "539": _requirements(2023, "黄骅梭子蟹、柞水（黑）木耳", {"notice-539.pdf": 1}),
    "546": _requirements(2023, "歙县珠兰花茶、常德茶油", {"notice-546.pdf": 1}),
    "555": _requirements(2023, "如皋火腿", {"notice-555.pdf": 1}),
    "557": _requirements(2023, "洪江雪峰乌骨鸡、北镇葡萄、镇坪黄连", {
        "notice-557-requirements-1.pdf": 1, "notice-557-requirements-2.pdf": 2, "notice-557-requirements-3.pdf": 3}),
    # Attachment 1 is 长白石, a stone, and was not downloaded.
    "566": _requirements(2024, "东莞腊肠", {"notice-566-requirements-2.pdf": 2}),
    "588": _requirements(2024, "介休绵芪、龙江小米、大圩葡萄、颍上大米、黟山石墨茶（黟县石墨茶）、金溪蜜梨、安化小籽花生、中江柚、横山大明绿豆",
                         {"notice-577-preliminary.pdf": 1}, "第577号公告 附件%s"),
    "589": _requirements(2024, "阜城鸭梨、阿尔山矿泉水", {"notice-574-preliminary.pdf": 1}, "第574号公告 附件%s"),
    "598": _requirements(2024, "天等指天椒酱、宝鸡柴胡", {"notice-592-preliminary.pdf": 1}, "第592号公告 附件%s"),
    "599": _requirements(2024, "迁西栗蘑、张北马铃薯、砀山黄桃、黟县香榧、和县辣椒、王庄花生、阳信鸭梨、莒南花生、金湾黄立鱼、德庆巴戟、平南石硖龙眼、北海沙虫、石棉枇杷",
                         {"notice-591-preliminary.pdf": 1}, "第591号公告 附件%s"),
    "600": _requirements(2024, "金寨天麻、龙川山茶油、苍梧迟熟荔枝", {"notice-580-preliminary.pdf": 1}, "第580号公告 附件%s"),
    "601": _requirements(2024, "南阳艾、彭州蒜薹、沙雅小刀", {"notice-586-preliminary.pdf": 1}, "第586号公告 附件%s"),
}


# The year of a notice read the ordinary way, from its product list, when it is not 2025. The
# notices in the two tables above carry their own year, or are of 2025.
YEARS = {"663": 2026, "677": 2026, "687": 2026}

SECTION = re.compile(r"一、(?:地理标志)?产品名称(.*?)二、申请(?:机构|人|单位)(.*?)三、(?:产地范围|保护范围)(.*?)四、")


def requirement_rows(notice, folder):
    """Rows for a notice in FROM_REQUIREMENTS, in the shape the table reader gives."""
    source = FROM_REQUIREMENTS[notice]
    found = []
    if source["rows"]:
        found = [("", name, applicant, area) for name, applicant, area in source["rows"]]
    for name, first in (source["files"] or {}).items():
        text = subprocess.run(["pdftotext", os.path.join(folder, name), "-"], capture_output=True, text=True, check=True).stdout
        text = clean(re.sub(r"\n\s*—\s*\d+\s*—\s*\n", "\n", text))  # page numbers fall inside sentences
        for index, match in enumerate(SECTION.finditer(text)):
            found.append((str(first + index),) + tuple(part.strip("。：:") for part in match.groups()))
    if [row[1] for row in found] != source["names"]:
        sys.exit("notice %s names %s, but the sections read are %s" % (
            notice, "、".join(source["names"]), "、".join(row[1] for row in found)))
    return [{"seq": seq, "name": name, "province": area, "applicant": applicant, "area": area, "remark": ""}
            for seq, name, applicant, area in found]


# Products placed by hand, by name: the units, and why the text alone does not give them. A third
# item, {"dot": unit}, moves the dot from the stated position toward a unit inside those units,
# where the product is named after it but covers more (庐山云雾茶, in all of 九江市).
PLACES = {
    "安县魔芋": (["cn:510705"], "安县 became 安州区 of 绵阳市 in 2016; the list still uses the old name."),
    "塔里木垦区马鹿胶": (["cn:652800"], "The regiments of the Second Division named in the text (二十一团 to 三十六团) lie in "
                                   "巴音郭楞蒙古自治州; the text and the applicant name no unit. From general knowledge."),
    "塔里木垦区马鹿花盘": (["cn:652800"], "As 塔里木垦区马鹿胶."),
    "长林岛龙垦杏": (["cn:230523"], "五九七农场 is in 宝清县, whose government is the applicant. The text names no unit, "
                               "and the stated range is wide enough to reach into 佳木斯市."),
    "同心滩羊肉": (["cn:640324"], "The text names its neighbours (盐池县, 原州区, 海原县, 中卫县) only to say where 同心县 "
                              "lies; the area is 同心县."),
    "沐川猕猴桃": (["cn:511129"], "The text names the counties 沐川县 borders (宜宾县, 屏山县, 沙湾区, 马边县) only to "
                              "bound its nine townships, which are all in 沐川县."),
    "莱芜黑山羊": (["cn:370116", "cn:370117", "cn:370114", "cn:370911", "cn:370982", "cn:370304"],
                "Eight towns of the former 莱芜市, now in 莱芜区 and 钢城区 (辛庄 and 里辛), and neighbouring towns of "
                "岱岳, 新泰, 博山 and 章丘, which the text names by their stems only (\"岱岳和新泰\")."),
    "宜昌白山羊": (["cn:420506", "cn:420528", "cn:420529", "cn:420581", "cn:420527", "cn:420526"],
                "The text lists six places of 宜昌市 by their stems only: 夷陵（原宜昌县）、长阳、五峰、宜都、秭归、兴山."),
    "三明翠碧一号烤烟": (["cn:350400"], "The text lists all of 三明市's places (梅列 is now part of 三元区); \"蒋乐\" is a "
                                   "slip for 将乐."),
    "泰山红茶": (["cn:370902", "cn:370911", "cn:370983", "cn:370921", "cn:370982"],
             "\"泰山市所辖泰山区、高新区、岱岳区、肥城、宁阳、新泰\": 泰山市 is a slip for 泰安市, and 高新区 is not a unit."),
    "剑门关土鸡": (["cn:510800"], "The text lists all seven places of 广元市, two by former names: 市中区 (now 利州区) and "
                              "元坝 (now 昭化区)."),
    "庐山云雾茶": (["cn:360400"], "庐山, the part of 鄱阳湖 under 九江 and 庐山西海, with 185 towns of 九江市's 227 (the three "
                              "named are examples); the applicant is 九江市人民政府 and the stated range covers the city. "
                              "The dot is moved toward 庐山市, as the tea is named after 庐山.", {"dot": "cn:360483"}),
    "湘潭矮脚白": (["cn:430302", "cn:430304", "cn:430321", "cn:430382"],
                "Its towns are in 雨湖区 (鹤岭, 姜畲), 湘潭县 (易俗河, 射埠, 杨家桥, now written 杨嘉桥), 韶山市 (银田, 韶山) and "
                "岳塘区 (荷塘乡, now 荷塘街道, which the 2023 town list has under its new name); 响水乡 is in the 九华 zone."),
}


def struct_rows(pdf_path):
    """Yield table body rows as lists of cell strings."""
    out = subprocess.run(["pdfinfo", "-struct-text", pdf_path], capture_output=True, text=True, check=True).stdout
    row = None
    cell = None
    for line in out.split("\n"):
        tag = line.strip()
        if tag == "TR":
            if row is not None:
                yield ["".join(c) for c in row]
            row, cell = [], None
        elif tag in ("TH", "TD"):
            if row is not None:
                cell = []
                row.append(cell)
        elif tag.startswith('"') and tag.endswith('"') and cell is not None:
            cell.append(tag[1:-1])
        elif tag.startswith("Table"):
            if row is not None:
                yield ["".join(c) for c in row]
            row, cell = None, None
    if row is not None:
        yield ["".join(c) for c in row]


def clean(text):
    return re.sub(r"\s+", "", text or "")


def merge_rows(rows):
    """Drop header rows and join rows that were split across a page break."""
    merged = []
    for cells in rows:
        cells = [clean(c) for c in cells]
        if not cells or cells[0] == "序号":
            continue
        if cells[0].isdigit():
            merged.append(cells)
        elif merged:
            last = merged[-1]
            # Where a long area text runs over a page break, the PDF's table structure files the
            # rest of it under the last column, the remark. It is the area's if nothing else is
            # in the row and the product has no remark of its own yet.
            area, remark = COLUMNS.index("area"), COLUMNS.index("remark")
            spilled = (len(cells) == len(COLUMNS) and cells[remark] and not any(cells[:remark])
                       and len(last) > area and not "".join(last[remark:]))
            if spilled:
                last[area] += cells[remark]
                continue
            for i, c in enumerate(cells):
                if i < len(last):
                    last[i] += c
                else:
                    last.append(c)
    return merged


def load_rows(notice, reread=False):
    """The table rows of a notice, from rows.json if present, else from the PDF."""
    folder = os.path.join(DOWNLOADS_DIR, "cnipa-gi-notices", "notice-%s" % notice)
    cache = os.path.join(folder, "rows.json")
    if os.path.exists(cache) and not reread:
        with open(cache, encoding="utf-8") as fh:
            return json.load(fh)["rows"]
    if notice in FROM_REQUIREMENTS:
        rows = requirement_rows(notice, folder)
        if FROM_REQUIREMENTS[notice]["files"]:
            note = "Sections read from %s by scripts/import_gi_notice.py." % ", ".join(FROM_REQUIREMENTS[notice]["files"])
            os.makedirs(folder, exist_ok=True)
            with open(cache, "w", encoding="utf-8") as fh:
                json.dump({"note": note, "rows": rows}, fh, ensure_ascii=False, indent=1)
        return rows
    preliminary = FROM_PRELIMINARY.get(notice)
    name = preliminary["file"] if preliminary else "notice-%s-product-list.pdf" % notice
    rows = []
    for cells in merge_rows(struct_rows(os.path.join(folder, name))):
        cells = cells + [""] * (len(COLUMNS) - len(cells))
        row = dict(zip(COLUMNS, cells))
        if preliminary:
            row["remark"] = ""  # the sixth column there is the local government's document, not a remark
        rows.append(row)
    if preliminary:
        wanted = preliminary["names"].split("、")
        found = [row["name"] for row in rows]
        missing = [n for n in wanted if n not in found]
        if missing:
            sys.exit("not in %s: %s" % (name, "、".join(missing)))
        for row in rows:
            if row["name"] not in wanted:
                print("left out, in the preliminary notice but not recognised by notice %s: %s" % (notice, row["name"]))
        rows = [row for row in rows if row["name"] in wanted]
    note = "Table rows read from %s by scripts/import_gi_notice.py. Kept so the slow PDF read is not repeated." % name
    with open(cache, "w", encoding="utf-8") as fh:
        json.dump({"note": note, "rows": rows}, fh, ensure_ascii=False, indent=1)
    return rows


ANGLE = re.compile(r"(\d{1,3}(?:\.\d+)?)°(?:(\d{1,2}(?:\.\d+)?)[′'’]?)?(?:(\d{1,2}(?:\.\d+)?)[″\"”]?)?")


def angles(segment):
    values = []
    for deg, minute, second in ANGLE.findall(segment):
        values.append(float(deg) + float(minute or 0) / 60 + float(second or 0) / 3600)
    return values


def coordinate_range(area):
    """Return (west, south, east, north) from a '东经…北纬…' statement, or None."""
    m = re.search(r"东经(.{3,60}?)北纬(.{3,60}?)(?:。|；|$)", area)
    if not m:
        return None
    if re.search(r"以[东西南北]", m.group(1) + m.group(2)):
        return None  # "东经125°以西" is a limit on one side, not a range with a middle
    lons, lats = angles(m.group(1)), angles(m.group(2))
    if not lons or not lats:
        return None
    west, east, south, north = min(lons), max(lons), min(lats), max(lats)
    if not (LON_RANGE[0] <= west <= east <= LON_RANGE[1] and LAT_RANGE[0] <= south <= north <= LAT_RANGE[1]):
        return None
    if east - west > 12 or north - south > 12:
        return None
    return (round(west, 4), round(south, 4), round(east, 4), round(north, 4))


def whole_parents(divisions, areas):
    """Where every unit of a parent is named, name the parent instead: all of 黄山市's seven units is 黄山市."""
    areas = list(areas)
    changed = True
    while changed:
        changed = False
        for parent in {divisions.get(a)["parent"] for a in areas}:
            children = divisions.children.get(parent, [])
            if parent and divisions.get(parent)["depth"] >= 2 and len(children) > 1 and all(c in areas for c in children):
                position = min(areas.index(c) for c in children)
                areas = [a for a in areas if a not in children]
                areas.insert(position, parent)
                changed = True
    return areas


# Words that make a clause a description of the area's border, naming neighbours only to say where
# the area ends: 东与通山县接壤, 与宜宾县交界, 西连海原县, 南接长汀.
BORDER = re.compile(r"接壤|毗邻|毗连|相邻|为邻|相望|交界|临界|相接|相连|接邻|邻接|接界|搭界|"
                    r"^其?(东南|东北|西南|西北|东|南|西|北)(邻|接|靠|连|临|毗|交|界|至|到)")
# A direction and the neighbours after it, to the end of the clause: 东邻仙居县、永嘉县; 南接晋江市、
# 西界南安市. Not 东至县, which is a county.
DIRECTION = re.compile(r"(东南|东北|西南|西北|东|南|西|北)面?(邻|接|靠|连|临|毗|交|界|至|到)(?!县)[^，,。；;]*")
# A distance is not a place: 距武汉市120公里.
DISTANCE = re.compile(r"距[^，,。；;、]*?(公里|千米|km|米)")
# What may stand between a city's name and a list of its counties: 宜春市所辖袁州区、万载….
AFTER_CITY = re.compile(r"(现辖行政区域内的?|行政区域内的?|所辖的?|下辖的?|辖区内的?|市辖|辖区|辖|境内的?|的)?")
# Where an item of such a list stops being a place's name: 平遥境内, 历城南部, 瑞安2个县级市, 兴山等.
ITEM_END = re.compile(r"(\d|等|共|全境|境内|全部|[东南西北中]部|一带|地区|行政区域).*$")
# Words that may open an item of such a list: 主要涵盖夷陵, 包括德清.
ITEM_START = re.compile(r"^(主要涵盖|主要包括|主要分布于|主要分布在|主要涉及|涵盖|包括|涉及|分布于|分布在|其中|所辖|下辖|市辖|辖)")
UNIT_KIND = re.compile(r"(自治县|自治旗|县|市|区|旗)$")


def text_places(divisions, towns, text, region):
    """The units an area text names, read with four guards on top of divisions.locate.

    1. Clauses that describe the border are left out, since the units they name are neighbours
       (崇阳野桂花蜜: 东与通山县接壤…西与通城县临界). If that leaves nothing, the whole text is read.
    2. A city's counties listed by their stems right after the city's name are taken
       (宜春市所辖袁州区、万载、奉新…; 济南市历城南部; 南通市启东汇龙), unless a stem is the
       name of a town of a county the text already names.
    3. Towns are used only when the text names no county of its own, and not when they are a few
       examples of many (海会镇、岷山乡、赛阳镇等185个乡镇): then the counties whose towns
       it names in full place it (双井西瓜: 掇刀石街办 is in 掇刀区; 崇阳野桂花蜜: 金塘镇 is in
       崇阳县). A text that names its counties keeps them, so 达州脆李 is not shrunk to the one
       county whose towns happen to carry 镇.
    4. Towns count only by their full names, not inside a longer town's name, and only towns,
       townships, subdistricts and sumu (see scripts/towns.py), so 水产养殖场 inside
       南北港水产养殖场 is not a place.
    """
    text = DISTANCE.sub("", re.sub(r"\s+", "", text or ""))
    text = DIRECTION.sub("", text)
    kept = []
    for clause in re.split(r"(?<=[，,。；;])", text):
        if BORDER.search(clause.lstrip("，,。；;")):
            # Keep what comes before the neighbour: 同心县东北与盐池县相接 keeps 同心县.
            before = re.match(r"(.*?)(东南|东北|西南|西北|东|南|西|北)?与", clause)
            clause = before.group(1) if before else ""
        kept.append(clause)
    inner = "".join(kept)
    # If the border clauses held every name, read the whole text after all.
    used = inner if inner == text or divisions.locate(inner, region) or towns.counties_in(inner, region) else text
    found = divisions.locate(used, region)

    # 2. Counties listed by their stems after their city. A city followed by 全境 is meant whole.
    plain = re.sub(r"（[^）]*）|\([^)]*\)", "", used)
    whole = set()
    for city_id in [region] + divisions.children.get(region, []):
        city = divisions.get(city_id)
        kids = [divisions.get(k) for k in divisions.children.get(city_id, []) if divisions.get(k)["depth"] == city["depth"] + 1]
        if not kids:
            continue
        # The words each county may be listed by: its short name, its name without its kind
        # (玉树 for 玉树市), and the same for the names it had before (元坝 for 昭化区).
        own = {city["short"], UNIT_KIND.sub("", city["name"]), re.sub(r"(地区|盟|自治州|州)$", "", city["name"])}
        words, same_as_city = {}, {}
        for kid in kids:
            for name in [kid["name"]] + kid.get("was", []):
                for word in dict.fromkeys([name, UNIT_KIND.sub("", name), kid["short"] if name == kid["name"] else None]):
                    if not word or len(word) < 2:
                        continue
                    if word in own and word != kid["name"]:
                        same_as_city.setdefault(word, kid)  # 菏泽 is the city, not 牡丹区 (once 菏泽县)
                    else:
                        words.setdefault(word, kid)
        for label in dict.fromkeys([city["name"], city["short"]]):
            for match in re.finditer(re.escape(label), plain):
                rest = plain[match.end():]
                if city_id != region and re.match(r"(市域)?全境", rest):
                    whole.add(city_id)
                rest = rest[AFTER_CITY.match(rest).end():]
                rest = re.split(r"[。；;]|地理坐标", rest)[0]
                items = re.split(r"[、，,和及与]+", rest)
                if re.match(r"[、，,和及与]", rest) and label in same_as_city:
                    kid = same_as_city[label]  # 玉树、称多、囊谦…: the city's stem is also its county's
                    if kid["id"] not in found:
                        found.append(kid["id"])
                for item in items:
                    item = ITEM_END.sub("", ITEM_START.sub("", item))
                    kid = words.get(item)
                    if not kid:
                        for short in sorted((w for w in words if 2 <= len(w) < len(item)), key=len, reverse=True):
                            if item.startswith(short) and towns.is_town_stem(item[len(short):], [words[short]["id"]]):
                                kid = words[short]  # 启东汇龙: 启东 and its town 汇龙
                                break
                    elif item != kid["name"] and towns.is_town_stem(item, [f for f in found if divisions.get(f)["depth"] == 3]):
                        kid = None  # a town of a county already named (启东's town 东海 is not 东海县)
                    if kid and kid["id"] not in found:
                        found.append(kid["id"])

    # 3. Towns, when no county is named. A county counts if at least two of its towns are named
    # and they weigh at least 1 (see Towns.counties_in); if no county does, the counties with the
    # most weight. So one stray town (讷河 for 双城甜瓜), or two common names (永胜乡, 朝阳乡), does
    # not pull in a county elsewhere in the province.
    if towns.available and not any(divisions.get(f)["depth"] >= 3 for f in found):
        cities = [f for f in found if divisions.get(f)["depth"] == 2 and f not in whole]
        within = None
        if cities:
            within = set()
            for c in cities:
                within |= set(divisions.children.get(c, []))
        weights = towns.counties_in(used, region, within)
        # Towns given as examples of many (海会镇、岷山乡、赛阳镇等185个乡镇) do not decide the counties.
        # What counts is how many places the sentence before 等 names, however they are written and
        # however grouped: 灵山香鸡 names 17 of its 18 by their stems, 开县锦橙 all 15 in three groups
        # separated by commas, 哈尔腾哈萨克羊 its 3 towns and then their villages.
        many = re.search(r"等(\d+)个(乡镇|镇乡|乡|镇|街道|办事处)", used)
        if many:
            named = re.split(r"[。；;]", used[:many.start()])[-1]
            items = [x for x in re.split(r"[、，,和及]", named) if x]
            if int(many.group(1)) >= 3 * max(1, len(items)):
                weights = {}
        # Towns change: a city is narrowed to counties only when most of the towns the text lists
        # are on the list (锦州海蜇's towns in 凌海市 are no longer, so it stays 锦州市).
        listed = towns.listed(used)
        matched = sum(1 for t in listed if t in towns.full.get(region, {}))
        enough = not cities or not listed or matched >= len(listed) / 2
        if weights and enough:
            strong = {c for c, (n, w) in weights.items() if n >= 2 and w >= 1}
            top = max(w for _n, w in weights.values())
            counties = strong or {c for c, (_n, w) in weights.items() if w == top}
            found = [f for f in found if f not in cities or not any(divisions.get(k)["parent"] == f for k in counties)]
            found += sorted(counties)

    # A city meant whole keeps its place, without its counties.
    for city_id in whole:
        found = [f for f in found if divisions.get(f)["parent"] != city_id]
        if city_id not in found:
            found.append(city_id)

    # A city is dropped when one of its own counties is named, as in divisions.locate.
    parents = {divisions.get(f)["parent"] for f in found}
    return [f for f in found if f not in parents]


# How far outside a unit's bounding box, in degrees, the middle of a stated range may fall and
# still count as that unit's position, to be pulled back inside its border. Measured on the
# notices imported so far, the stated positions run without a break up to 0.50 degrees outside
# and start again at 0.56, so the cut sits in that gap. Beyond it the range is taken for a slip
# in the notice (a degree or a minute mistyped, or a neighbouring prefecture's figures), and the
# dot goes to the unit's centre as if no coordinates were given.
NEAR = 0.53


def within(inner, outer, slack):
    """True if the range `inner` lies inside the range `outer`, give or take `slack` degrees."""
    return bool(outer) and (inner[0] >= outer[0] - slack and inner[1] >= outer[1] - slack
                            and inner[2] <= outer[2] + slack and inner[3] <= outer[3] + slack)


def place(divisions, shapes, region, title, named, box):
    """Decide where a product belongs. Returns (unit ids, how it was decided, the range if trusted).

    In order of trust: the units its area text names; the place its name starts with (秀山金银花);
    the unit whose shape contains the middle of its stated coordinate range. When none of these
    places it, main() falls back on the unit named by the applicant.
    """
    point = [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2] if box else None
    spot = [point[0], point[1], point[0], point[1]] if point else None
    if named:
        if point:
            lower = [a for a in named if a != region]
            boxes = [shapes.bbox(a) for a in lower]
            centres = [divisions.get(a)["centre"] for a in lower if divisions.get(a).get("centre")]
            # The middle of the stated range has to fall in or beside a named unit. The lists carry
            # slips (a latitude three degrees off puts 溧阳 in the Yellow Sea), and a unit's centre is
            # a better dot than a slip. A unit with no shape is judged by its centre instead.
            known = [b for b in boxes if b]
            near = any(within(spot, b, NEAR) for b in known) if known else any(
                max(abs(point[0] - c[0]), abs(point[1] - c[1])) <= MAX_OFFSET for c in centres)
            if lower and not near:
                return named, "text", None  # the stated position is nowhere near: not trusted
            # One city named, and the stated range fits inside one of its units: use that unit.
            if len(named) == 1 and divisions.get(named[0])["depth"] == 2 and divisions.children.get(named[0]):
                child = shapes.child_at(point[0], point[1], named[0])
                if child and within(box, shapes.bbox(child), 0.08):
                    return [child], "text and position", box
        return named, "text", box

    from_title = divisions.leading_unit(title, region)
    if point:
        unit = shapes.unit_at(point[0], point[1], region)
        while unit and unit != region and not within(box, shapes.bbox(unit), 0.08):
            unit = divisions.get(unit)["parent"]  # the range is wider than this unit: go up a level
        if unit == region:
            unit = None
        if from_title and unit:
            if divisions.inside(unit, from_title):
                return [unit], "name and position", box
            if divisions.inside(from_title, unit) or within(spot, shapes.bbox(from_title), 0.15):
                return [from_title], "name and position", box
            return [unit], "position", box  # the name starts with a place that is somewhere else
        if unit:
            return [unit], "position", box
        if from_title:
            return [from_title], "name", box if within(spot, shapes.bbox(from_title), 1.0) else None
        return [region], "province", box
    if from_title:
        return [from_title], "name", None
    return [region], "province", None


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("notice", help="notice number, e.g. 625")
    parser.add_argument("--year", type=int, help="year the notice was issued, if this file does not already know it")
    parser.add_argument("--reread", action="store_true", help="read the PDF again instead of rows.json")
    args = parser.parse_args()

    rows = load_rows(args.notice, args.reread)
    divisions = Divisions()
    shapes = Shapes(divisions)
    towns = Towns(divisions)
    if not towns.available:
        print("  ? no town list (research/downloads/modood-divisions/streets.json): towns are not used")
    kind_fixes = load_overrides()

    listed = FROM_REQUIREMENTS.get(args.notice) or FROM_PRELIMINARY.get(args.notice) or {}
    loc = listed.get("loc", "附件1 序号%s")
    year = args.year or listed.get("year") or YEARS.get(args.notice, 2025)
    records, problems, distrusted = [], [], []
    for row in rows:
        code = province_code(row["province"])
        if not code:
            problems.append("row %s: province not recognised: %r" % (row["seq"], row["province"]))
            continue
        region = region_id(code)
        # The area text sometimes ends with the coordinate statement; places are named before it.
        named = whole_parents(divisions, text_places(divisions, towns, re.split(r"地理坐标|东经", row["area"])[0], region))
        if row["name"] in PLACES:
            named = list(PLACES[row["name"]][0])
        stated = coordinate_range(row["area"])
        areas, how, box = place(divisions, shapes, region, row["name"], named, stated)
        if how == "province":
            # Nothing in the area text, the name or the coordinates places it: the text uses a
            # name the unit no longer has (户县 for 鄠邑区, 苍山县 for 兰陵县) or names only towns.
            # The applicant is a local government or association, and its name says where.
            holder = whole_parents(divisions, [a for a in divisions.locate(row["applicant"], region) if a != region])
            if holder:
                areas, how = holder, "applicant"
                # A stated position is kept only if it falls in or beside that unit.
                if box:
                    middle = [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2] * 2
                    if not any(within(middle, shapes.bbox(a), NEAR) for a in holder):
                        box = None
        # A stated position is used as the dot only if it falls inside one of the product's
        # units. Being near is not enough: the middle of a stated range is often just over the
        # border (溧阳鸡 fell in 宜兴市, because its range is written 119°08′～119°63′), and a dot in
        # the neighbouring unit reads as a mistake. A position that place() trusted, which means
        # it is in or beside the unit, is pulled back inside along the line to the unit's centre,
        # so the dot still says which side of the unit the product is on.
        lower = [a for a in areas if a != region]
        pulled = None
        toward = PLACES[row["name"]][2].get("dot") if row["name"] in PLACES and len(PLACES[row["name"]]) > 2 else None
        if toward:
            lower = [toward]
        if box and lower:
            mx, my = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            if not shapes.within_units(mx, my, lower, region):
                pulled = shapes.pull_inside(mx, my, lower, region)
                if not pulled:
                    box = None
        record = {
            "id": "gi:%s-%s" % (args.notice, row["seq"] or "1"),
            "title": row["name"],
            "kind": classify(row["name"], kind_fixes),
            "region": region,
            "areas": areas,
            "placed_by": how,
            "applicant": row["applicant"],
            "area": row["area"],
            "since": year,
            "refs": [{"w": "cnipa-notice-%s" % args.notice, "loc": loc % row["seq"] if "%s" in loc else loc}],
        }
        if box:
            record["bbox"] = list(box)
            record["coord"] = pulled or [round((box[0] + box[2]) / 2, 4), round((box[1] + box[3]) / 2, 4)]
            if toward:
                record["toward"] = toward  # moved toward the place it is named after
            elif pulled:
                record["pulled"] = True  # the stated position, moved inside the unit's border
        else:
            if stated:
                # Kept in the record, so the positions that were not used can be listed.
                record["stated_not_used"] = [round((stated[0] + stated[2]) / 2, 4), round((stated[1] + stated[3]) / 2, 4)]
                distrusted.append("%s %s: stated %s, placed in %s" % (
                    record["id"], row["name"], [round((stated[0] + stated[2]) / 2, 2), round((stated[1] + stated[3]) / 2, 2)],
                    "、".join(divisions.label(a) for a in areas[:2])))
            centre = shapes.dot_for([a for a in areas if a != region], region)
            if centre:
                record["coord"] = centre
                record["approx"] = True  # a unit's centre, not a stated position
        if row["remark"]:
            record["remark"] = row["remark"]
        records.append(record)

    out = write_json(os.path.join(DATA_DIR, "products", "notice-%s.json" % args.notice), records)
    depth = collections.Counter(max(divisions.get(a)["depth"] for a in r["areas"]) for r in records)
    kinds = collections.Counter(r["kind"] for r in records)
    print("rows: %d | placed at third level: %d, second level: %d, province only: %d" % (len(rows), depth[3], depth[2], depth[1]))
    print("placed by: " + ", ".join("%s %d" % item for item in collections.Counter(r["placed_by"] for r in records).most_common()))
    print("with a stated position: %d | at a unit's centre: %d | no dot: %d" % (
        sum(1 for r in records if "bbox" in r), sum(1 for r in records if r.get("approx")), sum(1 for r in records if "coord" not in r)))
    print("kinds: " + ", ".join("%s %d" % item for item in kinds.most_common()))
    for line in distrusted:
        print("  ? stated position not used, too far from its area: " + line)
    for p in problems:
        print("  !", p)
    print("wrote", os.path.relpath(out))


if __name__ == "__main__":
    main()
