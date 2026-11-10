"""Warm the cache with the year-long sweeps for the ridge and Malapert at startup.
Run once from the backend folder (needs patch_hardening.py and patch_sweep.py applied)."""
import sys

s = open("main.py").read()
if "WARM_SWEEPS" in s:
    sys.exit("already applied")

old_warm = '''def _warm():
    for sid in list(SITES):
        try:
            q = Query(site_id=sid)
            lat, lon, h, mask = resolve(q)
            lunar.timeseries(lat, lon, h, q.start_utc, q.hours, q.step_min, mask)
        except Exception as e:
            print("warm-up failed for", sid, e)
'''
new_warm = '''WARM_SWEEPS = ("connecting_ridge", "malapert")   # year-long sweeps pre-computed at startup


def _warm():
    for sid in list(SITES):
        try:
            q = Query(site_id=sid)
            lat, lon, h, mask = resolve(q)
            lunar.timeseries(lat, lon, h, q.start_utc, q.hours, q.step_min, mask)
        except Exception as e:
            print("warm-up failed for", sid, e)
    for sid in WARM_SWEEPS:
        if sid in SITES:
            try:   # same parameters as demo_sweep.py, so those requests hit the cache
                sweep(SweepQuery(site_id=sid, start_utc="2027-01-01T00:00:00"))
            except Exception as e:
                print("sweep warm-up failed for", sid, e)
'''
start_line = "threading.Thread(target=_warm, daemon=True).start()\n"
for need in (old_warm, start_line):
    if need not in s:
        sys.exit("main.py: expected warm-up code not found; paste your main.py tail to me")
if "def sweep(" not in s:
    sys.exit("Run patch_sweep.py first")

s = s.replace(old_warm, new_warm, 1)
s = s.replace(start_line, "", 1)                       # start the thread at the END of the file
s = s.rstrip("\n") + "\n\n\nthreading.Thread(target=_warm, daemon=True).start()\n"
open("main.py", "w").write(s)
print("patched main.py")
