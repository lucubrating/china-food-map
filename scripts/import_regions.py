#!/usr/bin/env python3
"""Import the first level of the base map from the DataV GeoAtlas files.

Sources (downloaded into research/downloads/datav-geoatlas/):
  100000_full.json       province-level boundaries, plus the maritime dashed line
  100000_full_city.json  boundaries of the second level
  level-3/*_full.json    boundaries of the third level, one file per second-level unit

Outputs:
  data/regions/provinces.geojson  boundaries of the 34 province-level units, with ids "cn:<code>"
  data/regions/maritime.geojson   the dashed line feature, kept apart from the provinces
  data/regions/level-2/*.geojson  second-level boundaries, one file per province
  data/regions/level-3/*.geojson  third-level boundaries, one file per second-level unit

Kinmen and Matsu. The source draws the islands that Taiwan administers as 金門縣 and 連江縣 inside
Fujian's shapes. They are on the map once, as Taiwan's units (scripts/import_taiwan.py), so here
those islands are taken out of Fujian's shapes at every level, and a unit that the divisions
table marks "shape": false gets no shape at all. On the overview the islands are still drawn:
the pieces taken out of Fujian's province shape are added to Taiwan's. Run scripts/import_taiwan.py before this script.

加格达奇区. It belongs to Heilongjiang (大兴安岭地区) but lies inside Inner Mongolia's 呼伦贝尔市. The
province-level file draws it as Inner Mongolia's and leaves it out of Heilongjiang's shape, while
the second-level file cuts it out of 呼伦贝尔. The province shapes are kept as the source draws them,
for the national map, and the piece, taken from that hole, is recorded beside them under
"enclaves" (ENCLAVES). The page adds it, as a hole in Inner Mongolia and a part of Heilongjiang,
while a province is open, so the levels agree from there down.

Slivers. A hole under SPECK square kilometres in a second- or third-level shape that no unit of
the same file fills is a sliver where the source's files disagree by a few hundred metres, as on
the Anhui-Jiangxi border. It is closed, so it is not a blank speck when the province is open.

Names, parents and centre points of the units at every level are in data/divisions.json, which
scripts/import_divisions.py builds. Run that script first: this one takes each unit's id from it.

Usage: python3 scripts/import_regions.py
"""
import glob
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA_DIR, DOWNLOADS_DIR, PROVINCES, read_json, region_id, write_json  # noqa: E402

ISLANDS_OF = ("tw:09020", "tw:09007")  # Taiwan's 金門縣 and 連江縣
NEAR = 0.01  # degrees, about a kilometre: the two sources' coordinates differ by a few hundred metres

# Land of one province that the province-level file gives to another:
# (the unit, the source code of the second-level unit that has a hole for it, from, to).
ENCLAVES = [("cn:232761", "150700", "150000", "230000")]  # 加格达奇区: Inner Mongolia -> Heilongjiang
SPECK = 1.0  # square kilometres


