"""
Utilities to generate map overlay layers from the graph and SDK grids.
"""
import base64
import io
import logging

import networkx as nx
import numpy as np
from shapely.geometry import LineString, mapping

logger = logging.getLogger("thermal_router.map_layers")

def _utci_colour(value: float) -> tuple[int, int, int, int]:
    """Map raw UTCI °C to RGBA using the same 4-band scale as the frontend utciColor.ts.

    Normalises via (raw - 26) / 20 so the heatmap and route polylines use
    identical colour breakpoints.
    """
    score = max(0.0, min(1.0, (value - 26.0) / 20.0))
    if score < 0.3:
        return (34,  197,  94, 150)   # green  – comfortable
    if score < 0.6:
        return (245, 158,  11, 160)   # amber  – moderate stress
    if score < 0.8:
        return (239,  68,  68, 170)   # red    – high stress
    return     (124,  58, 237, 180)   # purple – extreme stress


def utci_grid_to_png(utci_grid: np.ndarray, bounds: tuple, max_size: int = 256) -> tuple[str, list]:
    """Render UTCI grid as base64 PNG. Returns (b64_str, [[minLat,minLon],[maxLat,maxLon]])."""
    return _grid_to_png(utci_grid, bounds, _utci_colour, max_size, grid_type="utci")


def _wind_colour(value: float) -> tuple[int, int, int, int]:
    """Map wind speed (m/s) to RGBA. Calm=teal, moderate=amber, strong=red."""
    norm = max(0.0, min(1.0, value / 12.0))
    if norm < 0.25:
        return (20,  184, 166, 130)   # teal   – calm / comfortable
    if norm < 0.55:
        return (59,  130, 246, 145)   # blue   – light-moderate breeze
    if norm < 0.78:
        return (245, 158,  11, 155)   # amber  – strong
    return     (239,  68,  68, 170)   # red    – near-gale / dangerous


def _solar_colour(value: float) -> tuple[int, int, int, int]:
    """Map solar irradiance (kWh/m²) to RGBA. Low=indigo, high=orange-red."""
    norm = max(0.0, min(1.0, value / 600.0))
    if norm < 0.25:
        return (99,  102, 241, 120)   # indigo – low radiation
    if norm < 0.55:
        return (250, 204,  21, 135)   # yellow – moderate
    if norm < 0.78:
        return (249, 115,  22, 150)   # orange – high
    return     (239,  68,  68, 165)   # red    – very high


def _utci_rgba_vectorised(g: np.ndarray) -> np.ndarray:
    score = np.clip((g - 26.0) / 20.0, 0.0, 1.0)
    rgba = np.zeros((*g.shape, 4), dtype=np.uint8)
    # green / amber / red / purple bands
    rgba[score < 0.3]  = ( 34, 197,  94, 150)
    rgba[score < 0.6]  = (245, 158,  11, 160)   # overwrites nothing — bands are exclusive via cumulative
    rgba[score < 0.8]  = (239,  68,  68, 170)
    rgba[score >= 0.8] = (124,  58, 237, 180)
    # re-apply in correct order (each threshold overwrites the previous assignment)
    rgba[(score >= 0.0) & (score < 0.3)] = ( 34, 197,  94, 150)
    rgba[(score >= 0.3) & (score < 0.6)] = (245, 158,  11, 160)
    rgba[(score >= 0.6) & (score < 0.8)] = (239,  68,  68, 170)
    rgba[score >= 0.8]                   = (124,  58, 237, 180)
    rgba[np.isnan(g)] = 0
    return rgba


def _wind_rgba_vectorised(g: np.ndarray) -> np.ndarray:
    norm = np.clip(g / 12.0, 0.0, 1.0)
    rgba = np.zeros((*g.shape, 4), dtype=np.uint8)
    rgba[(norm >= 0.0)  & (norm < 0.25)] = ( 20, 184, 166, 130)
    rgba[(norm >= 0.25) & (norm < 0.55)] = ( 59, 130, 246, 145)
    rgba[(norm >= 0.55) & (norm < 0.78)] = (245, 158,  11, 155)
    rgba[norm >= 0.78]                   = (239,  68,  68, 170)
    rgba[np.isnan(g)] = 0
    return rgba


