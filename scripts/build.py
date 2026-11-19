#!/usr/bin/env python3
"""Compile the editable files in data/ into the bundles the page loads.

Outputs, all under js/data/:
  regions.js           window.FOODMAP_REGIONS: province boundaries as compact encoded strings
  summary.js           window.FOODMAP_DATA: sources, the eating table, and counts of records
  records/cn-*.js      one province's records each, loaded when the province is opened
  units/cn-*.js        the shapes inside one province or city each, loaded when it is opened
  dots.js              window.FOODMAP_DOTS: the position of every placed entry, for the whole map
  search.js            window.FOODMAP_SEARCH: titles and place names, loaded on the first search
  text.js              window.FOODMAP_TEXT: the words of the interface, in every language
  names/zh-hant.js     window.FOODMAP_NAMES: how to write every name above in Traditional Chinese
  names/en.js          window.FOODMAP_AS_WRITTEN: names from Traditional sources, as written there

It also checks the data (every region, place and cited work must exist) and stamps a content
hash onto each asset address in index.html, so browsers fetch a file again only when it has
changed. Generated files that are no longer produced are removed.

Usage:
  python3 scripts/build.py          # rebuild
  python3 scripts/build.py --check  # fail if the bundles are out of date
  python3 scripts/build.py --names       # list converted names that have not been read through
  python3 scripts/build.py --names-read  # record that the names listed have been read through
"""
import glob
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA_DIR, PROVINCES, ROOT, read_json, region_id, write_json  # noqa: E402
from hant import Converter  # noqa: E402

SCALE = 1000  # coordinates are stored as integers of 0.001 degree, about 100 m
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+-"
# Fields of each record that the page needs. The rest (long area texts, remarks, coordinate
# ranges, notes on how a record was placed) stay in data/ and out of what visitors download.
PAGE_FIELDS = {
    "dishes": ("id", "title", "region", "listed", "refs"),
    "heritage": ("id", "title", "own", "kind", "level", "region", "areas", "place", "body", "since", "refs", "coord", "approx"),
    "products": ("id", "title", "own", "kind", "region", "areas", "applicant", "gov", "since", "earlier", "refs", "coord", "approx", "pulled", "unused"),
    "farm": ("id", "title", "region", "areas", "batch", "since", "refs", "coord", "approx"),
}
# What an entry's own page shows beyond that. These are long, and wanted for one entry at a time,
# so they go in a file of their own for each province (js/data/details/), loaded when an entry's
# page is first opened there. "intro" comes from data/intros.json, if there is one.
DETAIL_FIELDS = ("area", "remark", "marks", "listed_by", "intro")
# Detail fields that keep the source's own script and are never converted.
AS_WRITTEN = ("marks",)


def encode_number(delta):
    value = ((-delta - 1) << 1) | 1 if delta < 0 else delta << 1
    out = ""
    while value >= 32:
        out += ALPHABET[(value & 31) | 32]
        value >>= 5
    return out + ALPHABET[value]


def encode_ring(ring):
    """Quantise a ring and write it as differences between consecutive points."""
    points = []
    for lon, lat in ring:
        point = (round(lon * SCALE), round(lat * SCALE))
        if not points or points[-1] != point:
            points.append(point)
    if len(points) < 4:
        return None
    out, px, py = "", 0, 0
    for x, y in points:
        out += encode_number(x - px) + encode_number(y - py)
        px, py = x, y
    return out


def encode_geometry(geometry):
    polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    out = []
    for polygon in polygons:
        rings = [encode_ring(ring) for ring in polygon]
        if rings and rings[0]:
            out.append([r for r in rings if r])
    return out


def build_regions(divisions, units_version):
    provinces = read_json(os.path.join(DATA_DIR, "regions", "provinces.geojson"))
    maritime = read_json(os.path.join(DATA_DIR, "regions", "maritime.geojson"))
    children = {}
    for unit in divisions.values():
        children[unit["parent"]] = children.get(unit["parent"], 0) + 1
    items = []
    for feature in provinces["features"]:
        props = feature["properties"]
        items.append({
            "id": feature["id"],
            "name": props["name"],
            "short": props["short"],
            "en": props["en"],
            "anchor": props["anchor"],
            "capital": props["capital"],
            "n": children.get(feature["id"], 0),  # how many units it opens into
            "polys": encode_geometry(feature["geometry"]),
        })
    lines = []
    for feature in maritime["features"]:
        lines.extend(encode_geometry(feature["geometry"]))
    # Land of one province inside another's shape (加格达奇区: Heilongjiang's, inside Inner
    # Mongolia). The page adds it to both shapes while a province is open; the national map
    # shows the provinces as the source draws them.
    enclaves = [{"from": e["from"], "to": e["to"], "ring": encode_ring(e["ring"])}
                for e in provinces.get("enclaves", [])]
    return {
        "scale": SCALE,
        "source": "datav-geoatlas",
        # What the page needs to find and load the files in js/data/units/.
        "unitsVersion": units_version,
        "unitLevels": list(UNIT_LEVELS),
        "prefixes": local_prefixes(divisions),
        "provinces": items,
        "maritime": lines,
        "enclaves": enclaves,
    }


def province_of(unit, divisions):
    while unit["parent"]:
        unit = divisions[unit["parent"]]
    return unit["id"]


