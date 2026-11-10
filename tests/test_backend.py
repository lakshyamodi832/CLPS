"""Regression tests. Run from the backend folder:  pip install pytest httpx && pytest -q
Tests that need SPICE kernels / the DEM are skipped automatically if those are missing."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import lunar  # noqa: E402

HAVE_KERNELS = all((lunar.KERNEL_DIR / k).exists() for k in lunar.KERNELS)
HAVE_DEM = (ROOT / "dem" / "LDEM_80S_80MPP_ADJ.TIF").exists()
needs_kernels = pytest.mark.skipif(not HAVE_KERNELS, reason="SPICE kernels not found")
needs_dem = pytest.mark.skipif(not HAVE_DEM, reason="LOLA DEM not found")


def load_mask(site):
    p = ROOT / "masks.json"
    if not p.exists():
        pytest.skip("masks.json not found")
    m = json.loads(p.read_text())
    if site not in m:
        pytest.skip(f"no mask for {site}")
    return m[site]


# ---------- pure logic (no kernels needed) ----------
def test_longest_run():
    f = [True, False, False, True, False, False, False, True]
    assert lunar._longest_run(f, False, 0.5) == 1.5
    assert lunar._longest_run(f, True, 0.5) == 0.5
    assert lunar._longest_run([], False, 1.0) == 0
    # fully dark: clamped to the range (4 intervals), not 5 samples x step
    assert lunar._longest_run([False] * 5, False, 1.0) == 4.0  # clamped


def test_horizon_interpolation_wraps_at_north():
    mask = list(range(360))
    assert lunar.horizon_at(np.array([10.0]), mask)[0] == pytest.approx(10.0)
    # halfway between az 359 (value 359) and az 0 (value 0)
    assert lunar.horizon_at(np.array([359.5]), mask)[0] == pytest.approx(179.5)
    assert lunar.horizon_at(np.array([5.0, 6.0]), None).tolist() == [0.0, 0.0]


# ---------- ephemeris regression against JPL Horizons ----------
@needs_kernels
def test_matches_jpl_horizons_apollo11():
    # Horizons, Moon-surface observer 23.473E 0.674N, 2027-03-01 00:00 and 05:00 UTC
    ts = lunar.timeseries(0.674, 23.473, 0.0, "2027-03-01T00:00:00", 5, 60, None)
    ref = {
        0: dict(sun=(271.002129, -27.950112), earth=(285.806287, 69.822076)),
        5: dict(sun=(271.062370, -30.486355), earth=(285.215447, 69.617416)),
    }
    for i, r in ref.items():
        assert ts["sun_az"][i] == pytest.approx(r["sun"][0], abs=0.02)
        assert ts["sun_el"][i] == pytest.approx(r["sun"][1], abs=0.02)
        assert ts["earth_az"][i] == pytest.approx(r["earth"][0], abs=0.02)
        assert ts["earth_el"][i] == pytest.approx(r["earth"][1], abs=0.02)


@needs_kernels
def test_window_edges_are_consistent():
    mask = load_mask("malapert")
    args = (-85.99, 0.12, 0.0)
    ts = lunar.timeseries(*args, "2027-03-01T00:00:00", 720, 10, mask)
    w = lunar.windows(ts, None, (*args, mask))
    # intervals tile the requested range
    assert sum(x["hours"] for x in w["sun"]) == pytest.approx(720, abs=1e-6)
    # at the first computed edge the Sun's upper limb sits on the horizon
    edge = w["sun"][0]["end"]
    lunar.load_kernels()
    import spiceypy as spice
    az, el, rad = lunar.azel("SUN", np.array([spice.str2et(edge)]), *args, lunar.R_SUN)
    assert abs(el[0] + rad[0] - lunar.horizon_at(az, mask)[0]) < 1e-3


@needs_kernels
def test_summary_has_expected_keys_and_ranges():
    ts = lunar.timeseries(0.674, 23.473, 0.0, "2027-03-01T00:00:00", 720, 30, None)
    s = lunar.summary(ts)
    for k in ("pct_sunlit", "pct_earth_visible", "longest_darkness_hours",
              "longest_earth_gap_hours", "mean_vertical_power_factor"):
        assert k in s
    assert 0 <= s["pct_sunlit"] <= 100
    assert 0 <= s["mean_horizontal_power_factor"] <= 1.0
    # equatorial site: roughly half the lunar day is sunlit
    assert 40 < s["pct_sunlit"] < 60


# ---------- terrain masks ----------
@needs_dem
def test_malapert_mask_shape():
    mask = load_mask("malapert")
    assert len(mask) == 360
    assert -4.5 < min(mask) < -3.9      # curvature dip from a ~4.8 km peak


@needs_dem
def test_ridge_horizon_is_below_zero():
    mask = load_mask("connecting_ridge")
    assert max(mask) < 0.5


# ---------- API ----------
@pytest.fixture(scope="module")
def client():
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    import main
    return TestClient(main.app)


def test_api_rejects_bad_input(client):
    r = client.post("/windows", json={"site_id": "malapert", "start_utc": "banana"})
    assert r.status_code == 422
    r = client.post("/windows", json={"site_id": "malapert", "hours": 9600, "step_min": 1})
    assert r.status_code == 422
    r = client.post("/windows", json={"site_id": "nope"})
    assert r.status_code == 404
    r = client.post("/windows", json={"start_utc": "2027-03-01T00:00:00"})
    assert r.status_code == 422
    r = client.post("/compare", json=[{"site_id": "malapert"}] * 13)
    assert r.status_code == 422
    r = client.post("/windows", json={"site_id": "malapert", "start_utc": "3500-01-01T00:00:00"})
    assert r.status_code == 422


def test_api_sites(client):
    r = client.get("/sites")
    assert r.status_code == 200 and len(r.json()) >= 1
    assert "has_terrain" in r.json()[0]


@needs_kernels
def test_api_sweep(client):
    r = client.post("/sweep", json={"site_id": "apollo11", "start_utc": "2027-03-01T00:00:00",
                                     "hours": 48, "step_min": 60, "count": 3, "step_days": 10})
    assert r.status_code == 200
    res = r.json()["results"]
    assert [x["start_utc"][:10] for x in res] == ["2027-03-01", "2027-03-11", "2027-03-21"]
    assert all("pct_sunlit" in x for x in res)
