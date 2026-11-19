#!/usr/bin/env python3
"""Import the China Cuisine Association's 2018 "中国菜" list of regional signature dishes.

Source: research/downloads/cca-dish-list/thepaper-2437871.html, a press repost that carries the
full list: ten dishes for each of the 34 province-level units, plus themed banquets.
Output: data/dishes.json

The list is an industry association's selection, not a government register.

Usage: python3 scripts/import_dishes.py
"""
import html
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA_DIR, DOWNLOADS_DIR, province_code, region_id, write_json  # noqa: E402

HEADING = re.compile(r"【(.+?)(?:十大)?(经典名菜|主题名宴)】")


def paragraphs(raw):
    """Return the page's text paragraphs in order."""
    body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S | re.I)
    parts = re.split(r"</p>|<br\s*/?>|</div>|</h\d>", body, flags=re.I)
    out = []
    for part in parts:
        text = html.unescape(re.sub(r"<[^>]+>", "", part))
        text = re.sub(r"\s+", "", text)
        if text:
            out.append(text)
    return out


def main():
    path = os.path.join(DOWNLOADS_DIR, "cca-dish-list", "thepaper-2437871.html")
    raw = open(path, "rb").read().decode("utf-8", "replace")
    current = None  # (province code, list kind)
    dishes = {}
    order = []
    for text in paragraphs(raw):
        m = HEADING.search(text)
        if m:
            code = province_code(m.group(1))
            current = (code, m.group(2)) if code else None
            if code and m.group(2) == "经典名菜" and code not in dishes:
                dishes[code] = []
                order.append(code)
            continue
        if not current or current[1] != "经典名菜":
            continue
        if "【" in text or len(text) > 24:
            current = None
            continue
        items = dishes[current[0]]
        if text.startswith("（") and items:
            items[-1] += text  # a bracketed note that belongs to the dish above
        elif len(items) < 10 and not province_code(text) == text:
            # A bare province name between lists is a section label, not a dish.
            if any(text == name for name in ("甘肃", "北京", "上海", "广东", "天津", "重庆", "四川", "湖南", "湖北", "河南", "河北", "山东", "山西", "浙江", "江苏", "福建", "江西", "广西", "安徽", "贵州", "陕西", "宁夏", "青海", "云南", "西藏", "新疆", "内蒙古", "黑龙江", "吉林", "辽宁", "海南", "香港", "澳门", "台湾")):
                continue
            items.append(text)

    records = []
    for code in order:
        for i, title in enumerate(dishes[code], 1):
            records.append({
                "id": "dish:cca2018-%s-%d" % (code, i),
                "title": title,
                "region": region_id(code),
                "listed": 2018,
                "refs": [{"w": "cca-2018", "loc": "十大经典名菜"}],
            })
    out = write_json(os.path.join(DATA_DIR, "dishes.json"), records)
    short = [c for c in order if len(dishes[c]) != 10]
    print("units: %d | dishes: %d" % (len(order), len(records)))
    if short:
        print("  ! units without exactly ten dishes:", {c: len(dishes[c]) for c in short})
    for code in order[:2] + order[-3:]:
        print("  ", code, "、".join(dishes[code]))
    print("wrote", os.path.relpath(out))


if __name__ == "__main__":
    main()
