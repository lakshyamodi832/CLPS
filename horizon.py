"""Compute 360-point terrain horizon masks from the LOLA south-pole DEM.

Usage (from the backend folder, venv active):
    python3 horizon.py --info                       # check the DEM and projection
    python3 horizon.py                              # all catalog sites south of 80S
    python3 horizon.py --id mysite --lat -88.2 --lon 45   # add one custom site
Writes masks.json: {site_id: [elevation_deg for azimuth 0..359]}.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

R = 1737400.0  # m, LOLA reference sphere (heights in the DEM are relative to it)
HERE = Path(__file__).parent
DEM = HERE / "dem" / "LDEM_80S_80MPP_ADJ.TIF"
OUT = HERE / "masks.json"


def project(lat_deg, lon_deg):
    """Moon south polar stereographic (scale 1 at the pole), x/y in metres.
    Gives rho = 304 km at 80S, matching the DEM's +/-304 km extent."""
    phi, lam = np.radians(lat_deg), np.radians(lon_deg)
    rho = 2 * R * np.tan(np.pi / 4 + phi / 2)
    return rho * np.sin(lam), rho * np.cos(lam)


def compute_mask(ds, lat, lon, mast_m=0.0, max_km=200.0):
    """Max terrain elevation angle (deg) for azimuth 0..359 (clockwise from north)."""
    px = abs(ds.transform.a)
    x0, y0 = project(lat, lon)
    reach = max_km * 1000 + 2 * px
    win = ds.window(x0 - reach, y0 - reach, x0 + reach, y0 + reach)
    win = win.round_offsets().round_lengths()
    win = win.intersection(Window(0, 0, ds.width, ds.height))
    data = ds.read(1, window=win).astype("float32")
    if ds.nodata is not None:
        data[data == ds.nodata] = np.nan
    inv = ~ds.window_transform(win)

    def sample(lat_a, lon_a):
        x, y = project(lat_a, lon_a)
        c, r = inv * (x, y)
        ci, ri = np.floor(c).astype(int), np.floor(r).astype(int)
        ok = (ci >= 0) & (ci < data.shape[1]) & (ri >= 0) & (ri < data.shape[0])
        out = np.full(ci.shape, np.nan)
        out[ok] = data[ri[ok], ci[ok]]
        return out

    h0 = float(sample(np.array([lat]), np.array([lon]))[0])
    if np.isnan(h0):
        h0 = 0.0
    h0 += mast_m

    d = np.arange(px, max_km * 1000, px)                 # distances along each ray
    az = np.radians(np.arange(360))[:, None]
    th = (d / R)[None, :]                                # central angles
    la1, lo1 = np.radians(lat), np.radians(lon)
    la2 = np.arcsin(np.sin(la1) * np.cos(th) + np.cos(la1) * np.sin(th) * np.cos(az))
    lo2 = lo1 + np.arctan2(np.sin(az) * np.sin(th) * np.cos(la1),
                           np.cos(th) - np.sin(la1) * np.sin(la2))
    hs = sample(np.degrees(la2), np.degrees(lo2))        # terrain height along rays
    rt = R + hs
    # elevation of each terrain sample as seen from the site (includes curvature)
    elev = np.degrees(np.arctan2(rt * np.cos(th) - (R + h0), rt * np.sin(th)))
    mask = np.where(np.isnan(elev), -90.0, elev).max(axis=1)
    mask[mask <= -90.0] = 0.0
    return mask, h0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--info", action="store_true")
    ap.add_argument("--id")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--mast", type=float, default=0.0, help="antenna/panel height, m")
    ap.add_argument("--max-km", type=float, default=200.0)
    a = ap.parse_args()

    if not DEM.exists():
        raise SystemExit(f"DEM not found: {DEM}\nDownload it first (see instructions).")

    with rasterio.open(DEM) as ds:
        if a.info:
            print("size:", ds.width, "x", ds.height, " pixel:", ds.transform.a, "m")
            print("bounds:", ds.bounds, " dtype:", ds.dtypes[0], " nodata:", ds.nodata)
            print("CRS:", ds.crs.to_string() if ds.crs else None)
            print("Expect bounds ~ +/-304000 m and pixel 80 m.")
            from main import SITES
            for sid, s in SITES.items():
                if s["lat"] <= -80:
                    x, y = project(s["lat"], s["lon"])
                    v = next(ds.sample([(float(x), float(y))]))[0]
                    print(f"{sid:16s} lat {s['lat']:8.3f} lon {s['lon']:8.3f} DEM height {v:9.1f} m")
            return

        if a.id:
            if a.lat is None or a.lon is None:
                raise SystemExit("--id needs --lat and --lon")
            sites = {a.id: {"lat": a.lat, "lon": a.lon}}
        else:
            from main import SITES
            sites = SITES

        masks = json.loads(OUT.read_text()) if OUT.exists() else {}
        for sid, s in sites.items():
            if s["lat"] > -80:
                print(f"skip {sid}: north of 80S, outside this DEM (flat horizon used)")
                continue
            m, h0 = compute_mask(ds, s["lat"], s["lon"], a.mast, a.max_km)
            masks[sid] = [round(float(v), 3) for v in m]
            print(f"{sid:16s} site height {h0:8.1f} m | horizon min {m.min():6.2f} "
                  f"max {m.max():6.2f} deg at az {int(m.argmax())}")
        OUT.write_text(json.dumps(masks))
        print("wrote", OUT)


if __name__ == "__main__":
    main()