def local_prefixes(divisions):
    """Which province each id prefix other than "cn" belongs to: {"hk": "cn:810000", ...}.

    An id such as cn:510104 names its province in its first two digits. Hong Kong and Macau
    districts have ids outside the national codes, so the page looks their province up here.
    """
    found = {}
    for unit in divisions.values():
        prefix = unit["id"].split(":")[0]
        if prefix != "cn":
            found[prefix] = province_of(unit, divisions)
    return dict(sorted(found.items()))


def union_outline(geometries):
    """The outer boundary of shapes that tile an area, as rings of quantised points.

    Neighbouring units in the boundary files share their borders point for point, so an edge
    between two units appears twice and an edge on the outside once. Keeping the edges that
    appear an odd number of times leaves the outside. Returns (rings, closed): `closed` is False
    if the edges do not join up into rings, which means the shapes do not tile cleanly.
    """
    count = {}
    for geometry in geometries:
        polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        for polygon in polygons:
            for ring in polygon:
                points = []
                for lon, lat in ring:
                    point = (round(lon * SCALE), round(lat * SCALE))
                    if not points or points[-1] != point:
                        points.append(point)
                if points and points[0] != points[-1]:
                    points.append(points[0])
                for a, b in zip(points, points[1:]):
                    key = (a, b) if a < b else (b, a)
                    count[key] = count.get(key, 0) + 1
    links = {}
    for (a, b), n in count.items():
        if n % 2:
            links.setdefault(a, []).append(b)
            links.setdefault(b, []).append(a)
    if any(len(others) % 2 for others in links.values()):
        return [], False
    rings = []
    for start in sorted(links):
        while links[start]:
            ring, here = [start], start
            while True:
                following = links[here].pop()
                links[following].remove(here)
                ring.append(following)
                here = following
                if here == start:
                    break
            rings.append(ring)
    return rings, True


# Which levels of shapes are compiled for the page: the units directly under a province, and the
# units under those. Each level is read from data/regions/level-<n>/, one file per parent unit.
UNIT_LEVELS = (2, 3)


def unit_file(unit_id):
    return os.path.join(ROOT, "js", "data", "units", unit_id.replace(":", "-") + ".js")


def build_units(divisions, strings):
    """Files the page loads when a unit is opened: the shapes of the units directly under it.

    Returns ({path: text}, problems), and adds the Chinese texts in the files to `strings`. Each file also carries `outline`, the outer boundary of
    those units together. The page draws an opened unit with it, because a unit's own shape
    comes from a coarser file and does not follow its parts' borders exactly. A province's file
    also lists the names of its third-level units, so the page can name the place of every
    record in the province.
    """
    children = {}
    for unit in divisions.values():
        children.setdefault(unit["parent"], []).append(unit)
    outputs, problems = {}, []
    for level in UNIT_LEVELS:
        for path in sorted(glob.glob(os.path.join(DATA_DIR, "regions", "level-%d" % level, "*.geojson"))):
            parent_id = os.path.basename(path)[:-len(".geojson")].replace("-", ":", 1)
            shapes = {feature["id"]: feature["geometry"] for feature in read_json(path)["features"]}
            units = []
            for unit in children.get(parent_id, []):
                item = {"id": unit["id"], "name": unit["name"], "short": unit["short"], "kind": unit["kind"]}
                if "en" in unit:
                    item["en"] = unit["en"]
                if "frame" in unit:
                    item["frame"] = unit["frame"]
                if unit.get("centre"):
                    item["at"] = unit["centre"]
                item["n"] = len(children.get(unit["id"], []))
                if unit["id"] in shapes:
                    item["polys"] = encode_geometry(shapes[unit["id"]])
                units.append(item)
            payload = {"parent": parent_id, "scale": SCALE, "units": units}
            rings, closed = union_outline(shapes[unit["id"]] for unit in children.get(parent_id, []) if unit["id"] in shapes)
            if not closed:
                problems.append("units of %s: their shapes do not tile, so no outline could be made" % parent_id)
            outline = [encode_ring([(x / SCALE, y / SCALE) for x, y in ring]) for ring in rings]
            payload["outline"] = [ring for ring in outline if ring]
            if level == 2:
                payload["below"] = {low["id"]: [low["name"], low["short"], low["parent"]]
                                    for unit in children.get(parent_id, []) for low in children.get(unit["id"], [])}
            chinese_strings(payload, strings)
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            outputs[unit_file(parent_id)] = (
                "/* Generated by scripts/build.py. Do not edit; edit data/ and rebuild. */\n"
                "(window.FOODMAP_UNITS=window.FOODMAP_UNITS||{})[%s]=%s;\n" % (json.dumps(parent_id), body))
    return outputs, problems


