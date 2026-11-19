#!/usr/bin/env python3
"""Build the table of administrative units, data/divisions.json.

One row per unit at the three levels the map shows: the province-level units, the units directly
under them, and the units under those.

Sources (in research/downloads/):
  datav-geoatlas/list/all.json            every unit with its parent and seat, as of 2021
  datav-geoatlas/100000_full.json         label points of the first level
  datav-geoatlas/100000_full_city.json    label points of the second level
  datav-geoatlas/level-3/*_full.json      label points of the third level
  modood-divisions/areas.json             the statistics bureau's 2023 list, used to check codes

Taiwan's cities, counties, townships and districts are read from data/regions/taiwan-units.json,
which scripts/import_taiwan.py makes from the boundary file of Taiwan's surveying centre.

Hand-made corrections are read from data/overrides/divisions.json and are never written back.

Usage: python3 scripts/import_divisions.py
"""
import collections
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA_DIR, DOWNLOADS_DIR, PROVINCES, read_json, region_id  # noqa: E402
from divisions import TABLE_PATH, kind_of, short_name  # noqa: E402

# Words that mark a row of the statistics list as a development zone or similar, not a unit.
ZONE = re.compile(r"开发区|园区|管理区|示范区|试验区|保税|工业园|产业园|旅游|度假|风景|管委会|合作区|集聚区|基地|高新|"
                  r"经济区|物流|新城|产业|办事处|实验区|功能区|自贸|港区|口岸")


def point(pair):
    return [round(pair[0], 3), round(pair[1], 3)] if pair else None


def taiwan_units():
    """Rows for the units inside Taiwan, in the order of the file: each city or county, then its parts.

    Their ids are "tw:" plus the code the surveying centre gives them, since the national
    standard has no codes below the province. `hant` is the name as that file writes it.
    """
    path = os.path.join(DATA_DIR, "regions", "taiwan-units.json")
    if not os.path.exists(path):
        return []
    municipalities = {"63000", "64000", "65000", "66000", "67000", "68000"}
    units = []
    for row in read_json(path)["units"]:
        name, code = row["name"], row["id"].split(":")[1]
        depth = 2 if row["parent"].startswith("cn:") else 3
        if depth == 2:
            kind = "special-municipality" if code in municipalities else "county" if name.endswith("县") else "city"
        else:
            kind = {"区": "district", "乡": "township", "镇": "town", "市": "county-administered-city"}[name[-1]]
        units.append({
            "id": row["id"], "parent": row["parent"], "depth": depth, "kind": kind, "name": name,
            "short": name[:-1] if len(name) > 2 else name, "hant": row["hant"], "en": row["en"],
            "centre": row["centre"], "seat": None,
        })
    return units


