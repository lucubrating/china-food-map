"""Shapes of administrative units, read from the boundary files, for finding the unit at a point.

The files are the ones in research/downloads/datav-geoatlas/. They are read only when needed:
the second-level file once, and a third-level file the first time a point falls in its parent.
Standard library only.
"""
import os

from common import DOWNLOADS_DIR, read_json

SOURCE = os.path.join(DOWNLOADS_DIR, "datav-geoatlas")


def _rings(geometry):
    """Each polygon of a geometry as a list of rings."""
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"]]
    return geometry["coordinates"]


def _in_polygon(lon, lat, rings):
    """Even-odd test over all rings, so a point inside a hole counts as outside."""
    inside = False
    for ring in rings:
        j = len(ring) - 1
        for i in range(len(ring)):
            xi, yi = ring[i][0], ring[i][1]
            xj, yj = ring[j][0], ring[j][1]
            if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
                inside = not inside
            j = i
    return inside


class Shapes:
    def __init__(self, divisions):
        self.divisions = divisions
        # A unit's code in the boundary files, which is sometimes older than the code in its id.
        self.by_source = {}
        for unit in divisions.units:
            code = unit.get("source_code") or unit["id"].split(":")[1]
            self.by_source[code] = unit["id"]
        self.source_of = {unit_id: code for code, unit_id in self.by_source.items()}
        self._loaded = {}   # parent id -> {unit id: (bbox, polygons)}
        self._second = None

    def _features(self, parent_id):
        parent = self.divisions.get(parent_id)
        if parent["depth"] == 1:
            if self._second is None:
                self._second = read_json(os.path.join(SOURCE, "100000_full_city.json"))["features"]
            code = int(parent_id.split(":")[1])
            return [f for f in self._second if (f["properties"].get("parent") or {}).get("adcode") == code]
        path = os.path.join(SOURCE, "level-3", "%s_full.json" % self.source_of[parent_id])
        return read_json(path)["features"] if os.path.exists(path) else []

    def children(self, parent_id):
        """Shapes of the units directly under a unit: {unit id: (bbox, polygons)}."""
        if parent_id not in self._loaded:
            found = {}
            for feature in self._features(parent_id):
                unit_id = self.by_source.get(str(feature["properties"].get("adcode")))
                geometry = feature.get("geometry")
                if not unit_id or not geometry:
                    continue
                polygons = _rings(geometry)
                xs = [p[0] for poly in polygons for p in poly[0]]
                ys = [p[1] for poly in polygons for p in poly[0]]
                found[unit_id] = ((min(xs), min(ys), max(xs), max(ys)), polygons)
            self._loaded[parent_id] = found
        return self._loaded[parent_id]

    def bbox(self, unit_id):
        """(west, south, east, north) of a unit below the first level, or None."""
        parent = self.divisions.get(unit_id)["parent"]
        entry = self.children(parent).get(unit_id) if parent else None
        return entry[0] if entry else None

    def child_at(self, lon, lat, parent_id):
        for unit_id, (box, polygons) in self.children(parent_id).items():
            if box[0] <= lon <= box[2] and box[1] <= lat <= box[3]:
                if any(_in_polygon(lon, lat, rings) for rings in polygons):
                    return unit_id
        return None

    def dot_for(self, unit_ids, province_id):
        """A point for a record placed in these units, always inside one of them.

        One unit gives its centre. Several give the mean of their centres, unless that falls
        outside all of them (two counties with a third between them), and then the centre
        nearest the mean.
        """
        mean = self.divisions.centre_of(unit_ids)
        centres = [self.divisions.get(u)["centre"] for u in unit_ids if self.divisions.get(u).get("centre")]
        if not mean or len(centres) < 2:
            return mean
        at = self.unit_at(mean[0], mean[1], province_id)
        if at and any(self.divisions.inside(at, u) or self.divisions.inside(u, at) for u in unit_ids):
            return mean
        return min(centres, key=lambda c: (c[0] - mean[0]) ** 2 + (c[1] - mean[1]) ** 2)

    def within_units(self, lon, lat, unit_ids, province_id):
        """True if the point falls inside the shape of one of the units, or of a unit inside one."""
        at = self.unit_at(lon, lat, province_id)
        return bool(at) and any(self.divisions.inside(at, u) or self.divisions.inside(u, at) for u in unit_ids)

    def pull_inside(self, lon, lat, unit_ids, province_id, steps=200, margin=0.02):
        """Move a point that lies just outside its units back inside, keeping its direction.

        The point slides along the straight line to the centre of the nearest of the units and
        stops at the first place that is inside one of them. It then goes a little further, so
        the dot does not sit on the border: `margin` degrees (about 2 km), or a quarter of the
        way that is left to the centre if that is less. Returns the new point, or None if no
        unit has a centre or the line never enters a unit with the margin to spare.
        """
        centres = [self.divisions.get(u)["centre"] for u in unit_ids if self.divisions.get(u).get("centre")]
        if not centres:
            return None
        cx, cy = min(centres, key=lambda c: (c[0] - lon) ** 2 + (c[1] - lat) ** 2)
        length = ((cx - lon) ** 2 + (cy - lat) ** 2) ** 0.5
        for i in range(1, steps + 1):
            t = i / steps
            if not self.within_units(lon + (cx - lon) * t, lat + (cy - lat) * t, unit_ids, province_id):
                continue
            # Inside. The margin must hold too: a first touch can be an islet or a sliver of
            # coast with open water behind it, and then the search goes on.
            more = min(margin, length * (1 - t) / 4) / length if length else 0
            point = [round(lon + (cx - lon) * (t + more), 4), round(lat + (cy - lat) * (t + more), 4)]
            if self.within_units(point[0], point[1], unit_ids, province_id):
                return point
        return None

    def unit_at(self, lon, lat, province_id):
        """The lowest unit of a province whose shape contains the point, or None."""
        found = None
        parent = province_id
        while parent:
            child = self.child_at(lon, lat, parent)
            if not child:
                break
            found = parent = child
        return found