def check_divisions():
    """Check the table of administrative units. Returns the table's units by id, and any problems."""
    units = read_json(os.path.join(DATA_DIR, "divisions.json"))["units"]
    problems, by_id = [], {}
    for unit in units:
        if unit["id"] in by_id:
            problems.append("divisions: duplicate id %s" % unit["id"])
        by_id[unit["id"]] = unit
    for unit in units:
        if not unit.get("name") or not unit.get("short"):
            problems.append("divisions %s: no name" % unit["id"])
        if unit["depth"] == 1:
            if unit["parent"] is not None:
                problems.append("divisions %s: a first-level unit with a parent" % unit["id"])
            continue
        parent = by_id.get(unit["parent"])
        if parent is None or parent["depth"] != unit["depth"] - 1:
            problems.append("divisions %s: parent %r is missing or at the wrong depth" % (unit["id"], unit["parent"]))
    # The page works out a unit's province from its id alone, so the ids must allow that.
    if not problems:
        by_prefix = {}
        for unit in units:
            prefix, code = unit["id"].split(":")
            province = province_of(unit, by_id)
            if prefix == "cn":
                if province != region_id(code[:2] + "0000"):
                    problems.append("divisions %s: the code does not start with its province's two digits" % unit["id"])
            elif by_prefix.setdefault(prefix, province) != province:
                problems.append("divisions: ids starting %s: belong to more than one province" % prefix)
    first = {unit["id"] for unit in units if unit["depth"] == 1}
    if first != {region_id(code) for code, _full, _short, _en in PROVINCES}:
        problems.append("divisions: the first-level units do not match the province list in common.py")
    return by_id, problems


def build_records(region_ids, divisions):
    works = read_json(os.path.join(DATA_DIR, "works.json"))
    problems = []

    def inside(unit_id, ancestor_id):
        while unit_id:
            if unit_id == ancestor_id:
                return True
            unit_id = divisions[unit_id]["parent"]
        return False

    def check(records, label):
        for record in records:
            if record.get("region") not in region_ids:
                problems.append("%s %s: unknown region %r" % (label, record.get("id"), record.get("region")))
            for area in record.get("areas", []):
                if area not in divisions:
                    problems.append("%s %s: area %r is not in the divisions table" % (label, record.get("id"), area))
                elif not inside(area, record.get("region")):
                    problems.append("%s %s: area %r is outside its region %r" % (label, record.get("id"), area, record.get("region")))
            for ref in record.get("refs", []):
                if ref.get("w") not in works:
                    problems.append("%s %s: unknown work %r" % (label, record.get("id"), ref.get("w")))
        ids = [r["id"] for r in records]
        if len(ids) != len(set(ids)):
            problems.append("%s: duplicate ids" % label)
        return records

    def slim(records, fields):
        return [{key: record[key] for key in fields if key in record} for record in records]

    dishes = check(read_json(os.path.join(DATA_DIR, "dishes.json")), "dish")
    # Taiwan's and Macau's heritage entries come from other registers, each in a file of its own.
    heritage = read_json(os.path.join(DATA_DIR, "heritage.json"))
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "heritage_*.json"))):
        heritage += read_json(path)
    heritage = check(heritage, "heritage")
    farm = check(read_json(os.path.join(DATA_DIR, "farm_heritage.json")), "farm")
    # A later notice sometimes publishes a product again, with a remark that it replaces the entry
    # in an earlier notice of the same office. The later entry is kept, with the year of the first.
    # The files are read in the order of their notice numbers, which is the order of publication.
    by_title, replaced = {}, []
    paths = glob.glob(os.path.join(DATA_DIR, "products", "*.json"))
    # A file with no notice number (Taiwan's place marks) comes after the notices.
    def order(path):
        number = re.search(r"(\d+)\.json$", path)
        return (0, int(number.group(1))) if number else (1, 0)

    for path in sorted(paths, key=order):
        for record in read_json(path):
            earlier = by_title.get(record["title"])
            if earlier and "代替国家知识产权局" in record.get("remark", ""):
                record = dict(record, since=earlier["since"])
                replaced.append(record["title"])
            elif earlier:
                problems.append("product %s is in two notices, and the later does not say it replaces the earlier: %s, %s" % (
                    record["title"], earlier["id"], record["id"]))
            by_title[record["title"]] = record
    products, skipped = [], []
    for record in by_title.values():
        if record.get("kind") == "not-food":
            skipped.append(record["title"])
        else:
            products.append(record)
    check(products, "product")

    indicators = read_json(os.path.join(DATA_DIR, "indicators.json"))
    width = len(indicators["columns"])
    for rid, row in indicators["rows"].items():
        if rid not in region_ids:
            problems.append("indicators: unknown region %r" % rid)
        if len(row) != width:
            problems.append("indicators %s: %d values for %d columns" % (rid, len(row), width))
    for ref in indicators.get("refs", []):
        if ref.get("w") not in works:
            problems.append("indicators: unknown work %r" % ref.get("w"))

    # Food supply per person, from food balance sheets: the mainland, Hong Kong, Macau and Taiwan
    # side by side, and Taiwan's own sheet. Shown in the panel only, never as shading.
    supply = {}
    for name, path in (("compared", "supply.json"), ("taiwan", "supply_taiwan.json")):
        table = read_json(os.path.join(DATA_DIR, path))
        for area, row in table["areas"].items():
            if area != "mainland" and area not in region_ids:
                problems.append("%s: unknown region %r" % (path, area))
            if len(row) != len(table["columns"]):
                problems.append("%s %s: %d values for %d columns" % (path, area, len(row), len(table["columns"])))
        for ref in table.get("refs", []):
            if ref.get("w") not in works:
                problems.append("%s: unknown work %r" % (path, ref.get("w")))
        supply[name] = table

    # A record from a source written in Traditional Chinese keeps that wording under "hant",
    # field by field. It is shown as it stands, like the official names of places.
    official = {}
    for record in heritage + products:
        for field, text in record.get("hant", {}).items():
            if official.setdefault(record[field], text) != text:
                problems.append("%s: %s is written both %s and %s in Traditional Chinese" % (record["id"], record[field], official[record[field]], text))
    # "own" is the title in the source's script where that is not the Simplified title, for the
    # name in an entry's address. "unused" marks a stated position that was set aside.
    #
    # Lists show who an entry is filed under only where that says more than its place does.
    # "body" marks a heritage entry filed under an organisation: the register's field holds either
    # that or a plain place, and a place ends in the word for a kind of unit. "gov" marks a
    # product whose applicant is the government (in Taiwan, the office) of a unit the product is
    # placed in, which the place already says.
    from divisions import Divisions
    table = Divisions()
    for record in heritage:
        if record.get("place") and not re.search(r"[省市县区州盟旗]$", record["place"]):
            record["body"] = True
    for record in products:
        named = re.match(r"(.+?)(人民政府|政府|公所)$", record.get("applicant", ""))
        if named and set(table.locate(named.group(1), record["region"])) & set(record["areas"]):
            record["gov"] = True
    # "since" is the year of the notice a product was read from. Where the notice's remark says
    # it replaces an earlier notice and gives that notice's year, "earlier" holds it: the earliest
    # year the sources in hand give for the product. It is the year of the notice replaced, which
    # may itself have been a revision, so the page words it as that and no more.
    for record in products:
        remark = record.get("remark", "")
        years = [int(year) for year in re.findall(r"(\d{4})年", remark)] if "代替" in remark else []
        years = [year for year in years if 1995 <= year < record["since"]]
        if years:
            record["earlier"] = min(years)
    for record in heritage + products:
        own = record.get("hant", {}).get("title")
        if own and own != record["title"]:
            record["own"] = own
        if "stated_not_used" in record:
            record["unused"] = True
    # A short introduction for an entry, written for this map: {record id: {"en", "zh", "refs"}}.
    intros_path = os.path.join(DATA_DIR, "intros.json")
    intros = read_json(intros_path).get("intros", {}) if os.path.exists(intros_path) else {}
    details, known = {}, set()
    for record in dishes + heritage + products + farm:
        known.add(record["id"])
        found = {key: record[key] for key in DETAIL_FIELDS if record.get(key)}
        if record["id"] in intros:
            found["intro"] = intros[record["id"]]
        if found:
            details.setdefault(record["region"], {})[record["id"]] = found
    for rid, intro in intros.items():
        if rid not in known:
            problems.append("intros: no entry %r" % rid)
        if not intro.get("en") or not intro.get("zh") or not intro.get("refs"):
            problems.append("intros %s: needs en, zh and refs" % rid)
        for ref in intro.get("refs", []):
            if ref.get("w") not in works:
                problems.append("intros %s: unknown work %r" % (rid, ref.get("w")))
    # The fields of records whose source writes them in Traditional Chinese, as written there, for
    # the English interface: {record id: {field: text}}.
    # Their source locators are written here in Simplified; main() adds them converted, so the
    # English interface shows "where in the source" in the source's own script too.
    as_written = {}
    for record in heritage + products:
        fields = {k: v for k, v in record.get("hant", {}).items() if v != record.get(k)}
        if record.get("hant"):
            fields["refs"] = [dict(ref) for ref in record.get("refs", [])]
        if fields:
            as_written[record["id"]] = fields
    data = {
        "official": official,
        "as_written": as_written,
        "details": details,
        "works": works,
        "dishes": slim(dishes, PAGE_FIELDS["dishes"]),
        "heritage": slim(heritage, PAGE_FIELDS["heritage"]),
        "products": slim(products, PAGE_FIELDS["products"]),
        "farm": slim(farm, PAGE_FIELDS["farm"]),
        "indicators": indicators,
        "supply": supply,
    }
    return data, problems, skipped, replaced