def write_table(path, note, editions, units):
    """One unit per line, so a change shows up as one changed line."""
    lines = ["{", '  "note": %s,' % json.dumps(note, ensure_ascii=False),
             '  "editions": %s,' % json.dumps(editions, ensure_ascii=False), '  "units": [']
    for index, unit in enumerate(units):
        comma = "," if index < len(units) - 1 else ""
        lines.append("    " + json.dumps(unit, ensure_ascii=False, separators=(", ", ": ")) + comma)
    lines += ["  ]", "}"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main():
    src = os.path.join(DOWNLOADS_DIR, "datav-geoatlas")
    overrides = read_json(os.path.join(DATA_DIR, "overrides", "divisions.json"))
    recode = {row["from"]: row for row in overrides["recode"]}
    local = overrides["local_ids"]

    listed = {str(d["adcode"]): d for d in read_json(os.path.join(src, "list", "all.json"))
              if str(d["adcode"]).isdigit() and d["level"] != "country"}

    # Label points and the set of units that have a shape, from the boundary files themselves.
    labels, shaped = {}, set()
    paths = [os.path.join(src, "100000_full.json"), os.path.join(src, "100000_full_city.json")]
    paths += sorted(glob.glob(os.path.join(src, "level-3", "*_full.json")))
    for path in paths:
        for feature in read_json(path)["features"]:
            props = feature["properties"]
            code = str(props.get("adcode"))
            if not code.isdigit():
                continue
            if props.get("centroid") or props.get("center"):
                labels[code] = props.get("centroid") or props.get("center")
            if (feature.get("geometry") or {}).get("coordinates"):
                shaped.add(code)

    def unit_id(code):
        if code in local:
            return local[code]["id"]
        return region_id(recode[code]["to"] if code in recode else code)

    problems = []
    units = []
    province_codes = [code for code, _full, _short, _en in PROVINCES]
    for code, full, short, english in PROVINCES:
        row = listed.get(code)
        if not row or row["name"] != full:
            problems.append("province %s %s is missing from the source list or named differently" % (code, full))
            continue
        units.append({
            "id": region_id(code), "parent": None, "depth": 1, "kind": kind_of(full, 1), "name": full,
            "short": short, "en": english, "centre": point(labels.get(code)), "seat": point([row["lng"], row["lat"]]),
        })

    def make(code, depth):
        row = listed[code]
        fix = recode.get(code, {})
        name = fix.get("name", row["name"])
        new_id = unit_id(code)
        unit = {"id": new_id, "parent": unit_id(str(row["parent"])), "depth": depth}
        unit["kind"] = kind_of(name, depth, new_id.split(":")[1])
        unit["name"] = name
        unit["short"] = short_name(name, new_id)
        if code in local:
            unit["hant"] = local[code]["hant"]
            unit["en"] = local[code]["en"]
        seat = [row["lng"], row["lat"]]
        unit["centre"] = point(labels.get(code) or seat)
        unit["seat"] = point(seat)
        if new_id != region_id(code):
            unit["source_code"] = code  # the code this unit carries in the boundary files
        if fix.get("was"):
            unit["was"] = list(fix["was"])
        if code not in shaped or code in overrides.get("no_shape", {}):
            unit["shape"] = False
        if fix.get("note") or code in overrides.get("no_shape", {}):
            unit["note"] = fix.get("note") or overrides["no_shape"][code]
        return unit

    by_parent = collections.defaultdict(list)
    for code, row in listed.items():
        by_parent[str(row["parent"])].append(code)

    added = collections.defaultdict(list)
    for row in overrides.get("add", []):
        added[row["parent"]].append(row)

    for province in province_codes:
        position = next(i for i, unit in enumerate(units) if unit["id"] == region_id(province))
        block = []
        for code in sorted(by_parent.get(province, [])):
            block.append(make(code, 2))
            for child in sorted(by_parent.get(code, [])):
                block.append(make(child, 3))
                if by_parent.get(child):
                    problems.append("%s %s has units below the third level" % (child, listed[child]["name"]))
        for row in added.get(province, []):
            block.append({
                "id": region_id(row["code"]), "parent": region_id(province), "depth": 2,
                "kind": kind_of(row["name"], 2, row["code"]), "name": row["name"],
                "short": short_name(row["name"]), "centre": None, "seat": None, "shape": False, "note": row["note"],
            })
        if province == "710000":
            block += taiwan_units()
        units[position + 1:position + 1] = block

    # Everyday names from the corrections file join the former names, for matching text.
    aliases = overrides.get("aliases", {})
    for unit in units:
        extra = aliases.get(unit["id"].split(":")[1])
        if isinstance(extra, list):
            unit["was"] = unit.get("was", []) + [name for name in extra if name not in unit.get("was", [])]

    # A short name must tell a unit apart from its siblings and from its parent.
    by_id = {unit["id"]: unit for unit in units}
    siblings = collections.defaultdict(list)
    for unit in units:
        if unit["depth"] > 1:
            siblings[(unit["parent"], unit["short"])].append(unit)
    for group in siblings.values():
        if len(group) > 1:  # 伊宁市 and 伊宁县 keep their full names
            for unit in group:
                unit["short"] = unit["name"]
    for unit in units:
        parent = by_id.get(unit["parent"])
        if parent and unit["short"] == parent["short"]:  # 长沙县 under 长沙市, 本溪满族自治县 under 本溪市
            unit["short"] = unit["short"] + unit["name"][-1] if "自治" in unit["name"] else unit["name"]
    # Units that the page frames with all their pieces (see "frame_all" in the corrections file).
    frame_all = {key for key in overrides.get("frame_all", {}) if key != "note"}
    for unit in units:
        if unit["id"] in frame_all:
            unit["frame"] = "all"
    for missing in sorted(frame_all - set(by_id)):
        problems.append("frame_all names %s, which is not in the table" % missing)
    # One Simplified name must not stand for two different official Traditional names.
    official = {}
    for unit in units:
        if unit.get("hant") and official.setdefault(unit["name"], unit["hant"]) != unit["hant"]:
            problems.append("%s is written both %s and %s" % (unit["name"], official[unit["name"]], unit["hant"]))

    # Checks on the table itself.
    ids = [unit["id"] for unit in units]
    if len(ids) != len(by_id):
        problems.append("duplicate ids: %s" % [i for i, n in collections.Counter(ids).items() if n > 1][:5])
    for unit in units:
        parent = by_id.get(unit["parent"]) if unit["parent"] else None
        if unit["depth"] > 1 and (parent is None or parent["depth"] != unit["depth"] - 1):
            problems.append("%s %s: parent %s is missing or at the wrong depth" % (unit["id"], unit["name"], unit["parent"]))
    placed = {unit.get("source_code") or unit["id"].split(":")[1] for unit in units}
    left_out = sorted(set(listed) - placed)
    if left_out:
        problems.append("in the source list but not in the table: %s" % left_out[:10])

    # Compare with the 2023 statistics list. Anything not explained in the overrides is reported.
    areas = {row["code"]: row["name"] for row in read_json(os.path.join(DOWNLOADS_DIR, "modood-divisions", "areas.json"))}
    explained_list = overrides.get("explained_2023", {})
    explained_table = overrides.get("explained_table", {})
    warnings = []
    table_codes = {}
    for unit in units:
        prefix, code = unit["id"].split(":")
        if prefix == "cn" and unit["depth"] > 1 and not code.endswith("00"):
            table_codes[code] = unit["name"]
    for code, name in sorted(table_codes.items()):
        if code not in areas:
            if code not in explained_table:
                warnings.append("in the table but not in the 2023 list: %s %s" % (code, name))
        elif areas[code] != name:
            warnings.append("named differently in the 2023 list: %s %s, there %s" % (code, name, areas[code]))
    zones = 0
    for code, name in sorted(areas.items()):
        if code in table_codes or code in explained_list:
            continue
        if 71 <= int(code[4:]) <= 80 or ZONE.search(name):
            zones += 1
        else:
            warnings.append("in the 2023 list but not in the table: %s %s" % (code, name))

    if problems:
        for problem in problems:
            print("  ! " + problem)
        sys.exit("divisions table not written: %d problem(s)" % len(problems))

    note = ("Generated by scripts/import_divisions.py. Do not edit by hand: put corrections in "
            "data/overrides/divisions.json and run the script again.")
    editions = {
        "units": "DataV GeoAtlas list and boundary files, dated June 2021",
        "codes": "Brought up to the statistics bureau's 2023 list where the two differ",
        "taiwan": "Units inside Taiwan from the township boundary file of Taiwan's National Land Surveying and Mapping Center, version of March 2023",
    }
    write_table(TABLE_PATH, note, editions, units)

    depths = collections.Counter(unit["depth"] for unit in units)
    kinds = collections.Counter(unit["kind"] for unit in units if unit["depth"] > 1)
    print("divisions: %d first-level, %d second-level, %d third-level units" % (depths[1], depths[2], depths[3]))
    print("kinds below the first level: " + ", ".join("%s %d" % item for item in kinds.most_common()))
    print("codes updated from the 2023 list: %d | units added: %d | without a shape: %d | local ids: %d" % (
        len(recode), len(overrides.get("add", [])), sum(1 for unit in units if unit.get("shape") is False), len(local)))
    print("development zones in the 2023 list, left out: %d" % zones)
    for warning in warnings:
        print("  ? " + warning)
    if not warnings:
        print("every difference from the 2023 list is accounted for")
    print("wrote %s (%d KB)" % (os.path.relpath(TABLE_PATH, os.path.dirname(DATA_DIR)), os.path.getsize(TABLE_PATH) // 1024))


if __name__ == "__main__":
    main()
