"""
One-time script to load all pre-warmed city OSM graphs into the Supabase
osm_edges table.  Run from the backend directory after graphml files are
present in _osm_cache/ (i.e. after prewarm_osm.py or sync from R2):

    python load_osm_to_supabase.py

Idempotent — uses upsert with on_conflict="city,u,v,k" so re-runs are safe.
Start with --city chennai to validate before loading larger cities.

Usage:
    python load_osm_to_supabase.py [--city CITY]

    --city   Only load the named city (barcelona | dubai | chennai).
             Omit to load all three.
"""

import argparse
import logging
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))

from shapely.geometry import LineString
from services.osm_service import _CITY_BBOXES, get_walk_graph_cached
from utils.db import get_supabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
)
logger = logging.getLogger("load_osm")

BATCH_SIZE = 500


def _first(value):
    """Return the first element if value is a list, else value itself."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _edge_geom(u, v, data, G) -> LineString:
    """Return edge geometry as a Shapely LineString."""
    geom = data.get("geometry")
    if geom is not None and hasattr(geom, "wkt"):
        return geom
    return LineString([
        (G.nodes[u]["x"], G.nodes[u]["y"]),
        (G.nodes[v]["x"], G.nodes[v]["y"]),
    ])


def load_city(city: str) -> None:
    t0 = time.monotonic()
    bbox = _CITY_BBOXES[city]
    logger.info("Loading OSM graph for %s …", city)
    G = get_walk_graph_cached(bbox)
    n_edges = G.number_of_edges()
    logger.info("  %s: %d nodes, %d edges — building rows …", city, G.number_of_nodes(), n_edges)

    sb = get_supabase()
    batch: list[dict] = []
    total_upserted = 0

    for idx, (u, v, k, data) in enumerate(G.edges(keys=True, data=True)):
        geom_obj = _edge_geom(u, v, data, G)
        batch.append({
            "city":     city,
            "u":        int(u),
            "v":        int(v),
            "k":        int(k),
            "u_lon":    float(G.nodes[u]["x"]),
            "u_lat":    float(G.nodes[u]["y"]),
            "v_lon":    float(G.nodes[v]["x"]),
            "v_lat":    float(G.nodes[v]["y"]),
            "geom":     f"SRID=4326;{geom_obj.wkt}",
            "geom_wkt": geom_obj.wkt,
            "length_m": float(data.get("length") or 50.0),
            "highway":  _first(data.get("highway")),
            "surface":  _first(data.get("surface")),
            "name":     _first(data.get("name")),
            "amenity":  _first(data.get("amenity")),
            "tourism":  _first(data.get("tourism")),
            "lit":      _first(data.get("lit")),
            "foot":     _first(data.get("foot")),
        })

        if len(batch) >= BATCH_SIZE:
            sb.table("osm_edges").upsert(batch, on_conflict="city,u,v,k").execute()
            total_upserted += len(batch)
            batch = []
            if total_upserted % 5000 == 0:
                pct = total_upserted / n_edges * 100
                logger.info("  %s: %d / %d edges (%.0f%%)", city, total_upserted, n_edges, pct)

    if batch:
        sb.table("osm_edges").upsert(batch, on_conflict="city,u,v,k").execute()
        total_upserted += len(batch)

    elapsed = time.monotonic() - t0
    logger.info("  %s: done — %d edges in %.1fs", city, total_upserted, elapsed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load city OSM graphs into Supabase osm_edges table")
    parser.add_argument("--city", choices=list(_CITY_BBOXES.keys()),
                        help="Load only this city (default: all)")
    args = parser.parse_args()

    cities = [args.city] if args.city else list(_CITY_BBOXES.keys())
    logger.info("Will load: %s", cities)

    for city in cities:
        try:
            load_city(city)
        except Exception as exc:
            logger.error("Failed to load %s: %s", city, exc, exc_info=True)
            sys.exit(1)

    logger.info("All done.")


if __name__ == "__main__":
    main()