# The kinds of record, in the order the page lists them. The position of a kind in this list is
# also how the search index names it.
RECORD_KEYS = ("dishes", "products", "heritage", "farm")


def record_file(region):
    return os.path.join(ROOT, "js", "data", "records", region.replace(":", "-") + ".js")


def build_record_files(data, region_ids, strings):
    """One file per province with that province's records. Returns ({path: text}, counts), and
    adds the Chinese texts in the files to `strings`.

    `region` is left out of each record, because the file it is in says which province it
    belongs to; the page puts it back.
    """
    groups = {region: {key: [] for key in RECORD_KEYS} for region in sorted(region_ids)}
    for key in RECORD_KEYS:
        for record in data[key]:
            groups[record["region"]][key].append({k: v for k, v in record.items() if k != "region"})
    outputs = {}
    for region, group in groups.items():
        # "own" is already in its source's script, so it is not among the texts to convert.
        chinese_strings({key: [{k: v for k, v in record.items() if k != "own"} for record in records]
                         for key, records in group.items()}, strings)
        body = json.dumps(group, ensure_ascii=False, separators=(",", ":"))
        outputs[record_file(region)] = (
            "/* Generated by scripts/build.py. Do not edit; edit data/ and rebuild. */\n"
            "(window.FOODMAP_RECORDS=window.FOODMAP_RECORDS||{})[%s]=%s;\n" % (json.dumps(region), body))
    counts = {region: {key: len(group[key]) for key in RECORD_KEYS} for region, group in groups.items()}
    return outputs, counts


