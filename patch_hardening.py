"""Adds: longest darkness / Earth-gap metrics, input validation, lower-memory DEM read.
Run once from the backend folder:  python3 patch_hardening.py
Safe to re-run (it skips what is already applied) and stops with a message if a
pattern is missing."""
import sys

def patch(path, fn):
    s = open(path).read()
    new = fn(s)
    if new != s:
        open(path, "w").write(new)
        print("patched", path)
    else:
        print("no change", path)

# ---------------- lunar.py: longest-run metrics ----------------
def lunar_patch(s):
    if "longest_darkness_hours" in s:
        return s
    helper = '''def _longest_run(flag, value, step_h):
    """Longest continuous stretch (hours) where flag == value, within the range."""
    best = cur = 0
    for f in flag:
        if bool(f) == value:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best * step_h


'''
    i = s.index("def summary(")
    s = s[:i] + helper + s[i:]
    for anchor in ('    return {\n        "mean_vertical_power_factor"',
                   '    return {\n        "pct_sunlit"'):
        if anchor in s:
            first_key = anchor.split("\n")[1].strip()
            repl = ('    step_h = float(ts["et"][1] - ts["et"][0]) / 3600 if len(ts["et"]) > 1 else 0.0\n'
                    '    return {\n'
                    '        "longest_darkness_hours": float(_longest_run(up_s, False, step_h)),\n'
                    '        "longest_earth_gap_hours": float(_longest_run(up_e, False, step_h)),\n'
                    '        ' + first_key)
            return s.replace(anchor, repl, 1)
    sys.exit("lunar.py: could not find the summary() return statement")

# ---------------- main.py: validation ----------------
VALIDATION = '''from datetime import datetime
from fastapi.responses import JSONResponse
from spiceypy.utils.exceptions import SpiceyError

MAX_POINTS = 60000
MAX_SCENARIOS = 12


@app.exception_handler(SpiceyError)
async def _spice_error(request, exc):
    return JSONResponse(status_code=422, content={
        "detail": "Ephemeris computation failed for these inputs "
                  "(check dates are between 1850 and 2149 and coordinates are valid)."})


def _check_time(t, name):
    try:
        d = datetime.fromisoformat(t.strip().replace("Z", ""))
    except ValueError:
        raise HTTPException(422, f"{name} must be ISO format like 2027-03-01T00:00:00 (UTC)")
    if not 1850 <= d.year <= 2149:
        raise HTTPException(422, f"{name} must be between 1850 and 2149 (ephemeris coverage)")


def validate(q):
    _check_time(q.start_utc, "start_utc")
    if q.now_utc:
        _check_time(q.now_utc, "now_utc")
    pts = q.hours * 60 / q.step_min
    if pts > MAX_POINTS:
        raise HTTPException(422, f"too many samples ({int(pts)}, max {MAX_POINTS}): "
                                 "increase step_min or reduce hours")


'''

def main_patch(s):
    if "def validate(" in s:
        return s
    a = "def resolve(q: Query):\n"
    if a not in s:
        sys.exit("main.py: resolve() not found")
    s = s.replace(a, VALIDATION + a + "    validate(q)\n", 1)
    b = "def compare(queries: List[Query]):\n"
    if b not in s:
        sys.exit("main.py: compare() not found")
    s = s.replace(b, b + '    if len(queries) > MAX_SCENARIOS:\n'
                  '        raise HTTPException(422, f"max {MAX_SCENARIOS} scenarios per request")\n', 1)
    return s

# ---------------- horizon.py: half the memory for custom masks ----------------
def horizon_patch(s):
    return s.replace('.astype("float64")', '.astype("float32")')

patch("lunar.py", lunar_patch)
patch("main.py", main_patch)
patch("horizon.py", horizon_patch)
