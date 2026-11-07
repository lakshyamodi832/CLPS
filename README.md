# Backend setup

```bash
pip install fastapi uvicorn spiceypy numpy
mkdir kernels && cd kernels
B=https://naif.jpl.nasa.gov/pub/naif/generic_kernels
curl -O $B/lsk/naif0012.tls
curl -O $B/pck/pck00011.tpc
curl -O $B/spk/planets/de440s.bsp
curl -O $B/pck/moon_pa_de440_200625.bpc
curl -O $B/fk/satellites/moon_de440_220930.tf
cd .. && uvicorn main:app --reload
```

Try it:

```bash
curl -X POST localhost:8000/windows -H 'content-type: application/json' \
  -d '{"site_id":"malapert","start_utc":"2027-03-01T00:00:00","hours":720,"step_min":10}'
```

## Notes
- Without a horizon mask, `use_terrain` has no effect (flat horizon at 0°).
  Fill `HORIZON_MASKS[site_id]` with 360 elevation angles from LOLA ray-marching.
- Window edge times are accurate to `step_min`. Refine with bisection on
  `lunar.azel` if you need minute-level precision.
- Validate sun/Earth az/el against JPL Horizons before trusting results.
- `/timeseries` and `/compare` loop over SPICE calls in Python: ~50k points is
  a few seconds. Cache results for catalog sites.
