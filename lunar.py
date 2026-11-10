"""Sun/Earth az/el at a lunar site using SpiceyPy (NAIF SPICE)."""
from pathlib import Path
import numpy as np
import spiceypy as spice

KERNEL_DIR = Path(__file__).parent / "kernels"
KERNELS = [
    "naif0012.tls",                 # leap seconds
    "pck00011.tpc",                 # body radii
    "de440s.bsp",                   # planetary ephemeris
    "moon_pa_de440_200625.bpc",     # lunar orientation (libration)
    "moon_de440_250416.tf",         # defines MOON_ME frame
]
R_MOON = 1737.4      # km, LOLA reference sphere
R_SUN = 695700.0     # km
R_EARTH = 6378.137   # km
_loaded = False


def load_kernels():
    global _loaded
    if _loaded:
        return
    for k in KERNELS:
        spice.furnsh(str(KERNEL_DIR / k))
    _loaded = True


def enu_basis(lat_deg, lon_deg):
    lat, lon = np.radians(lat_deg), np.radians(lon_deg)
    e = np.array([-np.sin(lon), np.cos(lon), 0.0])
    n = np.array([-np.sin(lat) * np.cos(lon), -np.sin(lat) * np.sin(lon), np.cos(lat)])
    u = np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])
    return e, n, u


def site_vector(lat_deg, lon_deg, height_km=0.0):
    _, _, u = enu_basis(lat_deg, lon_deg)
    return u * (R_MOON + height_km)


def azel(body, et, lat, lon, height_km, body_radius):
    """Return (az_deg, el_center_deg, angular_radius_deg) arrays for `body`."""
    e, n, u = enu_basis(lat, lon)
    obs = site_vector(lat, lon, height_km)
    az = np.empty(len(et)); el = np.empty(len(et)); rad = np.empty(len(et))
    for i, t in enumerate(et):
        state, _ = spice.spkcpo(body, t, "MOON_ME_DE440_ME421", "OBSERVER", "LT+S",
                                obs, "MOON", "MOON_ME_DE440_ME421")
        r = state[:3]
        d = np.linalg.norm(r)
        az[i] = np.degrees(np.arctan2(r @ e, r @ n)) % 360
        el[i] = np.degrees(np.arcsin(r @ u / d))
        rad[i] = np.degrees(np.arcsin(body_radius / d))
    return az, el, rad


def horizon_at(az_deg, mask):
    """mask: 360 values (deg elevation, index = azimuth deg). Periodic interp."""
    if mask is None:
        return np.zeros_like(az_deg)
    m = np.asarray(mask, float)
    xp = np.arange(-1, 361)
    fp = np.concatenate([[m[-1]], m, [m[0]]])
    return np.interp(az_deg, xp, fp)


def _timeseries_uncached(lat, lon, height_km, start_utc, hours, step_min, mask=None):
    load_kernels()
    et0 = spice.str2et(start_utc)
    et = et0 + np.arange(0, hours * 3600 + 1, step_min * 60.0)
    s_az, s_el, s_r = azel("SUN", et, lat, lon, height_km, R_SUN)
    e_az, e_el, e_r = azel("EARTH", et, lat, lon, height_km, R_EARTH)
    # Visible when upper limb clears the terrain horizon (no atmosphere)
    sun_up = (s_el + s_r) > horizon_at(s_az, mask)
    earth_up = (e_el + e_r) > horizon_at(e_az, mask)
    return {
        "et": et, "sun_az": s_az, "sun_el": s_el, "sun_up": sun_up,
        "earth_az": e_az, "earth_el": e_el, "earth_up": earth_up,
    }


import threading
_LOCK = threading.RLock()   # CSPICE is not thread-safe: serialise all SPICE calls
_CACHE = {}
_CACHE_MAX = 128


def timeseries(lat, lon, height_km, start_utc, hours, step_min, mask=None):
    key = (round(lat, 5), round(lon, 5), height_km, start_utc, hours, step_min,
           None if mask is None else hash(tuple(mask)))
    with _LOCK:
        if key in _CACHE:
            return _CACHE[key]
        ts = _timeseries_uncached(lat, lon, height_km, start_utc, hours, step_min, mask)
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = ts
        return ts


