# ThermalRoute — Build Progress

## Status: Steps 1–4 complete and tested

---

## Done

### Step 1 — FastAPI scaffold ✓
- `backend/main.py` — app factory, CORS from `CORS_ORIGINS` env, `/health` endpoint
- `backend/requirements.txt` — all deps pinned (`google-genai>=2.0.0`, not deprecated `google-generativeai`)
- `backend/.env` — `INFRARED_API_KEY` filled in; `SUPABASE_URL/KEY` and `GEMINI_API_KEY` still blank
- Stub router files so imports resolve from day one

### Step 2 — Personas router ✓
- `backend/routers/personas.py`
  - `GET /api/v1/personas` — Supabase query `is_default=true OR is_public=true`, optional `?city=` filter
  - `POST /api/v1/personas/custom` — Gemini `gemini-2.0-flash` → weight vector; fallback to balanced defaults
- `backend/utils/db.py` — `get_supabase()` singleton (`@lru_cache`), shared by all services

### Step 3 — Utility modules ✓  (13 tests green)
- `backend/utils/bbox.py`
  - `bbox_from_stops(stops, padding_m=500)` — tight route bbox
  - `bbox_from_loop(start, max_dist_m)` — loop bbox
  - `bbox_to_polygon(bbox)` — closed GeoJSON ring `[lon, lat]` per RFC 7946
  - `make_cache_key(city, bbox, time_slot, analyses)` — sha256, analyses order-independent
  - `bbox_center(bbox)` — `(lat, lon)` for weather station lookup
- `backend/utils/normalise.py`
  - `normalise_utci/lawson/solar`, `combined_shade`
  - `SURFACE_PENALTY`, `HIGHWAY_SAFETY` lookup dicts
  - `apply_age_boost`, `normalise_weights`

### Step 4 — Cache service ✓  (6 serialisation tests green)
- `backend/services/cache_service.py`
  - `get_cached_sdk(cache_key)` → row or None (filters `expires_at > now`)
  - `store_sdk_cache(...)` → upserts with 24h TTL; falls back to insert if UNIQUE constraint absent
  - `serialise_grids` / `deserialise_grids` — float32 ndarray ↔ base64 JSONB; NaN-safe; handles list and dict bounds from Supabase
  - `get_cache_stats()` → total/live/expired row counts
- `backend/routers/cache.py` — `GET /api/v1/cache/status`

---

## Locked-in decisions

| Decision | Choice |
|---|---|
| UTCI TimePeriod month | Current calendar month (dynamic) |
| PWC analysis | Fall back to `wind-speed` (simpler) |
| Supabase grid storage | Full base64 float32 blobs in JSONB |
| SDK analyses per call | Always UTCI + Wind + Solar (3 payloads, 1 `run_area_and_wait` call) |
| SDK bbox | Tight route bbox via `bbox_from_stops`, NOT full city bbox |
| Gemini library | `google-genai` v2 (`genai.Client`) — old `google.generativeai` is deprecated |
| Weather station field | `locations[0]["uuid"]` — `"identifier"` field no longer exists in SDK |
| `sdk_result` contract | `{"utci": ndarray, "wind": ndarray, "solar": ndarray, "bounds": tuple, "legend": dict}` |

---

## Remaining steps

### Step 5 — `utils/grid_sampler.py`  ← NEXT
SDK numpy grid → OSM edge score. Pure numpy, no external deps.
- `sample_grid_at_point(grid, bounds, lon, lat)` — inverted lat axis: `row = (max_lat - lat) / range * H`
- `sample_edge(geom, grid, bounds)` — midpoint for ≤100m edges, 5-point average for >100m
- `enrich_all_edges(G, sdk_grids, bounds, veg_features)` → `{(u,v,k): score_dict}`
  - score_dict keys: `utci_score`, `raw_utci`, `wind_score`, `shade_score`, `veg_score`
  - veg scoring via `STRtree` on SDK vegetation geometries

### Step 6 — `services/sdk_service.py`
Infrared SDK wrapper. **SDK only called here, never on import/startup.**
- `run_sdk(bbox, time_slot, city_lat, city_lon)` → `sdk_result` dict (see contract above)
- `InfraredClient` used as context manager
- Builds 3-payload list → single `client.run_area_and_wait([utci, wind, solar], polygon, buildings=..., vegetation=..., ground_materials=...)`
- Unpacks results list: `utci_r, wind_r, solar_r = results`
- UTCI `TimePeriod`: `start_month = end_month = datetime.now().month`; hours from `TIME_SLOTS[time_slot]`; clamp `h_end=24 → 23`
- Wind: `WindModelRequest(wind_speed=10, wind_direction=270)` — fixed defaults
- Solar: `SolarModelRequest` with same `TimePeriod` as UTCI
- Ground materials guard: pass `{}` if `area_gm.total_features > 5000`
- Weather: `client.weather.get_weather_file_from_location(lat, lon, radius=50)` → use `stations[0]["uuid"]`