def detail_file(region, language=None):
    parts = [ROOT, "js", "data", "details"] + ([language] if language else []) + [region.replace(":", "-") + ".js"]
    return os.path.join(*parts)


def build_detail_files(details, converters):
    """One file per province with what the entries' own pages show: {path: text}.

    The texts are long and made of running words, so they are not put through the page's table
    of names. A converted language gets files of its own, converted here.
    """
    def converted(value, converter):
        if isinstance(value, str):
            return converter.convert(value)
        if isinstance(value, list):
            return [converted(item, converter) for item in value]
        if isinstance(value, dict):
            return {k: (v if k in AS_WRITTEN or k in ("en", "w") else converted(v, converter)) for k, v in value.items()}
        return value

    outputs = {}
    for language, converter in [(None, None)] + sorted(converters.items()):
        for region, found in sorted(details.items()):
            value = converted(found, converter) if converter else found
            body = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            outputs[detail_file(region, language)] = (
                "/* Generated by scripts/build.py. Do not edit; edit data/ and rebuild. */\n"
                "(window.FOODMAP_DETAILS=window.FOODMAP_DETAILS||{})[%s]=%s;\n" % (json.dumps(region), body))
    return outputs


def build_dots(data):
    """Where every placed entry is, and nothing else: {province id: {kind: [lon, lat, lon, ...]}}.

    The page draws these as small quiet dots in the provinces that are not open, so the whole
    map shows where entries lie before any province's records have been fetched. Two decimal
    places, about a kilometre, is finer than a dot at that scale.
    """
    dots = {}
    for key in RECORD_KEYS[1:]:
        for record in data[key]:
            if record.get("coord"):
                flat = dots.setdefault(record["region"], {}).setdefault(key, [])
                flat += [round(record["coord"][0], 2), round(record["coord"][1], 2)]
    return dots


# The interfaces that show names from Traditional sources as their sources write them, and not
# in the script of the interface. The Chinese interfaces keep to one script each.
AS_WRITTEN_LANGUAGES = ("en",)


def build_as_written(records, divisions):
    """{id: {field: text}} for every unit and record whose source writes it in Traditional
    Chinese: places get "name" and "short", records their title and the like. The page loads it
    in the languages of AS_WRITTEN_LANGUAGES and puts these texts in place by id."""
    table = dict(records)
    for unit in divisions.values():
        hant, name, short = unit.get("hant"), unit["name"], unit["short"]
        if not hant or hant == name:
            continue
        fields = {"name": hant}
        if name.startswith(short) and len(hant) == len(name):
            fields["short"] = hant[:len(short)]
        table[unit["id"]] = fields
    return table


def build_search(data, divisions):
    """What the search box looks through: every place below province level and every title.

    places   [id, name, depth] in the order of the divisions table, so the unit a third-level
             place belongs to is the nearest second-level row above it. A fourth item holds
             other names to match: an English name, or names the place had before.
    records  {province id: [[title, kind, id], ...]}, where kind is a position in RECORD_KEYS.
             The page also looks here for the province of an entry named in the address.
    """
    places = []
    for unit in divisions.values():
        if unit["depth"] == 1:
            continue
        row = [unit["id"], unit["name"], unit["depth"]]
        other = [unit["en"]] if unit.get("en") else []
        other += unit.get("was", [])
        if other:
            row.append(" ".join(other))
        places.append(row)
    records = {}
    for index, key in enumerate(RECORD_KEYS):
        for record in data[key]:
            row = [record["title"], index, record["id"]]
            records.setdefault(record["region"], []).append(row)
    return {"kinds": list(RECORD_KEYS), "places": places, "records": records}


HAN = re.compile("[㐀-鿿\U00020000-\U0003ffff]")


def chinese_strings(value, into):
    """Add to the set `into` every text inside `value` that has a Chinese character in it.

    The page converts the same texts, found the same way: every text that is a value in a file
    it loads. Keys are never converted.
    """
    if isinstance(value, str):
        if HAN.search(value):
            into.add(value)
    elif isinstance(value, dict):
        for inner in value.values():
            chinese_strings(inner, into)
    elif isinstance(value, (list, tuple)):
        for inner in value:
            chinese_strings(inner, into)
    return into


# ---------- Traditional Chinese ----------
#
# The data is kept in Simplified Chinese. A language in data/text.json that names character
# "forms" ("tw" or "hk") is written in Traditional Chinese, converted here by scripts/hant.py:
# its interface text goes into text.js already converted, and the names in the data go into a
# table of their own that the page loads in that language only.


def names_file(key):
    return os.path.join(ROOT, "js", "data", "names", key + ".js")


def make_converters(source, divisions, official):
    """A converter for each language that needs one: {language key: Converter}."""
    converters = {}
    for language in source["languages"]:
        if language.get("forms"):
            converter = Converter(language["forms"])
            # Hong Kong and Macau districts and the units inside Taiwan have official Traditional
            # names in the table of units. They stand as they are, and so do their short forms
            # (臺北 beside 臺北市). The overrides file can still replace one.
            converter.official = set()
            for unit in divisions.values():
                if unit.get("hant"):
                    converter.texts.setdefault(unit["name"], unit["hant"])
                    converter.official.add(unit["name"])
                    if unit["short"] == unit["name"][:-1] and len(unit["hant"]) == len(unit["name"]):
                        converter.texts.setdefault(unit["short"], unit["hant"][:-1])
                        converter.official.add(unit["short"])
            for text, written in official.items():
                converter.texts.setdefault(text, written)
                converter.official.add(text)
            converters[language["key"]] = converter
    return converters


