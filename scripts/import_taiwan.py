#!/usr/bin/env python3
"""Import Taiwan's cities, counties, townships and districts: their names, codes and shapes.

Source (downloaded into research/downloads/taiwan-boundaries/), from the National Land Surveying
and Mapping Center of Taiwan's interior ministry, under the Open Government Data License:
  town-twd97/TOWN_MOI_1120317.shp   368 townships and districts, version of March 2023

Outputs:
  data/regions/taiwan-units.json          one row per unit: code, parent, names, centre
  data/regions/level-2/cn-710000.geojson  shapes of the 22 cities and counties
  data/regions/level-3/tw-<code>.geojson  shapes of the townships and districts of each

Only the township file is read. The shape of a city or county is made here from its townships,
so the two levels agree with each other exactly.

Names. The file's names are in Traditional Chinese. The project keeps names in Simplified, so
each is converted with the OpenCC table (research/downloads/opencc/TSCharacters.txt) and the
file's own form is kept beside it as `hant`, which the page shows as it stands.

Shapes. The file is survey-grade: 1.1 million points. The page draws on a grid of 0.001 degree,
about 100 m, so the points are put on that grid first. Then every stretch of border between two
meeting points is simplified once, and both units that share it get the same result, so
neighbours still fit without gaps. Islands too small to draw are dropped.

Left out, because they lie so far away that the unit holding them could not be shown at a
useful size: the islands the file gives to 頭城鎮 east of 123°E, and those it gives to 旗津區
south of 21.5°N.

Usage: python3 -I scripts/import_taiwan.py
Then:  python3 scripts/import_divisions.py && python3 scripts/build.py
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shapefile  # noqa: E402
from common import DATA_DIR, DOWNLOADS_DIR, write_json  # noqa: E402

SOURCE = os.path.join(DOWNLOADS_DIR, "taiwan-boundaries", "town-twd97", "TOWN_MOI_1120317.shp")
T2S = os.path.join(DOWNLOADS_DIR, "opencc", "TSCharacters.txt")
UNITS_PATH = os.path.join(DATA_DIR, "regions", "taiwan-units.json")
TAIWAN = "cn:710000"
GRID = 1000            # points per degree, the same as SCALE in build.py
TOLERANCE = (0.8, 1.6)  # how far a simplified border may stray, in grid steps: townships, counties
SMALLEST = 4           # an island under this many grid squares, about 0.04 sq km, is dropped
NOTE = ("Boundaries from the National Land Surveying and Mapping Center, Ministry of the Interior, Taiwan "
        "(鄉鎮市區界線, version of March 2023), under the Open Government Data License, version 1. "
        "Simplified for this map. Coordinates are TWD97 longitude and latitude.")


def too_far(ring):
    lon, lat = ring[0]
    return lat < 21.5 or (lon > 123.0 and lat > 25.0)


def simplified_chinese(text, table):
    return "".join(table.get(char, char) for char in text)


def area(ring):
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:])) / 2


def on_grid(ring):
    """A ring on the grid, closed, without repeated points or steps straight back."""
    points = []
    for lon, lat in ring:
        point = (round(lon * GRID), round(lat * GRID))
        if points and points[-1] == point:
            continue
        if len(points) > 1 and points[-2] == point:
            points.pop()
            continue
        points.append(point)
    while len(points) > 3 and points[0] == points[-1] and points[1] == points[-2]:
        points = points[1:-1]
    if points and points[0] != points[-1]:
        points.append(points[0])
    return points


def reduce_line(points, tolerance):
    """Douglas-Peucker: drop points that lie within `tolerance` of the line through the kept ones."""
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        if last - first < 2:
            continue
        (x1, y1), (x2, y2) = points[first], points[last]
        dx, dy = x2 - x1, y2 - y1
        length = (dx * dx + dy * dy) ** 0.5
        worst, at = -1.0, None
        for index in range(first + 1, last):
            px, py = points[index]
            if length:
                distance = abs(dy * (px - x1) - dx * (py - y1)) / length
            else:
                distance = ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
            if distance > worst:
                worst, at = distance, index
        if worst > tolerance:
            keep[at] = True
            stack += [(first, at), (at, last)]
    return [point for point, kept in zip(points, keep) if kept]


def simplify(rings_by_unit, tolerance):
    """Simplify the rings of units that tile an area, keeping shared borders shared.

    `rings_by_unit` is {unit: [closed ring of grid points]}. A point where three or more borders
    meet is kept. The stretch between two such points is simplified in one fixed direction, so
    the units on both sides of it get the same points.
    """
    around = collections.defaultdict(set)
    for rings in rings_by_unit.values():
        for ring in rings:
            for a, b in zip(ring, ring[1:]):
                around[a].add(b)
                around[b].add(a)
    done = {}

    def stretch(points):
        backwards = points[0] > points[-1] or (points[0] == points[-1] and points[1] > points[-2])
        key = tuple(points[::-1] if backwards else points)
        if key not in done:
            done[key] = reduce_line(list(key), tolerance)
        return done[key][::-1] if backwards else done[key]

    out = {}
    for unit, rings in rings_by_unit.items():
        result = []
        for ring in rings:
            body = ring[:-1]
            meeting = [i for i, point in enumerate(body) if len(around[point]) != 2]
            if not meeting:
                # A ring on its own, such as an island. Cut it at two far-apart points.
                start = body.index(min(body))
                body = body[start:] + body[:start]
                far = max(range(len(body)), key=lambda i: (body[i][0] - body[0][0]) ** 2 + (body[i][1] - body[0][1]) ** 2)
                new = stretch(body[:far + 1])[:-1] + stretch(body[far:] + body[:1])
            else:
                body = body[meeting[0]:] + body[:meeting[0]]
                cuts = [i - meeting[0] for i in meeting] + [len(body)]
                body.append(body[0])
                new = []
                for first, last in zip(cuts, cuts[1:]):
                    new += stretch(body[first:last + 1])[:-1]
                new.append(new[0])
            if len(set(new)) >= 3 and area(new):
                result.append(new)
        out[unit] = result
    return out


def outer_rings(rings):
    """The outside of rings that tile an area: the edges that belong to one ring only, joined up."""
    count = collections.Counter()
    for ring in rings:
        for a, b in zip(ring, ring[1:]):
            count[(a, b) if a < b else (b, a)] += 1
    links = collections.defaultdict(list)
    for (a, b), n in count.items():
        if n % 2:
            links[a].append(b)
            links[b].append(a)
    if any(len(others) % 2 for others in links.values()):
        raise ValueError("the shapes do not tile")
    found = []
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
            found.append(ring)
    return found


def inside(point, ring):
    x, y = point
    hit = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def polygons(rings):
    """Sort rings into polygons, each an outer ring followed by its holes, largest first."""
    def probe(ring):  # a point just off the grid, on the ring's first edge
        (x1, y1), (x2, y2) = ring[0], ring[1]
        return ((x1 + x2) / 2 + 0.0131, (y1 + y2) / 2 + 0.0173)

    depth = {}
    for index, ring in enumerate(rings):
        point = probe(ring)
        depth[index] = [other for other, outer in enumerate(rings) if other != index and inside(point, outer)]
    found = {index: [rings[index]] for index in depth if len(depth[index]) % 2 == 0}
    for index, holders in depth.items():
        if len(holders) % 2:
            outers = [h for h in holders if h in found]
            if outers:
                found[min(outers, key=lambda h: abs(area(rings[h])))].append(rings[index])
    return sorted(found.values(), key=lambda polygon: -abs(area(polygon[0])))


def centre(polygon):
    """The centre of area of a polygon's outer ring, in degrees."""
    ring = polygon[0]
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    return [round(cx / (3 * a) / GRID, 3), round(cy / (3 * a) / GRID, 3)]


