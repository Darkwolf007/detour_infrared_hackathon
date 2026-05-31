"""
Build a NetworkX MultiGraph from the Supabase osm_edges table.

Replaces get_walk_graph_cached() for the DB-backed path.  Returns None when
no edges are found so the caller can fall back to the graphml path gracefully.
"""

import logging
from typing import Optional

import networkx as nx
from shapely import wkt as shapely_wkt
from shapely.geometry import LineString

from utils.db import get_supabase

logger = logging.getLogger("thermal_router.graph_db_service")


def build_graph_from_db(city: str, bbox: dict) -> Optional[nx.MultiGraph]:
    """
    Query osm_edges for all edges whose geometry intersects bbox, then
    construct a minimal nx.MultiGraph compatible with the rest of the pipeline.

    Node attributes: x (lon), y (lat)  — same convention as osm_service.
    Edge attributes: geometry (LineString), length, highway, surface, name,
                     amenity, tourism — same fields assign_costs and
                     enrich_all_edges read.

    Returns None if the table has no rows for this city/bbox (triggers
    fallback to get_walk_graph_cached in the caller).
    """
    sb = get_supabase()
    rpc_params = {
        "p_city":    city.lower(),
        "p_min_lon": bbox["min_lon"],
        "p_min_lat": bbox["min_lat"],
        "p_max_lon": bbox["max_lon"],
        "p_max_lat": bbox["max_lat"],
    }

    # Supabase PostgREST caps RPC results at 1000 rows by default.
    # .limit() alone doesn't reliably override this for RPCs, so we
    # paginate with .range() to fetch all edges in the bbox.
    PAGE_SIZE = 1000
    rows: list[dict] = []
    try:
        offset = 0
        while True:
            res = (
                sb.rpc("get_osm_edges_in_bbox", rpc_params)
                .range(offset, offset + PAGE_SIZE - 1)
                .execute()
            )
            page = res.data or []
            rows.extend(page)
            if len(page) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
    except Exception as exc:
        logger.warning("graph_db_service: Supabase RPC failed (%s) — returning None", exc)
        return None

    if not rows:
        logger.info("graph_db_service: no rows for %s in bbox %s", city, bbox)
        return None

    G = nx.MultiGraph()

    for row in rows:
        u = int(row["u"])
        v = int(row["v"])
        k = int(row["k"])

        if u not in G:
            G.add_node(u, x=float(row["u_lon"]), y=float(row["u_lat"]))
        if v not in G:
            G.add_node(v, x=float(row["v_lon"]), y=float(row["v_lat"]))

        geom_wkt = row.get("geom_wkt") or ""
        try:
            geom = shapely_wkt.loads(geom_wkt) if geom_wkt else None
        except Exception:
            geom = None

        if geom is None:
            geom = LineString([
                (float(row["u_lon"]), float(row["u_lat"])),
                (float(row["v_lon"]), float(row["v_lat"])),
            ])

        G.add_edge(u, v, k,
            geometry=geom,
            length=float(row.get("length_m") or 50.0),
            highway=row.get("highway") or None,
            surface=row.get("surface") or None,
            name=row.get("name") or None,
            amenity=row.get("amenity") or None,
            tourism=row.get("tourism") or None,
            cost=1.0,  # placeholder — assign_costs overwrites this
        )

    logger.info(
        "graph_db_service: built graph for %s — %d nodes, %d edges",
        city, G.number_of_nodes(), G.number_of_edges(),
    )

    # Keep only the largest connected component (mirrors get_walk_graph_cached)
    if not nx.is_connected(G):
        largest = max(nx.connected_components(G), key=len)
        before = G.number_of_nodes()
        G = G.subgraph(largest).copy()
        logger.info(
            "graph_db_service: kept largest component %d/%d nodes",
            G.number_of_nodes(), before,
        )

    return G
