#!/usr/bin/env python3
"""Import China's nationally important agricultural heritage systems, batches 1 to 8.

Sources, all pages of the agriculture ministry's site saved in research/downloads/moa-farm-heritage/:
  batch-<n>-list.html, batch-<n>-list-2.html   batches 1 to 4 (2013 to 2017): the ministry's topic
                                               page lists each system as a link
  batch-<n>-notice.html                        batches 5 to 8: the notice names its systems in the
                                               page text, some followed by their counties in brackets
Output: data/farm_heritage.json

Each name starts with its province, so the province is read from the name. The count found for
each batch is checked against the count the ministry gives, and the import stops if they differ.

Usage: python3 scripts/import_farm_heritage.py
"""
import glob
import html
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA_DIR, DOWNLOADS_DIR, PROVINCES, province_code, region_id, write_json  # noqa: E402
from divisions import Divisions  # noqa: E402
from shapes import Shapes  # noqa: E402

SOURCE_DIR = os.path.join(DOWNLOADS_DIR, "moa-farm-heritage")
# batch: (year, how many systems the ministry gives, the work cited in data/works.json)
BATCHES = {
    1: (2013, 19, "moa-farm-heritage-1-4"),
    2: (2014, 20, "moa-farm-heritage-1-4"),
    3: (2015, 23, "moa-farm-heritage-1-4"),
    4: (2017, 29, "moa-farm-heritage-1-4"),
    5: (2020, 27, "moa-farm-heritage-5"),
    6: (2021, 21, "moa-farm-heritage-6"),
    7: (2023, 50, "moa-farm-heritage-7"),
    8: (2026, 88, "moa-farm-heritage-8"),
}
SHORTS = tuple(sorted((s for _c, _f, s, _e in PROVINCES), key=len, reverse=True))
# Slips in the ministry's own pages, put right here: {as published: as it should read}.
FIXES = {"黑龙江托远赫哲族鱼文化系统": "黑龙江抚远赫哲族鱼文化系统"}
# Places in brackets that are too short to match on their own: {as published: spelt out}.
SPELT_OUT = {"增城、东莞": "广州市增城区、东莞市", "茂名": "茂名市"}
# Where a name does not open with a place the divisions table can match: {name: its place}.
PLACES = {
    "内蒙古敖汉旱作农业系统": "赤峰市敖汉旗",
    "辽宁阜蒙旱作农业系统": "阜新市阜新蒙古族自治县",
    "内蒙古库伦荞麦旱作系统": "通辽市库伦旗",
    "福建武夷岩茶文化系统": "南平市武夷山市",
    "青海三江源曲麻莱高寒游牧系统": "玉树藏族自治州曲麻莱县",
}


def read(path):
    return open(path, "rb").read().decode("utf-8", "replace")


def from_lists(batch):
    """Names in a batch's list pages, where each system is a link to its own page."""
    names = []
    for path in sorted(glob.glob(os.path.join(SOURCE_DIR, "batch-%d-list*.html" % batch))):
        for _href, inner in re.findall(r'<a[^>]+href="(\./\d{6}/t[^"]+)"[^>]*>(.*?)</a>', read(path), flags=re.S):
            name = re.sub(r"\s+", "", html.unescape(re.sub(r"<[^>]+>", "", inner)))
            if name and name not in names:
                names.append(name)
    return [(name, None) for name in names]


def from_notice(batch):
    """(name, places in brackets or None) for each system in a batch's notice.

    The list is the last part of the page text, after the heading that repeats the notice's
    title. An entry starts on a line that opens with a province. The page sometimes breaks a
    name over several lines and puts the numbering on lines of its own, so a line that does not
    open with a province is joined to the entry before it.
    """
    raw = read(os.path.join(SOURCE_DIR, "batch-%d-notice.html" % batch))
    body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S | re.I)
    lines = [re.sub(r"\s+", "", line) for line in html.unescape(re.sub(r"<[^>]+>", "\n", body)).split("\n")]
    lines = [line for line in lines if line]
    starts = [i for i, line in enumerate(lines) if re.fullmatch(r"第.批中国重要农业文化遗产名单", line)]
    if not starts:
        sys.exit("batch %d: no list heading in the notice" % batch)
    entries = []
    for line in lines[starts[-1] + 1:]:
        if line.startswith(("附件：", "相关新闻", "扫一扫")):
            break
        line = re.sub(r"^\d+[.．、]", "", line)
        # Numbering can also sit on lines of its own, the number and the stop apart.
        if not line or re.fullmatch(r"[\d.．、]+", line) or line in ("新增项目：", "扩展项目："):
            continue
        if line.startswith(SHORTS):
            entries.append(line)
        elif entries:
            entries[-1] += line
    found = []
    for entry in entries:
        m = re.fullmatch(r"([^（(]+)(?:[（(](.*)[）)])?", entry)
        if not m:
            sys.exit("batch %d: cannot read %r" % (batch, entry))
        found.append((m.group(1), m.group(2)))
    return found


def main():
    divisions = Divisions()
    shapes = Shapes(divisions)
    records, depth, loose = [], {}, []
    for batch, (year, expected, work) in BATCHES.items():
        entries = from_lists(batch) if batch <= 4 else from_notice(batch)
        if len(entries) != expected:
            sys.exit("batch %d: found %d systems, the ministry gives %d" % (batch, len(entries), expected))
        for i, (name, places) in enumerate(entries, 1):
            name = FIXES.get(name, name)
            code = province_code(name)
            if not code:
                sys.exit("batch %d: no province at the start of %r" % (batch, name))
            region = region_id(code)
            record = {
                "id": "farm:%d-%d" % (batch, i),
                "title": name,
                "region": region,
                "batch": batch,
                "since": year,
                "refs": [{"w": work, "loc": "第%d批 第%d项" % (batch, i) if batch <= 4 else "名单 第%d项" % i}],
            }
            # The counties in brackets after the name, if any; otherwise the place the name itself
            # starts with once the province is taken off: 浙江青田稻鱼共生系统 is in 青田县.
            found = []
            if places:
                record["area"] = places
                found = divisions.locate(SPELT_OUT.get(places, places), region)
            if not found and name in PLACES:
                found = divisions.locate(PLACES[name], region)
            if not found:
                rest = name
                for _code, full, short, _en in PROVINCES:
                    if _code == code:
                        rest = name[len(full):] if name.startswith(full) else name[len(short):] if name.startswith(short) else name
                unit = divisions.leading_unit(rest, region)
                found = [unit] if unit else []
            record["areas"] = found or [region]
            centre = shapes.dot_for(found, region)
            if centre:
                record["coord"] = centre
                record["approx"] = True  # a unit's centre, not a stated position
            level = max(divisions.get(a)["depth"] for a in record["areas"])
            depth[level] = depth.get(level, 0) + 1
            if level == 1:
                loose.append(name)
            records.append(record)
    out = write_json(os.path.join(DATA_DIR, "farm_heritage.json"), records)
    print("systems: %d in %d batches (%s) | provinces: %d" % (
        len(records), len(BATCHES), ", ".join(str(n) for _y, n, _w in BATCHES.values()), len({r["region"] for r in records})))
    print("placed at third level: %d, second level: %d, province only: %d" % (depth.get(3, 0), depth.get(2, 0), depth.get(1, 0)))
    print("  province only:", "、".join(loose))
    print("wrote", os.path.relpath(out))


if __name__ == "__main__":
    main()