def _intervals(et, flag):
    """Return list of (start_et, end_et, state) with linear-step edge times."""
    out, start = [], 0
    for i in range(1, len(flag)):
        if flag[i] != flag[i - 1]:
            out.append((et[start], et[i], bool(flag[i - 1])))
            start = i
    out.append((et[start], et[-1], bool(flag[-1])))
    return out


def _refine(body, radius, et, flag, site):
    """Edge times (ET) where visibility flips, refined by bisection when a site is given."""
    edges = []
    for i in range(1, len(flag)):
        if flag[i] == flag[i - 1]:
            continue
        if site is None:
            edges.append(float(et[i]))
            continue
        lat, lon, h, mask = site
        lo, hi = float(et[i - 1]), float(et[i])
        for _ in range(14):                      # 600 s / 2^14 -> ~0.04 s
            mid = 0.5 * (lo + hi)
            az, el, rad = azel(body, np.array([mid]), lat, lon, h, radius)
            vis = bool((el[0] + rad[0]) > horizon_at(az, mask)[0])
            if vis == bool(flag[i - 1]):
                lo = mid
            else:
                hi = mid
        edges.append(0.5 * (lo + hi))
    return edges


def windows(ts, now_utc=None, site=None):
    """Up/down intervals and time until next change. site=(lat, lon, h_km, mask)
    enables second-level edge refinement."""
    res = {}
    et = ts["et"]
    with _LOCK:
        now = spice.str2et(now_utc) if now_utc else float(et[0])
        for name, key, body, radius in (("sun", "sun_up", "SUN", R_SUN),
                                        ("earth", "earth_up", "EARTH", R_EARTH)):
            flag = ts[key]
            bounds = [float(et[0])] + _refine(body, radius, et, flag, site) + [float(et[-1])]
            state = bool(flag[0])
            ivs = []
            for a, b in zip(bounds[:-1], bounds[1:]):
                ivs.append((a, b, state))
                state = not state
            res[name] = [
                {"start": spice.et2utc(a, "ISOC", 0), "end": spice.et2utc(b, "ISOC", 0),
                 "visible": v, "hours": (b - a) / 3600} for a, b, v in ivs
            ]
            cur = next((x for x in ivs if x[0] <= now <= x[1]), ivs[-1])
            res[name + "_now"] = {
                "visible": cur[2],
                "hours_until_change": float((cur[1] - now) / 3600),
                "open_ended": bool(cur[1] >= et[-1]),
            }
    return res


def _longest_run(flag, value, step_h):
    """Longest continuous stretch (hours) where flag == value, within the range."""
    best = cur = 0
    for f in flag:
        if bool(f) == value:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return min(best * step_h, max(len(flag) - 1, 0) * step_h)   # cannot exceed the range


def summary(ts):
    up_s, up_e = ts["sun_up"], ts["earth_up"]
    el = np.where(up_s, np.clip(ts["sun_el"], 0.0, None), 0.0)
    # vertical panel, best fixed azimuth (10 degree steps)
    A = np.radians(np.arange(0, 360, 10))[:, None]
    saz = np.radians(ts["sun_az"])[None, :]
    cel = np.cos(np.radians(ts["sun_el"]))[None, :]
    f = np.where(up_s[None, :], np.clip(cel * np.cos(saz - A), 0.0, None), 0.0)
    vm = f.mean(axis=1); vi = int(vm.argmax())
    step_h = float(ts["et"][1] - ts["et"][0]) / 3600 if len(ts["et"]) > 1 else 0.0
    return {
        "longest_darkness_hours": float(_longest_run(up_s, False, step_h)),
        "longest_earth_gap_hours": float(_longest_run(up_e, False, step_h)),
        "mean_vertical_power_factor": float(vm[vi]),
        "best_vertical_panel_azimuth_deg": int(vi * 10),
        "pct_sunlit": float(up_s.mean() * 100),
        "pct_earth_visible": float(up_e.mean() * 100),
        "max_sun_el_deg": float(ts["sun_el"].max()),
        "mean_sun_el_when_lit_deg": float(ts["sun_el"][up_s].mean()) if up_s.any() else 0.0,
        # cosine factor for a horizontal panel
        "mean_horizontal_power_factor": float(np.cos(np.radians(90 - el)).mean()),
    }