def inside(point, ring):
    """Whether a point lies inside a ring (even-odd rule)."""
    x, y = point
    found = False
    for i in range(len(ring)):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[i - 1][0], ring[i - 1][1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            found = not found
    return found


def covers(geometry, point):
    polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    return any(inside(point, p[0]) and not any(inside(point, h) for h in p[1:]) for p in polygons)


def interior_point(ring):
    """A point inside a ring: its mean point if that is inside, else the middle of a chord."""
    mean = (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))
    if inside(mean, ring):
        return mean
    step = max(1, len(ring) // 20)
    for i in range(0, len(ring), step):
        for j in range(i + 2, len(ring), step):
            middle = ((ring[i][0] + ring[j][0]) / 2, (ring[i][1] + ring[j][1]) / 2)
            if inside(middle, ring):
                return middle
    return mean


def area_km2(ring):
    """The area of a ring of longitude and latitude, roughly, in square kilometres."""
    twice = sum(ring[i][0] * ring[i - 1][1] - ring[i - 1][0] * ring[i][1] for i in range(len(ring)))
    lat = sum(p[1] for p in ring) / len(ring)
    return abs(twice) / 2 * 111.32 * 111.32 * math.cos(math.radians(lat))


def enclave_rings(src):
    """{from province code: [(ring, to province code)]}, from the holes the enclaves leave in the
    second-level file."""
    centres = {u["id"]: u.get("centre") for u in read_json(os.path.join(DATA_DIR, "divisions.json"))["units"]}
    cities = {str(f["properties"].get("adcode")): f["geometry"] for f in read_json(os.path.join(src, "100000_full_city.json"))["features"]}
    out = {}
    for unit, city, source, target in ENCLAVES:
        geometry = cities[city]
        polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        holes = [h for p in polygons for h in p[1:] if inside(centres[unit], h)]
        if len(holes) != 1:
            sys.exit("no single hole for %s in the shape of %s" % (unit, city))
        out.setdefault(source, []).append((holes[0], target))
    return out


def recorded_enclaves(features, rings):
    """The enclaves as [{unit, from, to, ring}], each checked to lie inside one piece of the
    province the source gives it to. The province shapes themselves are not changed."""
    by_code = {f["id"].split(":")[1]: f for f in features}
    out = []
    for source, pieces in rings.items():
        for ring, target in pieces:
            point = interior_point(ring)
            geometry = by_code[source]["geometry"]
            polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
            if len([p for p in polygons if inside(point, p[0])]) != 1:
                sys.exit("the enclave at %s is not inside one piece of %s" % (point, source))
            unit = [u for u, _c, s_, t_ in ENCLAVES if s_ == source and t_ == target][0]
            out.append({"unit": unit, "from": region_id(source), "to": region_id(target), "ring": ring})
    return out


def close_specks(items):
    """Close the holes under SPECK square kilometres that no other unit of the file fills.
    Returns how many were closed."""
    closed = 0
    for feature in items:
        for polygon in feature["geometry"]["coordinates"]:
            kept = [polygon[0]]
            for hole in polygon[1:]:
                point = interior_point(hole)
                filled = any(covers(other["geometry"], point) for other in items if other is not feature)
                if area_km2(hole) < SPECK and not filled:
                    closed += 1
                else:
                    kept.append(hole)
            polygon[:] = kept
    return closed


def island_boxes():
    """The bounding box of each island of Taiwan's Kinmen and Matsu, widened a little."""
    path = os.path.join(DATA_DIR, "regions", "level-2", "cn-710000.geojson")
    boxes = []
    if os.path.exists(path):
        for feature in read_json(path)["features"]:
            if feature["id"] in ISLANDS_OF:
                for polygon in feature["geometry"]["coordinates"]:
                    xs, ys = [p[0] for p in polygon[0]], [p[1] for p in polygon[0]]
                    boxes.append((min(xs) - NEAR, min(ys) - NEAR, max(xs) + NEAR, max(ys) + NEAR))
    return boxes


def without_islands(geometry, boxes, counter, taken=None):
    """A copy of a Fujian shape without the pieces that are islands of Kinmen or Matsu.

    A piece is one of those islands if the middle of its outline falls in an island's box.
    The pieces removed are added to `taken`, if it is given.
    """
    polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    kept = []
    for polygon in polygons:
        ring = polygon[0]
        x, y = sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)
        if any(a <= x <= c and b <= y <= d for a, b, c, d in boxes):
            counter[0] += 1
            if taken is not None:
                taken.append(polygon)
        else:
            kept.append(polygon)
    return {"type": "MultiPolygon", "coordinates": kept}


