from typing import Optional, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import lunar

app = FastAPI(title="Lunar Landing Site Navigator API")
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])
# Approximate coordinates (planetocentric lat, east lon). VERIFY against
# mission documents / LOLA before relying on them.
SITES = {
    "apollo11": {"name": "Apollo 11", "lat": 0.674, "lon": 23.473, "height_km": 0.0},
    "apollo15": {"name": "Apollo 15", "lat": 26.132, "lon": 3.634, "height_km": 0.0},
    "apollo17": {"name": "Apollo 17", "lat": 20.191, "lon": 30.772, "height_km": 0.0},
    "shackleton_rim": {"name": "Shackleton rim (approx)", "lat": -89.54, "lon": 129.78, "height_km": 0.0},
    "malapert": {"name": "Malapert massif (approx)", "lat": -85.99, "lon": 0.12, "height_km": 0.0},
}
HORIZON_MASKS = {}  # site_id -> list of 360 floats (precomputed from LOLA)


class Query(BaseModel):
    site_id: Optional[str] = None
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lon: Optional[float] = Field(None, ge=-180, le=360)
    height_km: float = 0.0
    start_utc: str = "2027-03-01T00:00:00"
    hours: float = Field(24 * 30, gt=0, le=24 * 400)
    step_min: float = Field(10, ge=1, le=1440)
    now_utc: Optional[str] = None
    use_terrain: bool = True


def resolve(q: Query):
    if q.site_id:
        s = SITES.get(q.site_id)
        if not s:
            raise HTTPException(404, "unknown site_id")
        return s["lat"], s["lon"], s["height_km"], HORIZON_MASKS.get(q.site_id)
    if q.lat is None or q.lon is None:
        raise HTTPException(422, "provide site_id or lat/lon")
    return q.lat, q.lon, q.height_km, None


@app.get("/sites")
def sites():
    return [{"id": k, **v} for k, v in SITES.items()]


@app.post("/timeseries")
def timeseries(q: Query):
    lat, lon, h, mask = resolve(q)
    ts = lunar.timeseries(lat, lon, h, q.start_utc, q.hours, q.step_min,
                          mask if q.use_terrain else None)
    return {
        "step_min": q.step_min, "start_utc": q.start_utc,
        **{k: v.tolist() for k, v in ts.items()},
        "summary": lunar.summary(ts),
    }


@app.post("/windows")
def windows(q: Query):
    lat, lon, h, mask = resolve(q)
    ts = lunar.timeseries(lat, lon, h, q.start_utc, q.hours, q.step_min,
                          mask if q.use_terrain else None)
    return {**lunar.windows(ts, q.now_utc), "summary": lunar.summary(ts)}


@app.post("/compare")
def compare(queries: List[Query]):
    out = []
    for q in queries:
        lat, lon, h, mask = resolve(q)
        ts = lunar.timeseries(lat, lon, h, q.start_utc, q.hours, q.step_min,
                              mask if q.use_terrain else None)
        out.append({"site_id": q.site_id, "lat": lat, "lon": lon,
                    "start_utc": q.start_utc, **lunar.summary(ts)})
    return out


@app.get("/horizon/{site_id}")
def horizon(site_id: str):
    if site_id not in HORIZON_MASKS:
        raise HTTPException(404, "no horizon mask precomputed for this site")
    return {"site_id": site_id, "elevation_deg_by_azimuth": HORIZON_MASKS[site_id]}
