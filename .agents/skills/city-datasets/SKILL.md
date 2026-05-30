# Skill: City-Specific Open Datasets

## Barcelona

### Street trees (most precise tree data available)
```python
BCN_TREES_URL = (
    "https://opendata-ajuntament.barcelona.cat/data/api/action/"
    "datastore_search?resource_id=arbrat-viari-2021&limit=50000"
)
# Fields: LONGITUD (lon), LATITUD (lat), DIAMETRENUSOS (crown cm)
def fetch_bcn_trees():
    r = httpx.get(BCN_TREES_URL, timeout=30).json()
    return [{'lon':float(rec['LONGITUD']), 'lat':float(rec['LATITUD']),
             'crown_m': float(rec.get('DIAMETRENUSOS',400))/100}
            for rec in r['result']['records'] if rec.get('LONGITUD')]
```

### Cycling lanes
```
URL: https://opendata-ajuntament.barcelona.cat/data/api/action/
     datastore_search?resource_id=carril-bici&limit=10000
Use: overlay onto OSM edges — is_cycling_lane = True
```

### Superblock boundaries
```
URL: https://opendata-ajuntament.barcelona.cat/data/api/action/
     datastore_search?resource_id=superilles&limit=1000
Use: in_superblock flag per edge (low traffic, pedestrian priority)
```

## Dubai

### RTA API (requires free registration at dubaipulse.gov.ae)
```python
DUBAI_PULSE_BASE = "https://api.dubaipulse.gov.ae"

def get_dubai_token(client_id, client_secret):
    r = httpx.post(
        f"{DUBAI_PULSE_BASE}/oauth/client_credential/accesstoken"
        "?grant_type=client_credentials",
        data={'client_id': client_id, 'client_secret': client_secret}
    )
    return r.json()['access_token']  # valid 30min — cache it

METRO_URL  = f"{DUBAI_PULSE_BASE}/shared/rta/rta_tram_stations-open-api"
BUS_URL    = f"{DUBAI_PULSE_BASE}/shared/rta/rta_bus_routes-open"
```

### Dubai data gaps — fallback strategy
```
Cycling tracks:   OSM highway=cycleway (partial but usable)
Shade structures: no open dataset → use SDK Solar analysis as sole source
Walking paths:    OSM footway + SDK UTCI ground truth
Trees:            OSM natural=tree + SDK vegetation layer combined
```

## Chennai

### GCC GIS REST (public, no auth)
```python
GCC_BASE = "https://gis.chennaicorporation.gov.in/server/rest/services"
# Use for: ward boundaries context only
# NOT reliable for trees or footpaths
```

### Chennai data strategy
```
Trees:     SDK vegetation layer is PRIMARY (satellite-derived, much better than OSM)
Footpaths: OSM highway=footway (reasonable coverage in central Chennai)
Cycling:   Not recommended in v1 (unsafe infrastructure, poor OSM data)
POIs:      OSM amenity tags (good coverage for temples, markets, hospitals)
```

## Nominatim — all cities
```python
NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
CITY_VIEWBOX = {
    'barcelona': '1.9,41.2,2.4,41.6',
    'dubai':     '54.9,24.8,55.6,25.5',
    'chennai':   '79.8,12.8,80.5,13.3',
}

async def geocode(query: str, city: str) -> list:
    params = {
        'q': query, 'format': 'json', 'limit': 4,
        'viewbox': CITY_VIEWBOX[city], 'bounded': '1',
        'accept-language': 'en'
    }
    headers = {'User-Agent': 'ThermalRouter/1.0'}
    r = await httpx.AsyncClient().get(f"{NOMINATIM_BASE}/search",
                                       params=params, headers=headers)
    return [{'lat':float(x['lat']),'lon':float(x['lon']),
             'label':x['display_name']} for x in r.json()]

async def reverse_geocode(lat: float, lon: float) -> str:
    r = await httpx.AsyncClient().get(f"{NOMINATIM_BASE}/reverse",
        params={'lat':lat,'lon':lon,'format':'json'},
        headers={'User-Agent':'ThermalRouter/1.0'})
    parts = r.json().get('display_name','').split(',')
    return ', '.join(parts[:2]).strip()

# RATE LIMIT: 1 request/second max — use 400ms debounce on frontend
```

## Caching all city datasets
```python
# Supabase table: city_datasets
# cache_key: f"{city}:{dataset_name}"
# TTL: 7 days
# Pre-warm on startup: Barcelona trees + cycling lanes
```
