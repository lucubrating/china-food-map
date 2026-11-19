"""Shared helpers for the import and build scripts. Standard library only."""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
DOWNLOADS_DIR = os.path.join(ROOT, "research", "downloads")

# Province-level units: (division code, full name, short name, English name).
# Codes follow GB/T 2260; region ids in the data are written as "cn:<code>".
PROVINCES = [
    ("110000", "北京市", "北京", "Beijing"),
    ("120000", "天津市", "天津", "Tianjin"),
    ("130000", "河北省", "河北", "Hebei"),
    ("140000", "山西省", "山西", "Shanxi"),
    ("150000", "内蒙古自治区", "内蒙古", "Inner Mongolia"),
    ("210000", "辽宁省", "辽宁", "Liaoning"),
    ("220000", "吉林省", "吉林", "Jilin"),
    ("230000", "黑龙江省", "黑龙江", "Heilongjiang"),
    ("310000", "上海市", "上海", "Shanghai"),
    ("320000", "江苏省", "江苏", "Jiangsu"),
    ("330000", "浙江省", "浙江", "Zhejiang"),
    ("340000", "安徽省", "安徽", "Anhui"),
    ("350000", "福建省", "福建", "Fujian"),
    ("360000", "江西省", "江西", "Jiangxi"),
    ("370000", "山东省", "山东", "Shandong"),
    ("410000", "河南省", "河南", "Henan"),
    ("420000", "湖北省", "湖北", "Hubei"),
    ("430000", "湖南省", "湖南", "Hunan"),
    ("440000", "广东省", "广东", "Guangdong"),
    ("450000", "广西壮族自治区", "广西", "Guangxi"),
    ("460000", "海南省", "海南", "Hainan"),
    ("500000", "重庆市", "重庆", "Chongqing"),
    ("510000", "四川省", "四川", "Sichuan"),
    ("520000", "贵州省", "贵州", "Guizhou"),
    ("530000", "云南省", "云南", "Yunnan"),
    ("540000", "西藏自治区", "西藏", "Tibet"),
    ("610000", "陕西省", "陕西", "Shaanxi"),
    ("620000", "甘肃省", "甘肃", "Gansu"),
    ("630000", "青海省", "青海", "Qinghai"),
    ("640000", "宁夏回族自治区", "宁夏", "Ningxia"),
    ("650000", "新疆维吾尔自治区", "新疆", "Xinjiang"),
    ("710000", "台湾省", "台湾", "Taiwan"),
    ("810000", "香港特别行政区", "香港", "Hong Kong"),
    ("820000", "澳门特别行政区", "澳门", "Macau"),
]

# Names that official lists use for a province-level unit but that are not its own name.
PROVINCE_ALIASES = {"新疆生产建设兵团": "650000", "兵团": "650000"}


def province_code(text):
    """Return the division code of the province-level unit named at the start of `text`, or None."""
    text = re.sub(r"\s+", "", text or "")
    for alias, code in PROVINCE_ALIASES.items():
        if text.startswith(alias):
            return code
    for code, full, short, _en in PROVINCES:
        if text.startswith(full) or text.startswith(short):
            return code
    return None


def region_id(code):
    return "cn:%s" % code


def read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(value, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return path
