"""Adds `has_terrain` to /sites and updates README.md with validation results,
the new metrics and the /sweep request format. Run once from the backend folder."""
import sys

# ---------- main.py: has_terrain ----------
s = open("main.py").read()
old = 'return [{"id": k, **v} for k, v in SITES.items()]'
new = 'return [{"id": k, **v, "has_terrain": k in HORIZON_MASKS} for k, v in SITES.items()]'
if "has_terrain" in s:
    print("main.py already patched")
elif old in s:
    open("main.py", "w").write(s.replace(old, new, 1)); print("patched main.py")
else:
    sys.exit("main.py: sites() return line not found")

# ---------- tests ----------
try:
    t = open("tests/test_backend.py").read()
    o = "    assert r.status_code == 200 and len(r.json()) >= 1\n"
    if o in t and "has_terrain" not in t:
        t = t.replace(o, o + '    assert "has_terrain" in r.json()[0]\n', 1)
        open("tests/test_backend.py", "w").write(t); print("patched tests")
except FileNotFoundError:
    pass

# ---------- README ----------
r = open("README.md").read()
if "PSR cross-check" in r:
    sys.exit("README already updated")

VALIDATION = '''## Validation
- **Ephemeris vs JPL Horizons.** Sun and Earth azimuth/elevation at Apollo 11
  (23.473E, 0.674N), 2027-03-01 00:00 to 05:00 UTC, agree with Horizons to about 0.005 degrees.
- **Window edges.** At a computed sunset the Sun's upper limb is within 1e-5 degrees of the
  terrain horizon (bisection refinement, edges accurate to seconds).
- **PSR cross-check.** Against NASA's LOLA permanently-shadowed-region map (20 m), using
  random points within 100 km of the south pole in two independent samples (seeds 1 and 2):
  all 60 PSR points receive 0% sunlight in the model, and 59 of 60 non-PSR points receive
  some. The exception lies on a PSR boundary (its 2 km neighbourhood is 18% PSR). Run
  `python3 psr_validate.py`. Caveats: the PSR encoding (1 = shadowed) is inferred, the model
  uses four 30-day windows of 2027 while the PSR map reflects many years, and the check tests
  Sun direction plus terrain, not exact sunlit percentages.
- **Regression tests.** `pytest -q` (Horizons values, window consistency, terrain masks, API).

'''
a = r.find("## Validation")
b = r.find("## Limitations")
if a == -1 or b == -1 or b < a:
    sys.exit("README: Validation/Limitations headings not found")
r = r[:a] + VALIDATION + r[b:]

anchor = "- `use_terrain: false` is a **flat 0-degree horizon baseline**"
extra = ("- `longest_darkness_hours`, `longest_earth_gap_hours`: longest continuous stretch with the Sun /\n"
         "  Earth hidden, **within the requested range** (use at least ~720 h to cover a lunar day).\n")
if anchor in r:
    r = r.replace(anchor, extra + anchor, 1)

anchor2 = "mask computed on the fly and cached.\n"
sweep = ("\n`POST /sweep` takes the same fields plus `count` (default 12) and `step_days` (default 29.53) and\n"
         "returns one summary per start date, e.g.\n"
         '`{"site_id":"connecting_ridge","start_utc":"2027-01-01T00:00:00","count":12}`.\n'
         "`GET /sites` includes `has_terrain` (true if a precomputed terrain mask exists) and a `source`\n"
         "for each coordinate. Points north of 80S have no terrain data and use a flat horizon.\n")
if anchor2 in r:
    r = r.replace(anchor2, anchor2 + sweep, 1)
open("README.md", "w").write(r); print("patched README.md")
