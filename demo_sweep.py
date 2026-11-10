"""Year-long sweep comparison. Usage: python3 demo_sweep.py [http://localhost:8000]
The first run computes ~36 monthly windows (a minute or two); repeat runs are fast."""
import json
import sys
import urllib.request

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"
COMMON = {"start_utc": "2027-01-01T00:00:00", "count": 12, "step_days": 29.53,
          "hours": 720, "step_min": 10}
SCENARIOS = [
    ("Ridge high point (connecting_ridge)", {"site_id": "connecting_ridge"}),
    ("Malapert massif", {"site_id": "malapert"}),
    ("Crater floor (-88.2, 45E)", {"lat": -88.2, "lon": 45.0}),
]

for name, extra in SCENARIOS:
    body = json.dumps({**COMMON, **extra}).encode()
    req = urllib.request.Request(BASE + "/sweep", body, {"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        res = json.load(r)["results"]
    print(f"\n{name}")
    print(f"  {'start':10s} {'sunlit%':>8s} {'dark h':>8s} {'Earth%':>8s}")
    for x in res:
        print(f"  {x['start_utc'][:10]:10s} {x['pct_sunlit']:8.1f} "
              f"{x['longest_darkness_hours']:8.1f} {x['pct_earth_visible']:8.1f}")
    s = [x["pct_sunlit"] for x in res]
    print(f"  sunlit% range over the year: {min(s):.1f} to {max(s):.1f}")