def build_names(strings, converter):
    """How the page writes each text of `strings` in Traditional Chinese. Returns (table, results).

    Sending every name twice would double what the page downloads, so the table is in two parts:
      chars  pairs of characters, Simplified then Traditional: the form each character takes in
             most of the names it appears in.
      texts  the names that come out wrong that way, in full.
    The page looks a text up in `texts` and otherwise converts it character by character. What
    it shows is therefore exactly what the converter produced here, for every text in `strings`.
    """
    results = {text: converter.convert(text) for text in sorted(strings)}
    votes = {}
    for text, result in results.items():
        if len(text) == len(result):
            for a, b in zip(text, result):
                votes.setdefault(a, {})
                votes[a][b] = votes[a].get(b, 0) + 1
    usual = {}
    for a, found in votes.items():
        best = max(sorted(found), key=lambda b: found[b])
        if best != a:
            usual[a] = best
    texts = {text: result for text, result in results.items()
             if "".join(usual.get(char, char) for char in text) != result}
    return {"chars": "".join(a + b for a, b in sorted(usual.items())), "texts": texts}, results


def like_characters(alike, strings, conversions):
    """Groups of characters that a search treats as one, as a text of groups with spaces between.

    Only the groups that have a character in what can be searched for. The first character of
    a group stands for the rest. `conversions` are the tables of results from build_names: a
    character and the form it was given are put in one group even if the tables did not.
    """
    group_of = {}
    for group in alike:
        members = set(group)
        for char in group:
            group_of[char] = members
    used = set("".join(strings))
    for results in conversions:
        for text, result in results.items():
            used.update(result)
            if len(text) != len(result):
                continue
            for a, b in zip(text, result):
                if a != b and group_of.get(a, {a}) is not group_of.get(b, {b}):
                    joined = group_of.get(a, {a}) | group_of.get(b, {b})
                    for char in joined:
                        group_of[char] = joined
    found = {"".join(sorted(group)) for group in group_of.values() if group & used}
    return " ".join(sorted(found))


def left_simplified(converter, results):
    """Problems: converted texts that still hold a character found only in Simplified Chinese.

    The tables cannot leave one behind, so this catches a slip in the overrides file, such as
    a correction typed in Simplified. A character that the place's own forms prefer (Taiwan
    writes 群, where the tables' standard form is 羣) is not a slip. Nor is an official name
    taken from the table of units: Taiwan writes 南庄鄉 with 庄.
    """
    only = {char for char, forms in converter.chars.items() if len(forms) == 1 and forms != char}
    only -= set("".join(converter.local_chars.values()))
    problems = []
    for text, result in results.items():
        found = sorted(set(result) & only)
        if found and text not in getattr(converter, "official", ()):
            problems.append("names: %s became %s, which still has the Simplified %s" % (text, result, " ".join(found)))
    return problems


READ_PATH = os.path.join(DATA_DIR, "hant-read.json")


def doubtful(converter, texts):
    """{text: result} for the texts with a character whose Traditional form depends on the word."""
    return {text: converter.convert(text) for text in sorted(texts) if converter.doubts(text)}


def print_doubts(converter, texts):
    """List texts under each doubtful character and the piece that decided its form."""
    listing = {}
    for text in sorted(texts):
        result = converter.convert(text)
        for char, form, how, piece in converter.doubts(text):
            if how == "text":
                label = "whole text, from the overrides file"
            elif how in ("usual", "our usual"):
                label = "%s→%s, %s" % (char, form, "our usual form" if how == "our usual" else "the usual form")
            else:
                label = "%s→%s, %s" % (piece, converter.convert(piece), "our phrase" if how == "ours" else "phrase")
            entry = listing.setdefault(char, {}).setdefault(label, [])
            if result not in entry:
                entry.append(result)
    for char in sorted(listing):
        print("%s  (%s)" % (char, " ".join(converter.chars[char])))
        for label in sorted(listing[char]):
            print("  %s: %s" % (label, "、".join(listing[char][label])))


