"""Compare the illumination model with NASA's PSR map at many random polar points.

Needs: SPICE kernels, dem/LDEM_80S_80MPP_ADJ.TIF, dem/LPSR_80S_20MPP_ADJ.TIF.
Usage:  python3 psr_validate.py              (default: 40 points, ~ a few minutes)
        python3 psr_validate.py --n 20 --radius-km 80

For each sampled point it reads the PSR flag (1 = permanently shadowed, assumed from the
file name and the earlier 3-site check), builds a terrain horizon, and runs the Sun model
for several 30-day windows spread over 2027. Report:
  * PSR points the model calls LIT      -> clear contradiction, worth inspecting
  * non-PSR points the model calls DARK -> ambiguous (the PSR map uses many years of
    illumination; this uses a few windows of 2027), reported but not counted as errors
"""
import argparse
from pathlib import Path

import numpy as np
import rasterio

import horizon
import lunar

ROOT = Path(__file__).parent
R = horizon.R
STARTS = ["2027-01-01T00:00:00", "2027-04-29T00:00:00",
          "2027-08-25T00:00:00", "2027-11-21T00:00:00"]


def xy_to_latlon(x, y):
    rho = np.hypot(x, y)
    return np.degrees(2 * np.arctan(rho / (2 * R)) - np.pi / 2), np.degrees(np.arctan2(x, y)) % 360


def psr_flag(ds, x, y, half=100.0):
    half = max(half, abs(ds.transform.a))          # at least one pixel
    win = ds.window(x - half, y - half, x + half, y + half).round_offsets().round_lengths()
    try:
        win = win.intersection(rasterio.windows.Window(0, 0, ds.width, ds.height))
    except rasterio.errors.WindowError:
        return None
    d = ds.read(1, window=win)
    d = d[~np.isnan(d)] if d.dtype.kind == "f" else d.ravel()
    return None if d.size == 0 else float((d != 0).mean())


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40, help="total points (half PSR, half not)")
    ap.add_argument("--radius-km", type=float, default=100.0, help="sample within this distance of the pole")
    ap.add_argument("--candidates", type=int, default=800)
    ap.add_argument("--hours", type=float, default=720)
    ap.add_argument("--step-min", type=float, default=30)
    ap.add_argument("--dark-threshold", type=float, default=0.5, help="pct sunlit below this = dark")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--dem", default=str(ROOT / "dem" / "LDEM_80S_80MPP_ADJ.TIF"))
    ap.add_argument("--psr", default=str(ROOT / "dem" / "LPSR_80S_20MPP_ADJ.TIF"))
    a = ap.parse_args(argv)
    for p in (a.dem, a.psr):
        if not Path(p).exists():
            raise SystemExit(f"File not found: {p}")

    rng = np.random.default_rng(a.seed)
    want = a.n // 2
    psr_pts, lit_pts = [], []
    with rasterio.open(a.psr) as pds:
        for _ in range(a.candidates):
            if len(psr_pts) >= want and len(lit_pts) >= a.n - want:
                break
            r = a.radius_km * 1000 * np.sqrt(rng.random())
            th = 2 * np.pi * rng.random()
            x, y = r * np.sin(th), r * np.cos(th)
            f = psr_flag(pds, x, y)
            if f is None:
                continue
            lat, lon = xy_to_latlon(x, y)
            if f >= 0.5 and len(psr_pts) < want:
                psr_pts.append((float(lat), float(lon)))
            elif f < 0.5 and len(lit_pts) < a.n - want:
                lit_pts.append((float(lat), float(lon)))
    print(f"sampled {len(psr_pts)} PSR points and {len(lit_pts)} non-PSR points "
          f"within {a.radius_km:.0f} km of the pole")
    if not psr_pts or not lit_pts:
        raise SystemExit("could not find both kinds of points; raise --candidates or --radius-km")

    rows = []
    with rasterio.open(a.dem) as dds:
        for is_psr, pts in ((True, psr_pts), (False, lit_pts)):
            for lat, lon in pts:
                mask, h0 = horizon.compute_mask(dds, lat, lon)
                mask = [float(v) for v in mask]
                best = 0.0
                for st in STARTS:
                    ts = lunar.timeseries(lat, lon, 0.0, st, a.hours, a.step_min, mask)
                    best = max(best, lunar.summary(ts)["pct_sunlit"])
                rows.append((is_psr, lat, lon, h0, best))
                print(f"  {'PSR ' if is_psr else 'lit '} lat {lat:8.3f} lon {lon:7.2f} "
                      f"height {h0:8.1f} m  best sunlit% {best:5.1f}", flush=True)

    dark = lambda r: r[4] < a.dark_threshold
    pd_ = sum(1 for r in rows if r[0] and dark(r)); pl = sum(1 for r in rows if r[0] and not dark(r))
    nd = sum(1 for r in rows if not r[0] and dark(r)); nl = sum(1 for r in rows if not r[0] and not dark(r))
    print("\n                    model dark   model lit")
    print(f"PSR points          {pd_:10d}   {pl:9d}")
    print(f"non-PSR points      {nd:10d}   {nl:9d}")
    if pd_ + pl:
        print(f"\nPSR points the model also calls dark: {pd_}/{pd_ + pl} ({100 * pd_ / (pd_ + pl):.0f}%)")
    if nd + nl:
        print(f"non-PSR points with some sunlight:    {nl}/{nd + nl} ({100 * nl / (nd + nl):.0f}%)")
    for r in rows:
        if r[0] and not dark(r):
            print(f"  CONTRADICTION  PSR point lat {r[1]:.3f} lon {r[2]:.2f} gets {r[4]:.1f}% sunlight in the model")
    for r in rows:
        if (not r[0]) and dark(r):
            print(f"  ambiguous      non-PSR point lat {r[1]:.3f} lon {r[2]:.2f} is dark in the sampled windows")
    return rows


if __name__ == "__main__":
    main()
