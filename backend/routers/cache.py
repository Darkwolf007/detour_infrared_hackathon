from fastapi import APIRouter, HTTPException

from services.cache_service import get_cache_stats

router = APIRouter(tags=["cache"])


@router.get("/cache/status")
def cache_status():
    """Return live vs expired row counts for the SDK cache."""
    try:
        return get_cache_stats()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Cache unavailable: {exc}")