def geometry(polys):
    return {"type": "MultiPolygon",
            "coordinates": [[[[x / GRID, y / GRID] for x, y in ring] for ring in polygon] for polygon in polys]}


def write_shapes(path, features):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "source": NOTE, "features": features}, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")


def main():
    table = {}
    with open(T2S, encoding="utf-8") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) >= 2:
                table[parts[0]] = parts[1]

    records = shapefile.read(SOURCE)
    towns, counties, raw, left_out, points_in = {}, {}, {}, collections.Counter(), 0
    for fields, rings in records:
        code, county = fields["TOWNCODE"], fields["COUNTYCODE"]
        towns[code] = {"code": code, "parent": county, "hant": fields["TOWNNAME"], "en": fields["TOWNENG"]}
        counties.setdefault(county, {"code": county, "parent": None, "hant": fields["COUNTYNAME"]})
        kept = []
        for ring in rings:
            points_in += len(ring)
            if too_far(ring):
                left_out[fields["COUNTYNAME"] + fields["TOWNNAME"]] += 1
                continue
            ring = on_grid(ring)
            if len(set(ring)) >= 3 and area(ring):
                kept.append(ring)
        # Small islands go, but a unit always keeps its largest piece.
        largest = max(kept, key=lambda ring: abs(area(ring)))
        raw[code] = [ring for ring in kept if ring is largest or abs(area(ring)) >= SMALLEST]

    town_rings = simplify(raw, TOLERANCE[0])
    for code, rings in town_rings.items():
        if not rings:
            sys.exit("no shape left for %s %s" % (code, towns[code]["hant"]))

    by_county = collections.defaultdict(list)
    for code in sorted(towns):
        by_county[towns[code]["parent"]].append(code)
    whole = {county: outer_rings([ring for code in codes for ring in town_rings[code]]) for county, codes in by_county.items()}
    county_rings = simplify(whole, TOLERANCE[1])

    # English names of the cities and counties come from the towns' file only as codes, so they
    # are read from the county file's table, which has nothing else this script needs.
    county_table = os.path.join(DOWNLOADS_DIR, "taiwan-boundaries", "county-twd97", "COUNTY_MOI_1090820.dbf")
    for row in shapefile.read_dbf(county_table):
        if row["COUNTYCODE"] in counties:
            if counties[row["COUNTYCODE"]]["hant"] != row["COUNTYNAME"]:
                sys.exit("the two files name %s differently" % row["COUNTYCODE"])
            counties[row["COUNTYCODE"]]["en"] = row["COUNTYENG"]

    points_out = 0
    features = []
    for county in sorted(counties):
        polys = polygons(county_rings[county])
        counties[county]["centre"] = centre(polys[0])
        features.append({"type": "Feature", "id": "tw:" + county, "properties": {"name": counties[county]["hant"]}, "geometry": geometry(polys)})
        lower = []
        for code in by_county[county]:
            polys = polygons(town_rings[code])
            towns[code]["centre"] = centre(polys[0])
            points_out += sum(len(ring) for polygon in polys for ring in polygon)
            lower.append({"type": "Feature", "id": "tw:" + code, "properties": {"name": towns[code]["hant"]}, "geometry": geometry(polys)})
        write_shapes(os.path.join(DATA_DIR, "regions", "level-3", "tw-%s.geojson" % county), lower)
    write_shapes(os.path.join(DATA_DIR, "regions", "level-2", TAIWAN.replace(":", "-") + ".geojson"), features)

    rows = []
    for county in sorted(counties):
        for unit in [counties[county]] + [towns[code] for code in by_county[county]]:
            rows.append({
                "id": "tw:" + unit["code"],
                "parent": "tw:" + unit["parent"] if unit["parent"] else TAIWAN,
                "name": simplified_chinese(unit["hant"], table),
                "hant": unit["hant"],
                "en": unit["en"],
                "centre": unit["centre"],
            })
    write_json(UNITS_PATH, {
        "note": "Generated by scripts/import_taiwan.py from the surveying centre's township file. Do not edit by hand. "
                "`name` is converted from `hant`, the name as the file gives it.",
        "source": NOTE,
        "units": rows,
    })

    print("cities and counties: %d | townships and districts: %d" % (len(counties), len(towns)))
    print("points: %d in the file, %d kept for the townships" % (points_in, points_out))
    print("rings left out as too far away: %s" % (dict(left_out) or "none"))
    changed = sum(1 for row in rows if row["name"] != row["hant"])
    print("names: %d of %d differ in Simplified Chinese" % (changed, len(rows)))


if __name__ == "__main__":
    main()