def build_text(converters, names):
    """The words of the interface in every language, from data/text.json.

    Returns (value, problems). Each entry must have a text for every language, and the names in
    braces that the page fills in must be the same in each, unless the entry lists the names it
    may use under "vars": languages then differ in which of them they need. Every key that
    index.html or a script asks for by name must be in the table.

    A language with a converter takes the text it is made "from" and converts it, unless the
    entry gives a text under the language's own key, which is used as it stands: that is how the
    Traditional interface is given Taiwan's words where they differ. `names` gives the address of
    the table of converted names for each such language.
    """
    source = read_json(os.path.join(DATA_DIR, "text.json"))
    problems = []
    tables = {language["key"]: {} for language in source["languages"]}

    def holes(value):
        texts = value.values() if isinstance(value, dict) else [value]
        return set(name for text in texts for name in re.findall(r"\{(\w+)\}", text))

    for key, entry in source["text"].items():
        seen = None
        for language in source["languages"]:
            converter = converters.get(language["key"])
            if converter and language["key"] in entry:
                value, converter = entry[language["key"]], None
            else:
                value = entry.get(language["from"])
            if value is None or (isinstance(value, dict) and set(value) != {"one", "other"}):
                problems.append("text %s: no usable text for %s" % (key, language["key"]))
                continue
            if converter:
                value = ({form: converter.convert(text) for form, text in value.items()}
                         if isinstance(value, dict) else converter.convert(value))
            tables[language["key"]][key] = value
            if "vars" in entry:
                if not holes(value) <= set(entry["vars"]):
                    problems.append("text %s: a name in braces is not among its vars" % key)
            elif seen is None:
                seen = holes(value)
            elif holes(value) != seen:
                problems.append("text %s: the names in braces differ between languages" % key)

    asked = set()
    for path in [os.path.join(ROOT, "index.html")] + sorted(glob.glob(os.path.join(ROOT, "js", "*.js"))):
        text = open(path, encoding="utf-8").read()
        # Only keys written out in full: t('places.title'), not t('layer.' + key + '.label').
        asked.update(re.findall(r"\bt\('([\w.-]+)'\s*[,)]", text))
        asked.update(re.findall(r"data-t(?:-[a-z-]+)?=\"([\w.-]+)\"", text))
    for key in sorted(asked - set(source["text"])):
        problems.append("text %s: asked for by the page but not in data/text.json" % key)

    languages = []
    for language in source["languages"]:
        item = {k: language[k] for k in ("key", "tag", "name", "short")}
        if language["key"] in names:
            item["names"] = names[language["key"]]
        languages.append(item)
    return {"languages": languages, "text": tables}, problems


def interface_strings(source, language):
    """The Chinese texts of the interface that a converted language is made from."""
    found = set()
    for entry in source["text"].values():
        if language["key"] not in entry:  # a text given in full is not converted
            chinese_strings(entry.get(language["from"]), found)
    return found


def bundle(name, value):
    body = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return "/* Generated by scripts/build.py. Do not edit; edit data/ and rebuild. */\nwindow.%s = %s;\n" % (name, body)


def stamp_hashes(index_path):
    """Rewrite ?v=<hash> on local css and js addresses in index.html. Returns the new text."""
    text = open(index_path, encoding="utf-8").read()

    def repl(match):
        rel = match.group(1)
        full = os.path.join(ROOT, rel)
        if not os.path.exists(full):
            return match.group(0)
        digest = hashlib.sha256(open(full, "rb").read()).hexdigest()[:8]
        return "%s?v=%s" % (rel, digest)

    return re.sub(r"((?:css|js)/[\w./-]+\.(?:css|js))\?v=[0-9a-f]{0,8}", repl, text)


