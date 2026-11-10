"""Updates the site catalog with sourced coordinates and a `source` field (shown by /sites).
Run once from the backend folder. malapert and connecting_ridge keep their coordinates,
so the existing masks.json stays valid."""
import re
import sys

NEW = '''SITES = {
    "apollo11": {"name": "Apollo 11 (Lunar Module)", "lat": 0.67416, "lon": 23.47314, "height_km": 0.0,
                 "source": "NASA NSSDCA Apollo landing site coordinates (LROC-based, Wagner et al. 2017)"},
    "apollo15": {"name": "Apollo 15 (Lunar Module)", "lat": 26.13239, "lon": 3.63330, "height_km": 0.0,
                 "source": "LROC 2016 coordinates of human features (Wagner et al.)"},
    "apollo17": {"name": "Apollo 17 (Lunar Module)", "lat": 20.19080, "lon": 30.77168, "height_km": 0.0,
                 "source": "NASA NSSDC lunar sites table (Davies and Colvin 2000)"},
    "malapert": {"name": "Malapert massif high point (not an official landing site)",
                 "lat": -85.99, "lon": 0.12, "height_km": 0.0,
                 "source": "Inside the IAU feature Mons Malapert; near the LROC Malapert mosaic centre (-86.0, 0.3); "
                           "about 4.8 km high in the 80 m LOLA DEM"},
    "connecting_ridge": {"name": "Connecting Ridge high point (DEM-derived, not an official site)",
                         "lat": -89.44, "lon": 222.9, "height_km": 0.0,
                         "source": "Highest ground near Shackleton in the 80 m LOLA DEM; about 0.3 km from site 001 "
                                   "(-89.45, 222.69) in Planet. Sci. J. 2022, doi:10.3847/PSJ/aca590"},
}
'''

s = open("main.py").read()
m = re.search(r"SITES = \{\n.*?\n\}\n", s, re.S)
if not m:
    sys.exit("main.py: SITES block not found")
if '"source"' in m.group(0):
    print("main.py already has sources")
else:
    open("main.py", "w").write(s[:m.start()] + NEW + s[m.end():])
    print("patched main.py")

try:
    r = open("README.md").read()
    old = ("- Catalog coordinates are approximate, and `connecting_ridge` is a DEM-derived\n"
           "  high point, not an official landing site. Verify before citing.\n")
    new = ("- Catalog sources are in the `source` field of `/sites`. `malapert` and `connecting_ridge`\n"
           "  are DEM-derived high points near those features, not official landing sites.\n")
    if old in r:
        open("README.md", "w").write(r.replace(old, new)); print("patched README.md")
except FileNotFoundError:
    pass
