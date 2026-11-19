"""Read polygon shapefiles (.shp with its .dbf). Standard library only.

Only what the boundary files of Taiwan's surveying centre need: polygon shapes (type 5) and
text fields. A record comes back as (fields, rings), where `fields` is {name: text} and `rings`
is a list of rings of (lon, lat) pairs, each closed, in the file's own order. In a shapefile an
outer ring runs clockwise and a hole anticlockwise; `polygons` sorts rings into polygons.
"""
import struct


def read_dbf(path, encoding="utf-8"):
    """The rows of a .dbf table: [{field name: text}]."""
    with open(path, "rb") as fh:
        data = fh.read()
    count, header_length, row_length = struct.unpack("<IHH", data[4:12])
    fields, at = [], 32
    while data[at] != 0x0D:
        name = data[at:at + 11].split(b"\0")[0].decode("ascii")
        fields.append((name, data[at + 16]))
        at += 32
    rows = []
    for index in range(count):
        row = data[header_length + index * row_length:header_length + (index + 1) * row_length]
        at, values = 1, {}
        for name, length in fields:
            values[name] = row[at:at + length].decode(encoding).strip()
            at += length
        rows.append(values)
    return rows


def read_shp(path):
    """The rings of each record of a polygon .shp file, in order. An empty shape gives []."""
    with open(path, "rb") as fh:
        data = fh.read()
    if struct.unpack("<i", data[32:36])[0] != 5:
        raise ValueError("%s is not a polygon shapefile" % path)
    shapes, at = [], 100
    while at < len(data):
        length = struct.unpack(">i", data[at + 4:at + 8])[0] * 2
        body = data[at + 8:at + 8 + length]
        at += 8 + length
        if struct.unpack("<i", body[:4])[0] != 5:
            shapes.append([])
            continue
        parts, points = struct.unpack("<ii", body[36:44])
        starts = list(struct.unpack("<%di" % parts, body[44:44 + 4 * parts])) + [points]
        flat = struct.unpack("<%dd" % (2 * points), body[44 + 4 * parts:44 + 4 * parts + 16 * points])
        shapes.append([[(flat[2 * i], flat[2 * i + 1]) for i in range(starts[p], starts[p + 1])]
                       for p in range(parts)])
    return shapes


def read(shp_path, encoding="utf-8"):
    """[(fields, rings)] for a shapefile, given the path of its .shp."""
    rows = read_dbf(shp_path[:-4] + ".dbf", encoding)
    shapes = read_shp(shp_path)
    if len(rows) != len(shapes):
        raise ValueError("%s: %d shapes but %d rows" % (shp_path, len(shapes), len(rows)))
    return list(zip(rows, shapes))


def signed_area(ring):
    """Twice the area is not needed: this is the area itself, negative for a clockwise ring."""
    total = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        total += x1 * y2 - x2 * y1
    return total / 2
