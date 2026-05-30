"""
Download pre-warmed city graphml files from Cloudflare R2 on startup.

Files are stored in the R2 bucket as {city}.graphml.
Only downloads if the local cache file is missing — no-op on warm containers.

Required env vars:
    R2_ACCOUNT_ID   — Cloudflare account ID
    R2_ACCESS_KEY   — R2 API token access key ID
    R2_SECRET_KEY   — R2 API token secret access key
    R2_BUCKET       — bucket name (default: graphml-cache)
"""

import logging
import os
from functools import lru_cache

import boto3
from botocore.config import Config

from services.osm_service import _CITY_BBOXES, _graph_cache_path

logger = logging.getLogger("thermal_router.graphml_sync")


@lru_cache(maxsize=1)
def _r2_client():
    account_id = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY"],
        aws_secret_access_key=os.environ["R2_SECRET_KEY"],
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def sync_graphml() -> None:
    """Download any missing city graphml files from R2."""
    bucket = os.environ.get("R2_BUCKET", "graphml-cache")
    os.makedirs(os.path.join(os.path.dirname(__file__), "..", "_osm_cache"), exist_ok=True)

    for city, bbox in _CITY_BBOXES.items():
        local_path = _graph_cache_path(bbox)
        if os.path.exists(local_path):
            logger.info(f"graphml sync: {city} already cached locally — skipping")
            continue

        logger.info(f"graphml sync: downloading {city}.graphml from R2 …")
        try:
            _r2_client().download_file(bucket, f"{city}.graphml", local_path)
            size_mb = os.path.getsize(local_path) / 1_048_576
            logger.info(f"graphml sync: {city} saved ({size_mb:.1f} MB) → {local_path}")
        except Exception as e:
            logger.error(f"graphml sync: failed to download {city}.graphml — {e}")