### Step 7 — `services/osm_service.py`
OSMnx graph download and edge enrichment.
- `get_walk_graph(bbox)` → undirected graph with `useful_tags_way` list
- `enrich_graph(G, edge_scores, persona_weights, surface_pen, highway_saf)` → sets `G[u][v][k]['cost']`
- `build_poi_index(G)` → `STRtree` of amenity/tourism nodes
- `poi_density(edge_geom, poi_tree, radius_deg=0.0005)` → 0–1

### Step 8 — `services/routing_service.py`
Dijkstra + loop algorithm → GeoJSON + edge_scores list.
- `route_typical(G, stops)` → `nx.shortest_path(G, src, dst, weight='cost')`
- `route_multi(G, stops)` → chain `shortest_path` between consecutive stop pairs
- `route_loop(G, start_node, max_dist_m)` → greedy expansion + `shortest_path` back
- `path_to_geojson(G, node_path)` — use edge `geometry` attr if present, else straight line
- `turn_penalty(prev_bearing, curr_bearing, preference)` → add to cost
- `build_summary(edge_scores_list, distance_m)` → `{avg_utci, avg_shade, comfort_rating, …}`
- Returns `(route_geojson, edge_scores_list, summary_dict)`

### Step 9 — `services/gemini_service.py`
Formalise Gemini (refactor from `personas.py` + add narrative).
- Move `_infer_persona` from `routers/personas.py` here; update personas.py import
- Add `generate_narrative(meta)` → 2-sentence plain-text route explanation
- `meta` dict: `{persona_name, city, distance_m, duration_min, avg_utci, shade_pct, nature_pct, time_slot, comfort_rating}`

### Step 10 — `routers/route.py`
Full POST /route + polling. Orchestrates all services.
- `POST /api/v1/route` → 202 `{job_id, status:"processing", estimated_seconds:8}`
- `BackgroundTasks` runs `process_route(job_id, req)`:
  1. Build bbox from stops/loop
  2. `make_cache_key` → `get_cached_sdk` (hit/miss)
  3. Miss: `sdk_service.run_sdk()` → `store_sdk_cache()`
  4. `deserialise_grids(row)` → numpy grids
  5. `osm_service.get_walk_graph(bbox)` → `enrich_all_edges()` → `assign_costs()`
  6. `routing_service.route_*(…)` → geojson + edge_scores
  7. `gemini_service.generate_narrative(meta)`
  8. Store `route_requests` row in Supabase
  9. Write result to `jobs[job_id]`
- `GET /api/v1/route/status/{job_id}` → job dict from `jobs = {}` (in-memory)

### Step 11 — Frontend scaffold
- `npm create vite@latest frontend -- --template react-ts`
- Install: `react-leaflet leaflet @types/leaflet zustand @tanstack/react-query axios`
- `src/types/index.ts` — Persona, Stop, RouteRequest, RouteResult, EdgeScore, Summary
- `src/utils/utciColor.ts` — score → hex (`<0.3` green, `<0.6` amber, `<0.8` red, else purple)
- `src/utils/cityConfig.ts` — center, zoom, nominatim_bbox per city
- `src/store/routerStore.ts` — Zustand store (all form + result state)

### Step 12 — Frontend components
- `CitySelector`, `AgeGroupSelector`, `ReasonSelector`, `PersonaPreview`
- `RouteTypeSelector` — auto-selects from `sub_reason` via `ROUTE_DEFAULTS` map
- `StopInputs` + `useNominatim.ts` — debounced 400ms, `User-Agent: ThermalRoute/1.0`, 1 req/s
- `LoopDistanceChips` — 1km / 2km / 5km / 10km / 30min (≈2400m) / 60min (≈4800m)
- `TimeSlotSelector`, `PreferencePanel` (sliders → `normalise_weights`, shows live bar chart)
- `FindRouteButton` — validates form (typical needs 2 stops, loop needs 1 + distance)
- `LoadingOverlay` — staged messages: 0ms / 1500ms / 3000ms / 7000ms
- `MapPanel` — react-leaflet + free OSM tiles (no API key)
- `usePersonas.ts` — React Query `GET /personas`
- `useRoute.ts` — React Query `POST /route` + `refetchInterval: data?.status==='done' ? false : 2000`

### Step 13 — Route result display
- `MapPanel` renders `edge_scores` as individual `<Polyline>` — colour from `utciColor`, weight=5, opacity=0.85; tooltip shows `raw_utci °C`
- `ResultSummary` — distance, duration, comfort badge, avg UTCI, Gemini narrative, shade/green/POI chips
- City warnings: Dubai afternoon, Chennai monsoon

---

## Environment checklist

Fill in `thermal-router/backend/.env`:
```
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...
GEMINI_API_KEY=AIza...
```
`INFRARED_API_KEY` is already set.

Supabase tables required (already created per spec):
`personas`, `sdk_cache`, `route_requests`, `city_datasets`

---

## Run locally

```bash
cd thermal-router/backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# docs → http://localhost:8000/docs
```