def _solar_rgba_vectorised(g: np.ndarray) -> np.ndarray:
    norm = np.clip(g / 600.0, 0.0, 1.0)
    rgba = np.zeros((*g.shape, 4), dtype=np.uint8)
    rgba[(norm >= 0.0)  & (norm < 0.25)] = ( 99, 102, 241, 120)
    rgba[(norm >= 0.25) & (norm < 0.55)] = (250, 204,  21, 135)
    rgba[(norm >= 0.55) & (norm < 0.78)] = (249, 115,  22, 150)
    rgba[norm >= 0.78]                   = (239,  68,  68, 165)
    rgba[np.isnan(g)] = 0
    return rgba


# Maps each grid type to its vectorised colouring function
_VECTORISED_FN = {
    "utci":  _utci_rgba_vectorised,
    "wind":  _wind_rgba_vectorised,
    "solar": _solar_rgba_vectorised,
}


def _grid_to_png(
    grid: np.ndarray,
    bounds: tuple,
    colour_fn,
    max_size: int = 256,
    grid_type: str = "",
) -> tuple[str, list]:
    """
    Generic raster-to-PNG helper.  Flips the grid north-up (SDK row 0 = south),
    applies colour mapping via vectorised numpy ops, and returns (base64_str, leaflet_bounds).
    """
    from PIL import Image

    g = grid.copy().astype(np.float32)
    h, w = g.shape
    if h == 0 or w == 0:
        raise ValueError(f"Grid has zero dimension: shape={g.shape}")
    if np.all(np.isnan(g)):
        raise ValueError("Grid is entirely NaN — no valid analysis data in this area")
    if h > max_size or w > max_size:
        scale = max_size / max(h, w)
        sh = max(1, h // max(1, int(h * scale)))
        sw = max(1, w // max(1, int(w * scale)))
        g = g[::sh, ::sw]

    g = np.flipud(g)  # SDK row 0 = south; flip so row 0 = north for Leaflet

    vec_fn = _VECTORISED_FN.get(grid_type)
    if vec_fn is not None:
        rgba = vec_fn(g)
    else:
        # Fallback: scalar loop for unknown grid types
        h2, w2 = g.shape
        rgba = np.zeros((h2, w2, 4), dtype=np.uint8)
        for r in range(h2):
            for c in range(w2):
                v = float(g[r, c])
                rgba[r, c] = (0, 0, 0, 0) if np.isnan(v) else colour_fn(v)

    img = Image.fromarray(rgba, mode="RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    min_lon, min_lat, max_lon, max_lat = bounds
    return b64, [[min_lat, min_lon], [max_lat, max_lon]]


def wind_grid_to_png(wind_grid: np.ndarray, bounds: tuple, max_size: int = 256) -> tuple[str, list]:
    return _grid_to_png(wind_grid, bounds, _wind_colour, max_size, grid_type="wind")


def solar_grid_to_png(solar_grid: np.ndarray, bounds: tuple, max_size: int = 256) -> tuple[str, list]:
    return _grid_to_png(solar_grid, bounds, _solar_colour, max_size, grid_type="solar")


_MAX_NETWORK_FEATURES = 500


def graph_to_network_geojson(G: nx.MultiGraph) -> dict:
    """
    Convert a sampled subset of G's edges to a GeoJSON FeatureCollection.
    Capped at _MAX_NETWORK_FEATURES to keep the HTTP payload manageable and
    prevent the browser from freezing when rendering thousands of polylines.
    """
    all_edges = list(G.edges(keys=True, data=True))
    # Sample evenly if graph is larger than the cap
    step = max(1, len(all_edges) // _MAX_NETWORK_FEATURES)
    sampled = all_edges[::step][:_MAX_NETWORK_FEATURES]

    features = []
    for u, v, k, data in sampled:
        geom = data.get("geometry")
        if not geom:
            try:
                geom = LineString([
                    (G.nodes[u]["x"], G.nodes[u]["y"]),
                    (G.nodes[v]["x"], G.nodes[v]["y"]),
                ])
            except Exception:
                continue

        props = {
            "utci_score": data.get("utci_score"),
            "cost": data.get("cost"),
        }
        # geom may already be a GeoJSON dict (graphml load path) or a Shapely object
        geom_dict = geom if isinstance(geom, dict) else mapping(geom)
        features.append({
            "type": "Feature",
            "geometry": geom_dict,
            "properties": props,
        })

    return {"type": "FeatureCollection", "features": features}
