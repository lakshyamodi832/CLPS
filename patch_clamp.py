"""Clamp longest-run metrics to the requested range (fixes the 720.2 h artifact)."""
import sys

s = open("lunar.py").read()
old = "    return best * step_h\n"
new = "    return min(best * step_h, max(len(flag) - 1, 0) * step_h)   # cannot exceed the range\n"
if new in s:
    print("lunar.py already patched")
elif old in s:
    open("lunar.py", "w").write(s.replace(old, new, 1)); print("patched lunar.py")
else:
    sys.exit("lunar.py: _longest_run return line not found (run patch_hardening.py first)")

try:
    t = open("tests/test_backend.py").read()
    if "clamped" not in t:
        t = t.replace("    assert lunar._longest_run([], False, 1.0) == 0\n",
                      "    assert lunar._longest_run([], False, 1.0) == 0\n"
                      "    # fully dark: clamped to the range (4 intervals), not 5 samples x step\n"
                      "    assert lunar._longest_run([False] * 5, False, 1.0) == 4.0  # clamped\n", 1)
        open("tests/test_backend.py", "w").write(t); print("patched tests/test_backend.py")
except FileNotFoundError:
    pass
