# Skill: Thermal Comfort Routing — FastAPI Backend

## Dependencies
```
fastapi uvicorn[standard] osmnx networkx shapely geopandas
numpy supabase httpx python-dotenv infrared-sdk
```

## Environment variables
```
INFRARED_API_KEY=
SUPABASE_URL=
SUPABASE_KEY=
GEMINI_API_KEY=
DUBAI_PULSE_CLIENT_ID=
DUBAI_PULSE_CLIENT_SECRET=
```

## Project structure
```
backend/
  main.py
  routers/
    route.py        # POST /route, GET /route/status/{job_id}
    personas.py     # GET /personas, POST /personas/custom
    cache.py        # GET /cache/status
  services/
    sdk_service.py
    osm_service.py
    routing_service.py
    gemini_service.py
    cache_service.py
  models/
    request_models.py
    response_models.py
  utils/
    grid_sampler.py
    normalise.py
    bbox.py
```

## Rule 1 — SDK runs LAZY, cache-first
```python
async def get_or_run_sdk(city, bbox, time_slot, analyses, supabase):
    key = make_cache_key(city, bbox, time_slot, analyses)
    cached = supabase.table("sdk_cache").select("*").eq("cache_key", key).execute()
    if cached.data:
        return cached.data[0]          # HIT: instant
    result = await run_sdk(bbox, time_slot, analyses)
    store_cache(supabase, key, city, bbox, time_slot, analyses, result)
    return result                      # MISS: run + cache
```

## Rule 2 — Cache key
```python
import hashlib, json
def make_cache_key(city, bbox, time_slot, analyses):
    bbox_r = {k: round(v, 3) for k, v in bbox.items()}  # 3dp ~110m
    payload = f"{city}:{json.dumps(bbox_r,sort_keys=True)}:{time_slot}:{sorted(analyses)}"
    return hashlib.sha256(payload.encode()).hexdigest()
```

## Rule 3 — OSM graph fetch
```python
import osmnx as ox
def get_walk_graph(bbox):
    G = ox.graph_from_bbox(
        bbox['max_lat'], bbox['min_lat'], bbox['max_lon'], bbox['min_lon'],
        network_type='walk', retain_all=True,
        useful_tags_way=['highway','surface','lit','width','foot','bicycle',
                         'access','name','natural','landuse','amenity',
                         'tourism','covered','cycleway','oneway']
    )
    return ox.convert.to_undirected(G)
```

## Rule 4 — Grid sampling (raster to vector)
```python
def sample_grid(grid, bounds, lon, lat):
    h, w = grid.shape
    col = int((lon - bounds[0]) / (bounds[2] - bounds[0]) * w)
    row = int((bounds[3] - lat) / (bounds[3] - bounds[1]) * h)
    return float(grid[max(0,min(h-1,row)), max(0,min(w-1,col))])

def sample_edge(edge_geom, grid, bounds):
    mid = edge_geom.interpolate(0.5, normalized=True)
    return sample_grid(grid, bounds, mid.x, mid.y)
```

## Rule 5 — Edge enrichment
```python
SURFACE_PENALTY = {
    'asphalt':0.0,'paving_stones':0.05,'concrete':0.05,
    'sett':0.15,'compacted':0.2,'gravel':0.4,'dirt':0.5,'sand':0.9,None:0.1
}
HIGHWAY_SAFETY = {
    'footway':0.0,'path':0.05,'pedestrian':0.0,'living_street':0.05,
    'residential':0.1,'cycleway':0.05,'tertiary':0.3,
    'secondary':0.5,'primary':0.7,'trunk':0.9
}
def enrich_edge(edge_data, geom, grids, bounds, veg_features):
    utci_score  = normalise_utci(sample_edge(geom, grids['utci'], bounds))
    wind_score  = normalise_lawson(sample_edge(geom, grids.get('wind'), bounds)) if 'wind' in grids else 0.3
    solar_norm  = normalise_solar(sample_edge(geom, grids.get('solar'), bounds)) if 'solar' in grids else 0.5
    shade_score = 1.0 - solar_norm
    buf = geom.buffer(0.0001)
    veg_score   = min(1.0, sum(1 for f in veg_features if buf.intersects(f)) / max(1, geom.length*111000/10))
    return {
        'utci_score':utci_score, 'wind_score':wind_score,
        'shade_score':shade_score, 'veg_score':veg_score,
        'surface_penalty': SURFACE_PENALTY.get(edge_data.get('surface'), 0.1),
        'highway_safety':  HIGHWAY_SAFETY.get(edge_data.get('highway'), 0.2),
    }
```

## Rule 6 — Edge cost function
```python
def edge_cost(scores, persona, length_m):
    return (
        persona.w_speed    * (length_m / 100.0)
        + persona.w_shade  * (1 - scores['shade_score'])
        + persona.w_nature * (1 - scores['veg_score'])
        + persona.w_discovery * (1 - scores.get('poi_density', 0.1))
        + persona.w_speed  * scores['surface_penalty']
        + persona.w_speed  * scores['highway_safety']
    ) * length_m
```

## Rule 7 — Turn penalty
```python
import math
def turn_penalty(prev_bearing, curr_bearing, preference):
    thresholds = {'low':(45,0.4), 'mid':(90,0.2), 'high':(999,0.0)}
    angle, weight = thresholds[preference]
    diff = abs((curr_bearing - prev_bearing + 180) % 360 - 180)
    return weight if diff > angle else 0.0
```

## Rule 8 — Route algorithms
```python
# TYPICAL
path = nx.shortest_path(G, source_node, target_node, weight='cost')

# MULTI: chain paths
full = []
for i in range(len(stops)-1):
    seg = nx.shortest_path(G, stops[i].node, stops[i+1].node, weight='cost')
    full.extend(seg[:-1])
full.append(seg[-1])

# LOOP: greedy expansion
def build_loop(G, start, max_dist_m):
    visited, dist, cur = [start], 0.0, start
    while dist < max_dist_m * 0.85:
        nbrs = sorted([(n, G[cur][n][0].get('cost',1.0))
                       for n in G.neighbors(cur) if n not in visited], key=lambda x:x[1])
        if not nbrs: break
        nxt = nbrs[0][0]
        dist += G[cur][nxt][0].get('length', 50)
        visited.append(nxt); cur = nxt
    return_path = nx.shortest_path(G, cur, start, weight='cost')
    visited.extend(return_path[1:])
    return visited
```

## Rule 9 — Async job pattern (202 + polling)
```python
jobs = {}

@router.post("/route")
async def create_route(req, background_tasks: BackgroundTasks):
    job_id = str(uuid4())
    jobs[job_id] = {"status": "processing"}
    background_tasks.add_task(process_route, job_id, req)
    return JSONResponse(status_code=202,
        content={"status":"processing","job_id":job_id,"estimated_seconds":8})

@router.get("/route/status/{job_id}")
async def route_status(job_id: str):
    return jobs.get(job_id) or HTTPException(404)
```

## Rule 10 — Gemini persona prompt
```python
GEMINI_PROMPT = """Given description: '{description}' for city '{city}',
return ONLY valid JSON (no markdown, no backticks):
{{"name":"...","w_speed":0.0,"w_shade":0.0,"w_nature":0.0,"w_discovery":0.0,
"turn_preference":"low|mid|high","default_route":"typical|multi|loop","reasoning":"..."}}
Weights must sum to 1.0."""
```