def main():
    src = os.path.join(DOWNLOADS_DIR, "datav-geoatlas")
    boxes, removed, moved = island_boxes(), [0], []
    provinces = read_json(os.path.join(src, "100000_full.json"))
    english = {code: en for code, _full, _short, en in PROVINCES}
    short = {code: s for code, _full, s, _en in PROVINCES}

    features, maritime = [], []
    for f in provinces["features"]:
        props = f["properties"]
        code = str(props.get("adcode"))
        if code.endswith("_JD"):
            maritime.append({"type": "Feature", "id": "cn:maritime-line", "properties": {"kind": "maritime-line"}, "geometry": f["geometry"]})
            continue
        if code not in english:
            print("  ! unexpected feature:", code, props.get("name"))
            continue
        anchor = props.get("centroid") or props.get("center")
        features.append({
            "type": "Feature",
            "id": region_id(code),
            "properties": {
                "name": props["name"],
                "short": short[code],
                "en": english[code],
                "level": "province",
                "anchor": [round(anchor[0], 3), round(anchor[1], 3)],
                "capital": [round(props["center"][0], 3), round(props["center"][1], 3)],
            },
            "geometry": without_islands(f["geometry"], boxes, removed, moved) if code == "350000" else f["geometry"],
        })
    enclaves = recorded_enclaves(features, enclave_rings(src))
    # The islands stay on the overview, as part of Taiwan's shape, so a click on them opens Taiwan.
    for feature in features:
        if feature["id"] == region_id("710000") and moved:
            geometry = feature["geometry"]
            polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
            feature["geometry"] = {"type": "MultiPolygon", "coordinates": polygons + moved}
    features.sort(key=lambda f: f["id"])
    note = "Boundaries from DataV GeoAtlas, version of May 2021. Coordinates are as published by the source."
    write_json(os.path.join(DATA_DIR, "regions", "provinces.geojson"), {"type": "FeatureCollection", "source": note, "features": features, "enclaves": enclaves})
    write_json(os.path.join(DATA_DIR, "regions", "maritime.geojson"), {"type": "FeatureCollection", "source": note, "features": maritime})

    print("provinces: %d | maritime features: %d" % (len(features), len(maritime)))
    lower_levels(src, note, boxes, removed)
    print("pieces of Fujian's shapes left out as islands of Kinmen and Matsu: %d" % removed[0])


def trimmed(geometry):
    """A copy of a geometry with coordinates rounded to four places, about ten metres."""
    def ring(points):
        out = []
        for lon, lat in points:
            pair = [round(lon, 4), round(lat, 4)]
            if not out or out[-1] != pair:
                out.append(pair)
        return out
    polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    return {"type": "MultiPolygon", "coordinates": [[ring(r) for r in polygon] for polygon in polygons]}


def lower_levels(src, note, boxes, removed):
    """Write the shapes of the second and third levels, one file per parent unit.

    data/regions/level-2/cn-510000.geojson holds the units directly under Sichuan, and
    data/regions/level-3/cn-510100.geojson those under Chengdu. Each feature's id is the unit's
    id in data/divisions.json, which is not always the code the boundary source uses.
    """
    table = read_json(os.path.join(DATA_DIR, "divisions.json"))["units"]
    by_source = {(unit.get("source_code") or unit["id"].split(":")[1]): unit for unit in table}

    specks = [0]

    def write(level, features_by_parent):
        folder = os.path.join(DATA_DIR, "regions", "level-%d" % level)
        os.makedirs(folder, exist_ok=True)
        count = 0
        for parent, items in sorted(features_by_parent.items()):
            items.sort(key=lambda item: item["id"])
            specks[0] += close_specks(items)
            path = os.path.join(folder, parent.replace(":", "-") + ".geojson")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"type": "FeatureCollection", "source": note, "features": items}, fh, ensure_ascii=False, separators=(",", ":"))
                fh.write("\n")
            count += len(items)
        return len(features_by_parent), count

    def collect(features, grouped, depth):
        for f in features:
            unit = by_source.get(str(f["properties"].get("adcode")))
            if not unit or unit["depth"] != depth or not f.get("geometry") or unit.get("shape") is False:
                continue
            geometry = f["geometry"]
            if unit["id"].startswith("cn:35"):
                geometry = without_islands(geometry, boxes, removed)
            grouped.setdefault(unit["parent"], []).append(
                {"type": "Feature", "id": unit["id"], "properties": {"name": unit["name"]}, "geometry": trimmed(geometry)})

    second = {}
    collect(read_json(os.path.join(src, "100000_full_city.json"))["features"], second, 2)
    third = {}
    for path in sorted(glob.glob(os.path.join(src, "level-3", "*_full.json"))):
        collect(read_json(path)["features"], third, 3)
    print("second level: %d files, %d units | third level: %d files, %d units" % (write(2, second) + write(3, third)))
    print("slivers closed: %d" % specks[0])


if __name__ == "__main__":
    main()
