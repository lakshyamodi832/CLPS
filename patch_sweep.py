"""Adds POST /sweep to main.py (run once from the backend folder, after patch_hardening.py)."""
import sys

SWEEP = r'''

# ---- /sweep: one site, many start dates (how conditions change across lunar days) ----
from datetime import timedelta, timezone

MAX_SWEEP_POINTS = 200000


class SweepQuery(Query):
    count: int = Field(12, ge=1, le=24)           # number of start dates
    step_days: float = Field(29.53, gt=0, le=400)  # spacing between start dates


@app.post("/sweep")
def sweep(q: SweepQuery):
    validate(q)
    lat, lon, h, mask = resolve(q)
    pts = q.hours * 60 / q.step_min
    if pts * q.count > MAX_SWEEP_POINTS:
        raise HTTPException(422, f"sweep too large ({int(pts * q.count)} samples, "
                                 f"max {MAX_SWEEP_POINTS}): reduce count/hours or raise step_min")
    t0 = datetime.fromisoformat(q.start_utc.strip().replace("Z", ""))
    if t0.tzinfo:
        t0 = t0.astimezone(timezone.utc).replace(tzinfo=None)
    results = []
    for i in range(q.count):
        start = (t0 + timedelta(days=q.step_days * i)).isoformat(timespec="seconds")
        _check_time(start, "sweep start date")
        ts = lunar.timeseries(lat, lon, h, start, q.hours, q.step_min,
                              mask if q.use_terrain else None)
        results.append({"start_utc": start, **lunar.summary(ts)})
    return {"site_id": q.site_id, "lat": lat, "lon": lon, "results": results}
'''

s = open("main.py").read()
if "def sweep(" in s:
    print("main.py already has /sweep")
else:
    if "def validate(" not in s:
        sys.exit("Run patch_hardening.py first (validate() is missing).")
    open("main.py", "w").write(s + SWEEP)
    print("patched main.py")

try:
    r = open("README.md").read()
    if "/sweep" not in r:
        row = "| `POST /sweep` | One site over many start dates (`count`, `step_days`, default 12 x 29.53 d) |\n"
        key = "| `POST /compare`"
        i = r.find(key)
        if i != -1:
            j = r.index("\n", i) + 1
            open("README.md", "w").write(r[:j] + row + r[j:])
            print("patched README.md")
except FileNotFoundError:
    pass
