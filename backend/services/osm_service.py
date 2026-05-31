import hashlib
import os
import logging
import osmnx as ox
import networkx as nx
import numpy as np
from shapely.geometry import Point, LineString
from shapely.strtree import STRtree
from typing import Optional

from utils.normalise import SURFACE_PENALTY, HIGHWAY_SAFETY

logger = logging.getLogger("thermal_router.osm_service")

# ── disk cache ────────────────────────────────────────────────────────────────
_GRAPH_CACHE_DIR = os.environ.get(
    "GRAPH_CACHE_DIR",
    os.path.join(os.path.dirname(__file__), "..", "_osm_cache"),
)

# Pre-warmed city bboxes — must match prewarm_osm.py exactly.
# Each bbox is large enough to contain any typical pedestrian route within the city.
_CITY_BBOXES = {
    "barcelona": {"min_lat": 41.340, "max_lat": 41.450, "min_lon": 2.080,  "max_lon": 2.240},
    "dubai":     {"min_lat": 25.090, "max_lat": 25.320, "min_lon": 55.170, "max_lon": 55.400},
    "chennai":   {"min_lat": 13.055, "max_lat": 13.110, "min_lon": 80.250, "max_lon": 80.300},
}

# Street network is always served from pre-warmed graphml files (see _CITY_BBOXES).
# Overpass is not used at runtime — no endpoint configuration needed.

# In-memory graphml cache so the city graph is only loaded from disk once per process.
_LOADED_GRAPHS: dict[str, nx.MultiGraph] = {}

# Preserve crucial OSM tags on edges
CRITICAL_TAGS = [
    "highway", "surface", "lit", "width", "foot", "bicycle",
    "access", "name", "natural", "landuse", "amenity",
    "tourism", "covered", "cycleway", "oneway", "maxspeed",
]
for tag in CRITICAL_TAGS:
    if tag not in ox.settings.useful_tags_way:
        ox.settings.useful_tags_way.append(tag)


def _graph_cache_path(bbox: dict) -> str:
    """
    Return a deterministic file path for caching an OSM graph by bbox.
    Rounds to 3 dp (~110 m) so nearby routes share the same cached graph.
    """
    key = (
        f"{round(bbox['min_lat'], 3):.3f}_"
        f"{round(bbox['min_lon'], 3):.3f}_"
        f"{round(bbox['max_lat'], 3):.3f}_"
        f"{round(bbox['max_lon'], 3):.3f}"
    )
    digest = hashlib.sha1(key.encode()).hexdigest()[:16]
    os.makedirs(_GRAPH_CACHE_DIR, exist_ok=True)
    return os.path.join(_GRAPH_CACHE_DIR, f"{digest}.graphml")



def _largest_component(G: nx.MultiGraph) -> nx.MultiGraph:
    """Return the largest connected component of G (drops isolated sub-graphs)."""
    if nx.is_connected(G):
        return G
    largest = max(nx.connected_components(G), key=len)
    before = G.number_of_nodes()
    G = G.subgraph(largest).copy()
    logger.info(f"Kept largest component: {G.number_of_nodes()}/{before} nodes")
    return G


def _find_city_superset(bbox: dict) -> str | None:
    """
    If bbox is fully contained within a pre-warmed city bbox, return the path
    to that cached graph. This lets every route request reuse the city graph
    regardless of the exact stop positions.
    """
    for city_bbox in _CITY_BBOXES.values():
        if (city_bbox["min_lat"] <= bbox["min_lat"] and
                city_bbox["max_lat"] >= bbox["max_lat"] and
                city_bbox["min_lon"] <= bbox["min_lon"] and
                city_bbox["max_lon"] >= bbox["max_lon"]):
            path = _graph_cache_path(city_bbox)
            if os.path.exists(path):
                return path
    return None


def get_walk_graph_cached(bbox: dict) -> nx.MultiGraph:
    """
    Return a pedestrian walk graph for bbox from pre-warmed graphml files only.

    Lookup order:
      1. Exact bbox cache hit  (~0.1 s)
      2. Pre-warmed city superset graph — load full city graphml, clip to route bbox (~0.2 s)

    Raises RuntimeError if the bbox is not covered by any cached graphml.
    Add new cities to _CITY_BBOXES and run prewarm_osm.py to extend coverage.
    """
    # 1. Exact hit
    path = _graph_cache_path(bbox)
    if os.path.exists(path):
        logger.info(f"OSM graph cache HIT (exact) — {path}")
        G = ox.load_graphml(path)
        return _largest_component(ox.convert.to_undirected(G))

    # 2. Route bbox is inside a pre-warmed city graph — load and clip to route area
    city_path = _find_city_superset(bbox)
    if city_path:
        if city_path in _LOADED_GRAPHS:
            logger.info("OSM graph cache HIT (in-memory) — clipping to route bbox")
            G_city = _LOADED_GRAPHS[city_path]
        else:
            logger.info("OSM graph cache HIT (city superset) — loading from disk and clipping to route bbox")
            G_city = ox.load_graphml(city_path)
            xs = [d["x"] for _, d in G_city.nodes(data=True)]
            ys = [d["y"] for _, d in G_city.nodes(data=True)]
            logger.info(f"Graphml extent: lon {min(xs):.4f}–{max(xs):.4f}, lat {min(ys):.4f}–{max(ys):.4f} ({G_city.number_of_nodes()} nodes)")
            _LOADED_GRAPHS[city_path] = G_city
        # truncate_graph_bbox mutates the graph; work on a copy to preserve the cached original
        G = ox.truncate.truncate_graph_bbox(
            G_city.copy(),
            (bbox["min_lon"], bbox["min_lat"], bbox["max_lon"], bbox["max_lat"]),
        )
        G = ox.convert.to_undirected(G)
        return _largest_component(G)

    raise RuntimeError(
        f"No pre-warmed graphml covers bbox {bbox}. "
        "Add the city to _CITY_BBOXES in osm_service.py and run prewarm_osm.py."
    )


