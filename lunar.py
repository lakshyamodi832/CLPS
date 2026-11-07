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


def timeseries(lat, lon, height_km, start_utc, hours, step_min, mask=None):
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


def _intervals(et, flag):
    """Return list of (start_et, end_et, state) with linear-step edge times."""
    out, start = [], 0
    for i in range(1, len(flag)):
        if flag[i] != flag[i - 1]:
            out.append((et[start], et[i], bool(flag[i - 1])))
            start = i
    out.append((et[start], et[-1], bool(flag[-1])))
    return out


def windows(ts, now_utc=None):
    """Contiguous up/down intervals and time until next change for each body."""
    res = {}
    now = spice.str2et(now_utc) if now_utc else ts["et"][0]
    for name, key in (("sun", "sun_up"), ("earth", "earth_up")):
        iv = _intervals(ts["et"], ts[key])
        res[name] = [
            {"start": spice.et2utc(a, "ISOC", 0), "end": spice.et2utc(b, "ISOC", 0),
             "visible": s, "hours": (b - a) / 3600} for a, b, s in iv
        ]
        cur = next((x for x in iv if x[0] <= now <= x[1]), iv[-1])
        res[name + "_now"] = {
            "visible": cur[2],
            "hours_until_change": (cur[1] - now) / 3600,
            "open_ended": bool(cur[1] >= ts["et"][-1]),  # extend range if True
        }
    return res


def summary(ts):
    up_s, up_e = ts["sun_up"], ts["earth_up"]
    el = np.where(up_s, ts["sun_el"], 0.0)
    return {
        "pct_sunlit": float(up_s.mean() * 100),
        "pct_earth_visible": float(up_e.mean() * 100),
        "max_sun_el_deg": float(ts["sun_el"].max()),
        "mean_sun_el_when_lit_deg": float(ts["sun_el"][up_s].mean()) if up_s.any() else 0.0,
        # cosine factor for a horizontal panel
        "mean_horizontal_power_factor": float(np.cos(np.radians(90 - el)).mean()),
    }
