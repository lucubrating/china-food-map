/**
 * Geometry helpers: decode the compact boundary strings written by scripts/build.py, and project
 * longitude and latitude onto the map's flat coordinate space (Web Mercator).
 */
(function () {
  'use strict';

  const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+-';
  const LOOKUP = new Uint8Array(128);
  for (let i = 0; i < 64; i++) LOOKUP[ALPHABET.charCodeAt(i)] = i;
  const DEG = 180 / Math.PI;

  /** Turn one encoded ring back into [[lon, lat], ...]. Mirrors encode_ring in scripts/build.py. */
  function decodeRing(text, scale) {
    const out = [];
    const n = text.length;
    let i = 0;
    let x = 0;
    let y = 0;
    while (i < n) {
      let b;
      let shift = 0;
      let v = 0;
      do { b = LOOKUP[text.charCodeAt(i++)]; v |= (b & 31) << shift; shift += 5; } while (b >= 32);
      x += (v & 1) ? ~(v >>> 1) : (v >>> 1);
      shift = 0;
      v = 0;
      do { b = LOOKUP[text.charCodeAt(i++)]; v |= (b & 31) << shift; shift += 5; } while (b >= 32);
      y += (v & 1) ? ~(v >>> 1) : (v >>> 1);
      out.push([x / scale, y / scale]);
    }
    return out;
  }

  class Projector {
    /** bounds: {west, east, south, north} in degrees. width: map units across the bounds. */
    constructor(bounds, width) {
      this.bounds = bounds;
      this.width = width;
      this.perDegree = width / (bounds.east - bounds.west);
      this.top = Projector.mercator(bounds.north);
      this.height = (this.top - Projector.mercator(bounds.south)) * DEG * this.perDegree;
    }

    static mercator(lat) {
      return Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
    }

    project(lon, lat) {
      return [
        (lon - this.bounds.west) * this.perDegree,
        (this.top - Projector.mercator(lat)) * DEG * this.perDegree,
      ];
    }

    unproject(x, y) {
      const lon = x / this.perDegree + this.bounds.west;
      const m = this.top - y / (DEG * this.perDegree);
      const lat = (2 * Math.atan(Math.exp(m)) - Math.PI / 2) * DEG;
      return [lon, lat];
    }

    /**
     * SVG path data for one ring, plus its bounding box in map units. Three decimal places keep
     * the full detail of the stored boundaries, which matters at the closest zoom.
     */
    ringPath(ring, box) {
      let d = '';
      for (let i = 0; i < ring.length; i++) {
        const p = this.project(ring[i][0], ring[i][1]);
        d += (i === 0 ? 'M' : 'L') + p[0].toFixed(3) + ' ' + p[1].toFixed(3);
        if (box) {
          if (p[0] < box.x0) box.x0 = p[0];
          if (p[0] > box.x1) box.x1 = p[0];
          if (p[1] < box.y0) box.y0 = p[1];
          if (p[1] > box.y1) box.y1 = p[1];
        }
      }
      return d + 'Z';
    }

    /** SVG path data for a line that does not close, such as a border between two units. */
    linePath(points) {
      let d = '';
      for (let i = 0; i < points.length; i++) {
        const p = this.project(points[i][0], points[i][1]);
        d += (i === 0 ? 'M' : 'L') + p[0].toFixed(3) + ' ' + p[1].toFixed(3);
      }
      return d;
    }
  }

  window.FoodMapGeo = { decodeRing, Projector };
})();