def build_poi_index(G: nx.MultiGraph) -> Optional[STRtree]:
    """
    Build a shapely spatial search index (STRtree) of amenities and tourist attractions in G.
    """
    pois = []
    for n, d in G.nodes(data=True):
        if d.get("amenity") or d.get("tourism"):
            try:
                pois.append(Point(d["x"], d["y"]))
            except Exception:
                pass
    if not pois:
        return None
    return STRtree(pois)

def poi_density(edge_geom, poi_tree: Optional[STRtree], radius_deg: float = 0.0005) -> float:
    """
    Calculate POI density (0.0 to 1.0) along an edge geometry using a buffer search.
    """
    if not poi_tree:
        return 0.0
    buf = edge_geom.buffer(radius_deg)  # Approx 50m buffer
    count = len(poi_tree.query(buf))
    return min(1.0, count / 10.0)

# Discovery-potential score by highway type.
# Higher = more interesting/explorable for pedestrians.
_HIGHWAY_DISCOVERY: dict[str | None, float] = {
    "pedestrian":    0.95,  # plazas, pedestrianised zones
    "steps":         0.80,  # characterful urban features
    "footway":       0.70,  # dedicated foot paths
    "path":          0.65,  # trails, park paths
    "living_street": 0.65,  # slow mixed-use streets
    "secondary":     0.65,  # commercial corridors
    "tertiary":      0.55,  # neighbourhood high street
    "primary":       0.45,  # main roads (many shops but busy)
    "residential":   0.35,  # quiet residential
    "cycleway":      0.40,
    "trunk":         0.20,  # fast road, unpleasant for walking
    None:            0.50,
}


def _edge_discovery_score(data: dict) -> float:
    """
    Per-edge discovery potential (0–1) from OSM attributes.
    Uses highway type + named street bonus so explorers favour plazas and
    commercial corridors over unnamed residential back-alleys.
    """
    hw = data.get("highway")
    if isinstance(hw, list):
        hw = hw[0] if hw else None
    base = _HIGHWAY_DISCOVERY.get(hw, 0.50)

    # Named streets are more interesting than unnamed service lanes
    if data.get("name"):
        base = min(1.0, base + 0.10)

    # Explicit amenity / tourism tag on the edge is a strong signal
    if data.get("amenity") or data.get("tourism"):
        base = min(1.0, base + 0.15)

    return base


def assign_costs(G: nx.MultiGraph, edge_scores: dict, weights: dict) -> nx.MultiGraph:
    """
    Enrich graph edges with a custom walking 'cost' based on persona weights.
    Cost combines distance (speed), shade, nature, and discovery potential,
    modified by surface and highway-safety penalties.
    """
    w_speed = weights.get("w_speed", 0.25)
    w_shade = weights.get("w_shade", 0.35)
    w_nature = weights.get("w_nature", 0.25)
    w_discovery = weights.get("w_discovery", 0.15)

    for u, v, k, data in G.edges(keys=True, data=True):
        scores = edge_scores.get((u, v, k), {})
        length = data.get("length", 50.0)

        # 1. Microclimate costs
        shade_cost = 1.0 - scores.get("shade_score", 0.5)
        nature_cost = 1.0 - scores.get("veg_score", 0.3)

        # Discovery score from OSM edge attributes (highway type, named streets).
        # Replaces the previous node-based poi_tree which was always empty because
        # osmnx walk graphs only contain junction nodes, not amenity/tourism nodes.
        disc_score = _edge_discovery_score(data)
        scores["poi_density"] = disc_score   # stored so route.py can count it
        discovery_cost = 1.0 - disc_score

        # 2. Infrastructure penalties
        surf_type = data.get("surface")
        if isinstance(surf_type, list):
            surf_type = surf_type[0] if surf_type else None
        surface_penalty = SURFACE_PENALTY.get(surf_type, SURFACE_PENALTY[None])

        hw_type = data.get("highway")
        if isinstance(hw_type, list):
            hw_type = hw_type[0] if hw_type else None
        highway_safety = HIGHWAY_SAFETY.get(hw_type, HIGHWAY_SAFETY[None])

        climate_cost = (
            w_shade     * shade_cost
            + w_nature    * nature_cost
            + w_discovery * discovery_cost
        )
        infra_penalty = w_speed * (surface_penalty + highway_safety)

        G[u][v][k]["cost"] = max(0.001, (w_speed + climate_cost + infra_penalty) * length)

    return G

def nearest_node(G: nx.MultiGraph, lat: float, lon: float) -> int:
    """
    Return the nearest graph node to (lat, lon) using a vectorised haversine-approximation
    (Euclidean in degrees with cos-lat longitude correction).  Bypasses osmnx/scipy so
    results are consistent regardless of whether scipy is installed.
    """
    nodes = list(G.nodes(data=True))
    ids   = np.array([n        for n, _    in nodes], dtype=np.int64)
    ys    = np.array([d["y"]   for _, d    in nodes])   # latitude
    xs    = np.array([d["x"]   for _, d    in nodes])   # longitude
    cos_lat = np.cos(np.radians(lat))
    dists = (ys - lat) ** 2 + ((xs - lon) * cos_lat) ** 2
    nid = int(ids[np.argmin(dists)])
    nd = G.nodes[nid]
    logger.info(f"nearest_node query=({lat:.5f},{lon:.5f}) → node {nid} at ({nd['y']:.5f},{nd['x']:.5f})")
    return nid
