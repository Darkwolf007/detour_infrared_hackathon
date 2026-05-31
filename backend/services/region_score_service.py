"""
Lazy per-region edge score cache backed by the Supabase region_edge_scores table.

On a cache miss the caller runs enrich_all_edges as normal, then calls
store_region_edge_scores (via FastAPI BackgroundTasks) to persist the scores.
On the next request to the same (city, time_slot, sdk_bbox cell) the scores
are returned instantly without touching the Infrared SDK or running grid sampling.
"""

import logging
from typing import Optional

from utils.db import get_supabase

logger = logging.getLogger("thermal_router.region_score_service")

BATCH_SIZE = 500

# Score column names and their fallback defaults
_SCORE_FIELDS: list[tuple[str, float]] = [
    ("utci_score",  0.5),
    ("raw_utci",    26.0),
    ("wind_score",  0.3),
    ("shade_score", 0.5),
    ("veg_score",   0.3),
]


def get_region_edge_scores(
    city: str,
    time_slot: str,
    bbox_key: str,
    edge_keys: set[tuple],
) -> Optional[dict[tuple, dict]]:
    """
    Look up pre-computed edge scores for (city, time_slot, bbox_key).

    edge_keys: set of (u, v, k) tuples from the DB-sourced graph for this
               request.  If the cached row count is less than the number of
               edges in the graph the cache is considered a partial miss and
               None is returned — this forces a full recompute so we never
               serve incomplete scores.

    Returns a dict matching enrich_all_edges output format:
        {(u, v, k): {utci_score, raw_utci, wind_score, shade_score, veg_score}}
    or None on miss.
    """
    if not edge_keys:
        return None

    sb = get_supabase()
    try:
        res = (
            sb.table("region_edge_scores")
            .select("u,v,k,utci_score,raw_utci,wind_score,shade_score,veg_score")
            .eq("city", city)
            .eq("time_slot", time_slot)
            .eq("bbox_key", bbox_key)
            .limit(10000)   # override Supabase default 1000-row cap
            .execute()
        )
        rows = res.data or []
    except Exception as exc:
        logger.warning("region_score_service: lookup failed (%s) — cache miss", exc)
        return None

    if not rows:
        logger.info("region_score_service: MISS for %s/%s — no cached rows", city, time_slot)
        return None

    # Build a set of cached (u,v,k) tuples and verify ALL current edges are covered.
    # A count-only check (len(rows) >= len(edge_keys)) is insufficient: the cached
    # rows may belong to a different sub-region that shares the same sdk_bbox key,
    # so edge (u,v,k) tuples in the current graph might not be present in the cache.
    cached_tuples = {(int(r["u"]), int(r["v"]), int(r["k"])) for r in rows}
    if not edge_keys.issubset(cached_tuples):
        logger.info(
            "region_score_service: MISS for %s/%s — %d cached, %d needed, %d uncovered",
            city, time_slot, len(cached_tuples), len(edge_keys),
            len(edge_keys - cached_tuples),
        )
        return None

    scores = {
        t: {field: float(r.get(field, default)) for field, default in _SCORE_FIELDS}
        for r in rows
        for t in [(int(r["u"]), int(r["v"]), int(r["k"]))]
        if t in edge_keys   # only return scores for edges in the current graph
    }
    logger.info(
        "region_score_service: HIT for %s/%s — %d/%d edges covered",
        city, time_slot, len(scores), len(edge_keys),
    )
    return scores


def store_region_edge_scores(
    city: str,
    time_slot: str,
    bbox_key: str,
    edge_scores: dict[tuple, dict],
) -> None:
    """
    Persist enrich_all_edges output to region_edge_scores for future requests.

    Intended to run via FastAPI BackgroundTasks (fire-and-forget) so it adds
    zero latency to the response that triggered the cache miss.

    Uses upsert so re-runs and concurrent writes are idempotent.
    """
    if not edge_scores:
        return

    sb = get_supabase()
    rows = []
    for (u, v, k), scores in edge_scores.items():
        rows.append({
            "city":      city,
            "time_slot": time_slot,
            "bbox_key":  bbox_key,
            "u":         int(u),
            "v":         int(v),
            "k":         int(k),
            **{field: float(scores.get(field, default)) for field, default in _SCORE_FIELDS},
        })

    try:
        for i in range(0, len(rows), BATCH_SIZE):
            sb.table("region_edge_scores").upsert(
                rows[i : i + BATCH_SIZE],
                on_conflict="city,time_slot,bbox_key,u,v,k",
            ).execute()
        logger.info(
            "region_score_service: stored %d scores for %s/%s",
            len(rows), city, time_slot,
        )
    except Exception as exc:
        logger.warning(
            "region_score_service: store failed (%s) — scores not cached, routing unaffected",
            exc,
        )
