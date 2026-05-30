"""
One-time upload of local graphml cache files to Cloudflare R2.

Run once from the backend directory after prewarm_osm.py has populated _osm_cache/:
    python upload_graphml.py

Requires in .env:
    R2_ACCOUNT_ID, R2_ACCESS_KEY, R2_SECRET_KEY
    R2_BUCKET  (optional, default: graphml-cache)
"""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config

from services.osm_service import _CITY_BBOXES, _graph_cache_path

# 50 MB parts — R2 multipart minimum is 5 MB, max 10 000 parts
_TRANSFER = TransferConfig(multipart_threshold=50 * 1024 ** 2, multipart_chunksize=50 * 1024 ** 2)

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")
logger = logging.getLogger("upload_graphml")

BUCKET = os.environ.get("R2_BUCKET", "graphml-cache")


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


def main() -> None:
    client = _r2_client()

    # Create bucket if it doesn't exist
    existing = [b["Name"] for b in client.list_buckets().get("Buckets", [])]
    if BUCKET not in existing:
        client.create_bucket(Bucket=BUCKET)
        logger.info(f"Created R2 bucket '{BUCKET}'")

    for city, bbox in _CITY_BBOXES.items():
        local_path = _graph_cache_path(bbox)
        if not os.path.exists(local_path):
            logger.error(f"{city}: local graphml not found at {local_path} — run prewarm_osm.py first")
            continue

        size_mb = os.path.getsize(local_path) / 1_048_576
        remote_name = f"{city}.graphml"
        logger.info(f"{city}: uploading {size_mb:.1f} MB as '{remote_name}' …")
        try:
            client.upload_file(local_path, BUCKET, remote_name, Config=_TRANSFER)
            logger.info(f"{city}: uploaded ✓")
        except Exception as e:
            logger.error(f"{city}: upload failed — {e}")


if __name__ == "__main__":
    main()
