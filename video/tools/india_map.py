"""Peninsular India outline for the ink-map zoom, as SVG paths in a 900-wide box.

Reads world-atlas countries-50m TopoJSON (npm world-atlas@2.0.2, Natural Earth data) and
writes src/film/india.json. The video frames the peninsula only, south of about 26 N.

    curl -sSfL -o countries-50m.json https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-50m.json
    python video/tools/india_map.py countries-50m.json
"""

import json
import math
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "src" / "film" / "india.json"
CITIES = {"Delhi": (77.21, 28.61), "Mumbai": (72.88, 19.08), "Kolkata": (88.36, 22.57), "Chennai": (80.27, 13.08)}


def main(path: str) -> None:
    topo = json.load(open(path, encoding="utf-8"))
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)

    geoms = topo["objects"]["countries"]["geometries"]
    india = next(g for g in geoms if g.get("properties", {}).get("name") == "India")

    def ring(idxs):
        out = []
        for i in idxs:
            a = arcs[i] if i >= 0 else arcs[~i][::-1]
            out.extend(a if not out else a[1:])
        return out

    polys = india["arcs"] if india["type"] == "MultiPolygon" else [india["arcs"]]
    rings = [r for r in (ring(p[0]) for p in polys) if len(r) > 12]

    lon0, lat0 = 82.0, 22.0
    k = math.cos(math.radians(lat0))

    def proj(lon, lat):
        return (lon - lon0) * k, -(lat - lat0)

    allp = [proj(*p) for r in rings for p in r]
    minx, maxx = min(p[0] for p in allp), max(p[0] for p in allp)
    miny, maxy = min(p[1] for p in allp), max(p[1] for p in allp)
    s = min(900 / (maxx - minx), 1000 / (maxy - miny))

    def xy(lon, lat):
        px, py = proj(lon, lat)
        return round((px - minx) * s, 1), round((py - miny) * s, 1)

    ordered = sorted(rings, key=len, reverse=True)
    paths = ["M" + " L".join(f"{x} {y}" for x, y in (xy(*p) for p in r)) + " Z" for r in ordered]
    OUT.write_text(json.dumps({
        "width": round((maxx - minx) * s, 1), "height": round((maxy - miny) * s, 1), "paths": paths,
        "bengaluru": list(xy(77.5946, 12.9716)), "cities": {n: list(xy(*c)) for n, c in CITIES.items()},
    }), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main(sys.argv[1])
