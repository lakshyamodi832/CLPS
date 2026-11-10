# Lunar Landing Site Navigator: backend

FastAPI service that returns Sun and Earth azimuth/elevation at a lunar site,
filtered by the real terrain horizon, plus sunlit/Earth-visible windows and
power and communication metrics.

## Data sources
- **Ephemeris:** NASA NAIF SPICE (SpiceyPy), DE440 planetary ephemeris, lunar
  orientation/libration kernels, frame `MOON_ME_DE440_ME421`, light-time and
  stellar-aberration corrections (`LT+S`).
- **Terrain:** LOLA south-polar DEM `LDEM_80S_80MPP_ADJ` (80 m/pixel, 80S to the
  pole), Barker et al. 2023, hosted by NASA PGDA.

## Setup (macOS)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

mkdir -p kernels && cd kernels
B=https://naif.jpl.nasa.gov/pub/naif/generic_kernels
curl -O $B/lsk/naif0012.tls
curl -O $B/pck/pck00011.tpc
curl -O $B/spk/planets/de440s.bsp
curl -O $B/pck/moon_pa_de440_200625.bpc
curl -O $B/fk/satellites/moon_de440_250416.tf
cd ..

mkdir -p dem && cd dem
curl -L -C - -O https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_80MPP_ADJ.TIF
cd ..

python3 horizon.py            # writes masks.json for catalog sites south of 80S
uvicorn main:app --reload --port 8000
```
Interactive API docs: `http://localhost:8000/docs`. Check each downloaded kernel is
not a tiny HTML "404" page (`ls -lh kernels`).

## Endpoints
| Endpoint | Purpose |
|---|---|
| `GET /sites` | Site catalog |
| `POST /timeseries` | Sun/Earth az/el and visibility flags over a time range |
| `POST /windows` | Up/down intervals (edges refined to about 1 s) and time until next change |
| `POST /compare` | List of scenarios in, summary metrics out |
| `POST /sweep` | One site over many start dates (`count`, `step_days`, default 12 x 29.53 d) |
| `GET /horizon/{site_id}`, `GET /horizon?lat=&lon=` | 360 horizon elevations (index = azimuth deg, 0 = north, clockwise) |

Request body: `site_id` or `lat`/`lon`, `start_utc`, `hours`, `step_min`,
optional `now_utc`, `use_terrain`. Custom `lat`/`lon` south of 80S get a terrain
mask computed on the fly and cached.

`POST /sweep` takes the same fields plus `count` (default 12) and `step_days` (default 29.53) and
returns one summary per start date, e.g.
`{"site_id":"connecting_ridge","start_utc":"2027-01-01T00:00:00","count":12}`.
`GET /sites` includes `has_terrain` (true if a precomputed terrain mask exists) and a `source`
for each coordinate. Points north of 80S have no terrain data and use a flat horizon.

## Metrics
- `pct_sunlit`, `pct_earth_visible`: share of time steps where the body's **upper
  limb** is above the terrain horizon (no atmosphere, no refraction).
- `max_sun_el_deg`, `mean_sun_el_when_lit_deg`: elevation relative to local horizontal
  (can be slightly negative where the terrain horizon is dipped below 0).
- `mean_horizontal_power_factor`: cos(zenith angle), zero when the Sun is hidden. About 0
  at the poles.
- `mean_vertical_power_factor`, `best_vertical_panel_azimuth_deg`: one fixed vertical
  panel at its best compass direction (10 degree search).
- `longest_darkness_hours`, `longest_earth_gap_hours`: longest continuous stretch with the Sun /
  Earth hidden, **within the requested range** (use at least ~720 h to cover a lunar day).
- `use_terrain: false` is a **flat 0-degree horizon baseline**, not "no terrain".

## Validation
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

## Limitations
- Terrain only south of 80S and out to 200 km; elsewhere a flat horizon is used.
- 80 m DEM, nearest-pixel sampling. The 20 m DEM would be better for site-level work.
- Time steps are sampled (default 10 min); events shorter than a step can be missed.
- Catalog sources are in the `source` field of `/sites`. `malapert` and `connecting_ridge`
  are DEM-derived high points near those features, not official landing sites.
- Eclipses of the Sun by Earth are not modelled.
- Requests are serialised (CSPICE is not thread-safe). Restart after regenerating
  `masks.json`, since results are cached in memory.

## Demo
`python3 demo.py [base_url]` prints a side-by-side comparison of four scenarios.