def fail_on(problems):
    if problems:
        for p in problems[:30]:
            print("  ! " + p)
        sys.exit("build failed: %d data problem(s)" % len(problems))


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def main():
    args = sys.argv[1:]
    check_only = "--check" in args
    strings = set()  # every Chinese text in the files the page loads
    divisions, division_problems = check_divisions()
    unit_outputs, unit_problems = build_units(divisions, strings)
    units_version = hashlib.sha256("".join(unit_outputs[p] for p in sorted(unit_outputs)).encode("utf-8")).hexdigest()[:8]
    regions = build_regions(divisions, units_version)
    region_ids = {p["id"] for p in regions["provinces"]}
    data, problems, skipped, replaced = build_records(region_ids, divisions)
    problems += division_problems + unit_problems
    problems += ["divisions: province %s on the map is not in the table" % rid for rid in sorted(region_ids - set(divisions))]
    fail_on(problems)

    details = data.pop("details")
    as_written = build_as_written(data.pop("as_written"), divisions)
    record_outputs, counts = build_record_files(data, region_ids, strings)
    search = build_search(data, divisions)
    chinese_strings([regions, search, data["works"], data["indicators"], data["supply"]], strings)

    # Traditional Chinese: a table of names for each language that is converted.
    text_source = read_json(os.path.join(DATA_DIR, "text.json"))
    converters = make_converters(text_source, divisions, data.pop("official"))
    name_outputs, names, conversions, doubts, name_problems = {}, {}, [], {}, []
    for language in text_source["languages"]:
        converter = converters.get(language["key"])
        if not converter:
            continue
        table, results = build_names(strings, converter)
        conversions.append(results)
        body = bundle("FOODMAP_NAMES", table)
        name_outputs[names_file(language["key"])] = body
        names[language["key"]] = "js/data/names/%s.js?v=%s" % (language["key"], digest(body))
        shown = strings | interface_strings(text_source, language)
        doubts[language["key"]] = doubtful(converter, shown)
        name_problems += left_simplified(converter, {text: converter.convert(text) for text in shown})
    search["alike"] = like_characters(read_json(os.path.join(DATA_DIR, "hant.json"))["alike"], strings, conversions)

    # Names with a character whose form depends on the word are worth reading through once.
    # data/hant-read.json records the ones that have been, with the form they had then.
    read = read_json(READ_PATH)["read"] if os.path.exists(READ_PATH) else {}
    unread = {key: {text: result for text, result in found.items() if read.get(key, {}).get(text) != result}
              for key, found in doubts.items()}
    if "--names" in args:
        for key, found in unread.items():
            print("== %s: %d of %d doubtful names not yet read through" % (key, len(found), len(doubts[key])))
            print_doubts(converters[key], found)
        return
    if "--names-read" in args:
        write_json(READ_PATH, {
            "note": "Converted names that have been read through, with the form they had then. "
                    "Written by python3 scripts/build.py --names-read; do not edit.",
            "read": doubts,
        })
        print("recorded %d names as read through" % sum(len(found) for found in doubts.values()))
        return

    detail_outputs = build_detail_files(details, converters)
    converter = next(iter(converters.values()))
    for fields in as_written.values():
        for ref in fields.get("refs", []):
            if ref.get("loc"):
                ref["loc"] = converter.convert(ref["loc"])
    as_written_body = bundle("FOODMAP_AS_WRITTEN", as_written)
    as_written_path = "js/data/names/en.js?v=%s" % digest(as_written_body)
    text, text_problems = build_text(converters, names)
    for language in text["languages"]:
        if language["key"] in AS_WRITTEN_LANGUAGES:
            language["asWritten"] = as_written_path
    fail_on(text_problems + name_problems)
    search_text = bundle("FOODMAP_SEARCH", search)
    dots_text = bundle("FOODMAP_DOTS", build_dots(data))
    summary = {
        "works": data["works"],
        "indicators": data["indicators"],
        "supply": data["supply"],
        # How many records each province has of each kind, so the page can show totals before
        # any province's records have loaded.
        "counts": counts,
        # How many records of each kind have a position on the map, for the legend.
        "placed": {key: sum(1 for record in data[key] if record.get("coord")) for key in RECORD_KEYS[1:]},
        # One hash for the files loaded on demand, for their ?v= addresses.
        "recordsVersion": digest("".join(record_outputs[p] for p in sorted(record_outputs))),
        "searchVersion": digest(search_text),
        "dotsVersion": digest(dots_text),
        # The provinces that have a file of details for their entries' own pages.
        "detailed": sorted(details),
        "detailsVersion": digest("".join(detail_outputs[p] for p in sorted(detail_outputs))),
    }
    outputs = {
        os.path.join(ROOT, "js", "data", "regions.js"): bundle("FOODMAP_REGIONS", regions),
        os.path.join(ROOT, "js", "data", "summary.js"): bundle("FOODMAP_DATA", summary),
        os.path.join(ROOT, "js", "data", "search.js"): search_text,
        os.path.join(ROOT, "js", "data", "dots.js"): dots_text,
        os.path.join(ROOT, "js", "data", "text.js"): bundle("FOODMAP_TEXT", text),
    }
    main_outputs = list(outputs)
    outputs.update(unit_outputs)
    outputs.update(record_outputs)
    outputs.update(detail_outputs)
    outputs[os.path.join(ROOT, "js", "data", "names", "en.js")] = as_written_body
    outputs.update(name_outputs)
    stale = []
    # Generated files that this run no longer produces, such as a unit that has been recoded.
    for path in sorted(glob.glob(os.path.join(ROOT, "js", "data", "**", "*.js"), recursive=True)):
        if path not in outputs:
            stale.append(os.path.relpath(path, ROOT) + " (no longer produced)")
            if not check_only:
                os.remove(path)
    for path, text in outputs.items():
        current = open(path, encoding="utf-8").read() if os.path.exists(path) else None
        if current != text:
            stale.append(os.path.relpath(path, ROOT))
            if not check_only:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)

    index_path = os.path.join(ROOT, "index.html")
    if os.path.exists(index_path):
        stamped = stamp_hashes(index_path)
        if stamped != open(index_path, encoding="utf-8").read():
            stale.append("index.html (asset hashes)")
            if not check_only:
                with open(index_path, "w", encoding="utf-8") as fh:
                    fh.write(stamped)

    if check_only:
        if stale:
            sys.exit("out of date: " + ", ".join(stale) + ". Run python3 scripts/build.py")
        print("bundles are up to date")
        return

    vertices = sum(len(ring) for p in regions["provinces"] for poly in p["polys"] for ring in poly)
    print("regions: %d provinces, %d characters of boundary data" % (len(regions["provinces"]), vertices))
    print("divisions: %d units checked" % len(divisions))
    print("records: %d dishes, %d heritage entries, %d products, %d farm heritage systems" % (
        len(data["dishes"]), len(data["heritage"]), len(data["products"]), len(data["farm"])))
    if skipped:
        print("products left out as not food: %d" % len(skipped))
    if replaced:
        print("earlier entries left out, replaced by a later notice: %d (%s)" % (len(replaced), "、".join(replaced)))
    for path in main_outputs:
        print("wrote %s (%d KB)" % (os.path.relpath(path, ROOT), os.path.getsize(path) // 1024))
    print("wrote %d unit files in js/data/units (%d KB in all)" % (
        len(unit_outputs), sum(os.path.getsize(path) for path in unit_outputs) // 1024))
    print("wrote %d record files in js/data/records (%d KB in all)" % (
        len(record_outputs), sum(os.path.getsize(path) for path in record_outputs) // 1024))
    for path in name_outputs:
        key = os.path.basename(path)[:-len(".js")]
        print("wrote %s (%d KB): %d texts converted, %d with a character whose form depends on the word, %d of those not yet read through" % (
            os.path.relpath(path, ROOT), os.path.getsize(path) // 1024, len(strings), len(doubts[key]), len(unread[key])))
    if stale:
        print("updated: " + ", ".join(stale[:6]) + (" and %d more" % (len(stale) - 6) if len(stale) > 6 else ""))


if __name__ == "__main__":
    main()
