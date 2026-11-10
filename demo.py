"""Side-by-side demo comparison. Usage: python3 demo.py [http://localhost:8000]"""
import json
import sys
import urllib.request

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"
COMMON = {"hours": 720, "step_min": 10}
SCENARIOS = [
    ("Ridge high point, Mar 2027",   {"site_id": "connecting_ridge", "start_utc": "2027-03-01T00:00:00"}),
    ("Malapert massif, Mar 2027",    {"site_id": "malapert",         "start_utc": "2027-03-01T00:00:00"}),
    ("Crater floor -88.2/45, Mar",   {"lat": -88.2, "lon": 45.0,     "start_utc": "2027-03-01T00:00:00"}),
    ("Malapert massif, Jun 2027",    {"site_id": "malapert",         "start_utc": "2027-06-01T00:00:00"}),
]

body = json.dumps([{**COMMON, **q} for _, q in SCENARIOS]).encode()
req = urllib.request.Request(BASE + "/compare", body, {"content-type": "application/json"})
with urllib.request.urlopen(req, timeout=300) as r:
    rows = json.load(r)

print(f"{'Scenario':32s} {'Sunlit%':>8s} {'Earth%':>8s} {'VertPwr':>8s} {'PanelAz':>8s}")
for (name, _), s in zip(SCENARIOS, rows):
    print(f"{name:32s} {s['pct_sunlit']:8.1f} {s['pct_earth_visible']:8.1f} "
          f"{s['mean_vertical_power_factor']:8.3f} {s['best_vertical_panel_azimuth_deg']:8d}")
