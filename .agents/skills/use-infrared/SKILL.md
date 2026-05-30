# Skill: Use Infrared SDK

## Purpose
Run microclimate simulations (UTCI, wind, solar, PWC) using the Infrared SDK
for any GeoJSON polygon. This is the physics engine of the thermal router.

## Installation
```bash
pip install infrared-sdk
```

## Environment
```
INFRARED_API_KEY=your_key_here
```

## Core import
```python
from infrared_sdk import InfraredClient
client = InfraredClient(api_key=os.environ["INFRARED_API_KEY"])
```

## Step 1 — Define polygon (GeoJSON, closed ring)
```python
polygon = {
  "type": "Polygon",
  "coordinates": [[
    [lon_min, lat_min],
    [lon_max, lat_min],
    [lon_max, lat_max],
    [lon_min, lat_max],
    [lon_min, lat_min]   # first == last, required
  ]]
}
# Coordinates: [longitude, latitude]. x = East, y = North.
```

## Step 2 — Fetch area context
```python
area     = client.get_area(polygon)
area_veg = client.get_vegetation(polygon)
area_gm  = client.get_ground_materials(polygon)
```

## Step 3 — Find nearest TMY weather station
```python
stations = client.get_weather_stations(lat=lat, lon=lon, radius_km=50)
station  = stations[0]
```

## Step 4 — Filter weather to time slot
```python
time_slots = {
  "early_morning": (6,  9),
  "morning":       (9,  12),
  "afternoon":     (12, 16),
  "evening":       (16, 20),
  "night":         (20, 24),
}
h_start, h_end = time_slots[time_slot]
# CRITICAL: h_end - h_start must be >= 1. Never pass equal values.
weather = client.filter_weather_data(station.id, h_start, h_end)
```

## Step 5 — Run all analyses in ONE call
```python
from infrared_sdk.models import UtciModelRequest, WindModelRequest, TcsModelRequest

result = client.run_area_and_wait(
    polygon=polygon,
    buildings=area.buildings,
    vegetation=area_veg.features,
    ground_materials=area_gm.layers,
    weather=weather,
    analyses=[
        UtciModelRequest(),
        WindModelRequest(),
        TcsModelRequest(),
    ]
)
# result.merged_grid  → numpy float32 (H x W)
# result.bounds       → (min_lon, min_lat, max_lon, max_lat)
# result.min_legend / max_legend → colour scale range
```

## Step 6 — Access per-analysis grids
```python
utci_grid  = result.analyses['UTCI'].merged_grid
wind_grid  = result.analyses['Wind'].merged_grid
solar_grid = result.analyses['TCS'].merged_grid
```

## Analysis selection per persona
| Persona          | Analyses                    |
|------------------|-----------------------------|
| Commuter         | UTCI, Wind                  |
| Parent/couple    | UTCI, Solar, Vegetation     |
| Dog walker       | UTCI, Vegetation, Wind      |
| Runner           | UTCI, Wind, PWC             |
| Cyclist          | Wind, PWC                   |
| Tourist          | UTCI, Solar, Vegetation     |
| Shopper          | UTCI, Solar                 |
| Bar hopper       | UTCI, Wind                  |

## Normalisation
```python
def normalise_utci(raw):    return max(0.0, min(1.0, (raw - 26) / 20.0))
def normalise_lawson(raw):  return max(0.0, min(1.0, raw / 5.0))
def normalise_solar(raw):   return max(0.0, min(1.0, raw / 8.0))
```

## Common errors
- ValidationError on TimePeriod: h_start == h_end — always ensure gap >= 1
- Polygon not closed: first and last coordinate must be identical
- Empty grid: bbox too small — minimum ~100m x 100m
- API timeout: always use run_area_and_wait(), never run_async() directly
