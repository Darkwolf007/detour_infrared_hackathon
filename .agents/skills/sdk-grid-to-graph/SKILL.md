# Skill: SDK Grid → Road Graph Correlation

## The core operation
SDK returns a float32 numpy grid + geographic bounds.
OSM edges are LineString geometries in WGS84.
This skill samples the grid at each edge's midpoint to assign thermal scores.

## Grid sampler
```python
import numpy as np
from shapely.geometry import LineString

def sample_grid_at_point(grid, bounds, lon, lat):
    """
    grid:   numpy float32 (H, W)
    bounds: (min_lon, min_lat, max_lon, max_lat)
    """
    h, w = grid.shape
    min_lon, min_lat, max_lon, max_lat = bounds
    col = int((lon - min_lon) / (max_lon - min_lon) * w)
    row = int((max_lat - lat) / (max_lat - min_lat) * h)  # lat is inverted
    col = max(0, min(w-1, col))
    row = max(0, min(h-1, row))
    val = float(grid[row, col])
    return 0.0 if np.isnan(val) else val

def sample_edge_midpoint(geom, grid, bounds):
    mid = geom.interpolate(0.5, normalized=True)
    return sample_grid_at_point(grid, bounds, mid.x, mid.y)

def sample_edge_average(geom, grid, bounds, n=5):
    """Use for edges longer than 100m."""
    vals = [sample_grid_at_point(grid, bounds,
            *geom.interpolate(i/(n-1), normalized=True).coords[0][:2])
            for i in range(n)]
    return float(np.mean(vals))

def sample_edge(geom, grid, bounds):
    length_m = geom.length * 111000
    return sample_edge_average(geom, grid, bounds) if length_m > 100 \
           else sample_edge_midpoint(geom, grid, bounds)
```

## Normalisation
```python
def normalise_utci(raw):
    """26°C comfortable → 46°C extreme stress → 0-1"""
    return max(0.0, min(1.0, (raw - 26) / 20.0))

def normalise_lawson(raw):
    """Lawson class 0-5 → 0-1"""
    return max(0.0, min(1.0, raw / 5.0))

def normalise_solar(raw):
    """0 = full shade, 8h = full exposure → 0-1"""
    return max(0.0, min(1.0, raw / 8.0))

def combined_shade(solar_norm, svf_norm):
    """Higher = more shaded = good. SVF: 0=canyon, 1=open sky."""
    return 0.6 * (1.0 - solar_norm) + 0.4 * (1.0 - svf_norm)
```

## Batch enrich all graph edges
```python
from shapely.strtree import STRtree
from shapely import shape

def enrich_all_edges(G, sdk_grids, bounds, veg_features):
    """
    G:            osmnx graph (undirected)
    sdk_grids:    {'utci': ndarray, 'wind': ndarray, 'solar': ndarray}
    bounds:       (min_lon, min_lat, max_lon, max_lat)
    veg_features: list of GeoJSON feature dicts from SDK
    Returns: {(u,v,k): score_dict}
    """
    veg_geoms = [shape(f['geometry']) for f in veg_features if f.get('geometry')]
    veg_tree  = STRtree(veg_geoms)
    results   = {}

    for u,v,k,data in G.edges(keys=True, data=True):
        geom = data.get('geometry') or LineString([
            (G.nodes[u]['x'], G.nodes[u]['y']),
            (G.nodes[v]['x'], G.nodes[v]['y'])
        ])
        scores = {}

        if 'utci' in sdk_grids:
            raw = sample_edge(geom, sdk_grids['utci'], bounds)
            scores['utci_score'] = normalise_utci(raw)
            scores['raw_utci']   = round(raw, 1)

        if 'wind' in sdk_grids:
            scores['wind_score'] = normalise_lawson(
                sample_edge(geom, sdk_grids['wind'], bounds))

        solar_n = normalise_solar(sample_edge(geom, sdk_grids['solar'], bounds)) \
                  if 'solar' in sdk_grids else 0.5
        svf_n   = sample_edge(geom, sdk_grids['svf'], bounds) \
                  if 'svf' in sdk_grids else 0.5
        scores['shade_score'] = combined_shade(solar_n, svf_n)

        buf = geom.buffer(0.0001)
        veg_nearby = len(veg_tree.query(buf))
        length_m   = max(1.0, geom.length * 111000)
        scores['veg_score'] = min(1.0, veg_nearby / max(1, length_m / 10))

        results[(u,v,k)] = scores

    return results
```

## Supabase grid serialisation
```python
import base64

def grid_to_b64(grid: np.ndarray) -> str:
    return base64.b64encode(grid.astype(np.float32).tobytes()).decode()

def b64_to_grid(data: str, shape: tuple) -> np.ndarray:
    return np.frombuffer(base64.b64decode(data), dtype=np.float32).reshape(shape)

# Store in sdk_cache.grids JSONB as:
# {"utci":{"data":"<b64>","shape":[H,W]}, "wind":{...}, "solar":{...}}
```

## Important: lat/lon axis in SDK grid
```
SDK grid row 0   = northern edge of bbox (max_lat)
SDK grid row H-1 = southern edge of bbox (min_lat)
SDK grid col 0   = western edge of bbox  (min_lon)
SDK grid col W-1 = eastern edge of bbox  (max_lon)

Therefore: row = (max_lat - lat) / (max_lat - min_lat) * H   ← inverted
           col = (lon - min_lon) / (max_lon - min_lon) * W   ← normal
```
