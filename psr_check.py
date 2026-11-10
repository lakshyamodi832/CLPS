"""Compare sites against NASA's permanently-shadowed-region (PSR) map.
Download first (148 MB):
  curl -L -C - -o dem/LPSR_80S_20MPP_ADJ.TIF https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LPSR_80S_20MPP_ADJ.TIF
Then:  python3 psr_check.py            (built-in sites)
       python3 psr_check.py --lat -88.5 --lon 100      (any point)
It prints the raw values found near each point so you can see how the file encodes PSRs."""
import argparse
from pathlib import Path

import numpy as np
import rasterio

from horizon import project

DEFAULT = Path(__file__).parent / "dem" / "LPSR_80S_20MPP_ADJ.TIF"
POINTS = {
    "connecting_ridge": (-89.44, 222.9),
    "malapert": (-85.99, 0.12),
    "crater floor": (-88.2, 45.0),
}

ap = argparse.ArgumentParser()
ap.add_argument("--file", default=str(DEFAULT))
ap.add_argument("--lat", type=float)
ap.add_argument("--lon", type=float)
ap.add_argument("--radius", type=float, default=500.0, help="metres around the point")
a = ap.parse_args()
if not Path(a.file).exists():
    raise SystemExit(f"File not found: {a.file}\nSee the download command at the top of this script.")

pts = {"custom": (a.lat, a.lon)} if a.lat is not None and a.lon is not None else POINTS
with rasterio.open(a.file) as ds:
    print(f"size {ds.width}x{ds.height}  pixel {ds.transform.a} m  dtype {ds.dtypes[0]}  nodata {ds.nodata}")
    print(f"bounds {ds.bounds}")
    if abs(abs(ds.bounds.left) - 304000) > 1000:
        print("WARNING: bounds are not +/-304 km, so the projection assumed by project() may not match")
    for name, (lat, lon) in pts.items():
        x, y = project(lat, lon)
        x, y = float(x), float(y)
        r = a.radius
        try:
            win = ds.window(x - r, y - r, x + r, y + r).round_offsets().round_lengths()
            win = win.intersection(rasterio.windows.Window(0, 0, ds.width, ds.height))
            d = ds.read(1, window=win)
            centre = next(ds.sample([(x, y)]))[0]
        except Exception as e:
            print(f"{name:18s} lat {lat:8.3f} lon {lon:8.3f}  could not read: {e}")
            continue
        vals, counts = np.unique(d, return_counts=True)
        show = ", ".join(f"{v}:{c}" for v, c in list(zip(vals, counts))[:8])
        frac = float((d != 0).mean() * 100)
        print(f"{name:18s} lat {lat:8.3f} lon {lon:8.3f}  centre={centre}  "
              f"nonzero in {a.radius:.0f} m box: {frac:5.1f}%  values {{{show}}}")
