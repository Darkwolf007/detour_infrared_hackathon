import json
import numpy as np
from shapely.geometry import LineString, shape
from shapely.strtree import STRtree
from utils.normalise import normalise_utci, normalise_lawson, normalise_solar, combined_shade

def sample_grid_at_point(grid: np.ndarray, bounds: tuple[float, float, float, float], lon: float, lat: float) -> float:
    """
    Sample a float32 numpy grid (H, W) at a specific (lon, lat) point.
    bounds: (min_lon, min_lat, max_lon, max_lat)
    SDK convention: row 0 = south (min_lat), last row = north (max_lat).
    """
    h, w = grid.shape
    min_lon, min_lat, max_lon, max_lat = bounds
    
    # Calculate column and row indices.
    # SDK convention: row 0 = south (min_lat), last row = north (max_lat).
    # Column 0 = west (min_lon), last column = east (max_lon).
    if max_lon == min_lon:
        col = 0
    else:
        col = int((lon - min_lon) / (max_lon - min_lon) * w)

    if max_lat == min_lat:
        row = 0
    else:
        row = int((lat - min_lat) / (max_lat - min_lat) * h)
        
    # Clamp to grid boundary
    col = max(0, min(w - 1, col))
    row = max(0, min(h - 1, row))
    
    val = float(grid[row, col])
    return 0.0 if np.isnan(val) else val

def sample_edge(geom, grid: np.ndarray, bounds: tuple[float, float, float, float]) -> float:
    """
    Sample an edge geometry: midpoint for shorter edges (<=100m),
    5-point average for longer edges (>100m).
    """
    # length in degrees to metres approx (1 deg lat = 111,000m)
    length_m = geom.length * 111000
    if length_m > 100.0:
        # 5-point average
        vals = []
        for i in range(5):
            point = geom.interpolate(i / 4.0, normalized=True)
            vals.append(sample_grid_at_point(grid, bounds, point.x, point.y))
        return float(np.mean(vals))
    else:
        # Midpoint
        mid = geom.interpolate(0.5, normalized=True)
        return sample_grid_at_point(grid, bounds, mid.x, mid.y)

def enrich_all_edges(
    G,
    sdk_grids: dict[str, np.ndarray],
    bounds: tuple[float, float, float, float],
    veg_features: list[dict],
    persona_analyses: list[str],
    grid_bounds: dict[str, tuple] | None = None,
) -> dict[tuple, dict]:
    """
    Enrich all edges of graph G with microclimate scores.
    G: undirected networkx MultiGraph
    sdk_grids: dict containing 'utci', 'wind', 'solar' (and maybe 'svf')
    bounds: tuple of (min_lon, min_lat, max_lon, max_lat)
    veg_features: list of GeoJSON features representing vegetation
    persona_analyses: list of active analyses for the persona (e.g. ['UTCI', 'Wind'])
    
    Returns: {(u, v, k): score_dict}
    """
    # Build vegetation spatial index if vegetation features exist and active
    veg_tree = None
    use_veg = any(a.lower() in ("vegetation", "nature") for a in persona_analyses)
    if use_veg and veg_features:
        veg_geoms = []
        for f in veg_features:
            if isinstance(f, str):
                try:
                    f = json.loads(f)
                except Exception:
                    continue
            if not isinstance(f, dict):
                continue
            if f.get("geometry"):
                try:
                    veg_geoms.append(shape(f["geometry"]))
                except Exception:
                    pass
        if veg_geoms:
            veg_tree = STRtree(veg_geoms)

    def _bounds_for(key: str) -> tuple:
        """Return the correct geographic extent for a specific grid layer."""
        if grid_bounds and key in grid_bounds:
            return grid_bounds[key]
        return bounds

    results = {}

    # Normalize analyses list to lower case
    analyses_lower = [a.lower() for a in persona_analyses]
    
    for u, v, k, data in G.edges(keys=True, data=True):
        geom = data.get("geometry")
        if not geom:
            geom = LineString([
                (G.nodes[u]["x"], G.nodes[u]["y"]),
                (G.nodes[v]["x"], G.nodes[v]["y"])
            ])
            
        scores = {}
        
        # 1. UTCI scoring
        if "utci" in sdk_grids and "utci" in analyses_lower:
            raw = sample_edge(geom, sdk_grids["utci"], _bounds_for("utci"))
            scores["utci_score"] = normalise_utci(raw)
            scores["raw_utci"] = round(raw, 1)
        else:
            scores["utci_score"] = 0.5  # Neutral default
            scores["raw_utci"] = 26.0

        # 2. Wind scoring
        # Support either 'wind' or 'pwc' in persona analyses
        has_wind_req = "wind" in analyses_lower or "pwc" in analyses_lower
        if "wind" in sdk_grids and has_wind_req:
            raw_wind = sample_edge(geom, sdk_grids["wind"], _bounds_for("wind"))
            scores["wind_score"] = normalise_lawson(raw_wind)
        else:
            scores["wind_score"] = 0.3  # Neutral default

        # 3. Solar / Shade scoring
        if "solar" in sdk_grids and "solar" in analyses_lower:
            _solar_bounds = _bounds_for("solar")
            solar_n = normalise_solar(sample_edge(geom, sdk_grids["solar"], _solar_bounds))
            svf_n = sample_edge(geom, sdk_grids["svf"], _solar_bounds) if "svf" in sdk_grids else 0.5
            scores["shade_score"] = combined_shade(solar_n, svf_n)
        else:
            scores["shade_score"] = 0.5  # Neutral default
            
        # 4. Vegetation / Nature scoring
        if veg_tree and use_veg:
            # Query vegetation within buffer (~11m buffer for nearby vegetation)
            buf = geom.buffer(0.0001)
            veg_nearby = len(veg_tree.query(buf))
            length_m = max(1.0, geom.length * 111000)
            # Normalize so that 1 tree per 10m gives a perfect score of 1.0
            scores["veg_score"] = min(1.0, veg_nearby / max(1.0, length_m / 10.0))
        else:
            scores["veg_score"] = 0.3  # Neutral default
            
        results[(u, v, k)] = scores
        
    return results
