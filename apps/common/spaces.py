import logging

import boto3
from botocore.config import Config
from django.conf import settings

logger = logging.getLogger(__name__)


def create_boto3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.DO_SPACES_ENDPOINT,  # https://lon1.digitaloceanspaces.com
        region_name=settings.DO_SPACES_REGION,     # lon1
        aws_access_key_id=settings.DO_SPACES_ACCESS_KEY_ID,
        aws_secret_access_key=settings.DO_SPACES_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )


def delete_spaces_object(bucket: str, key: str) -> bool:
    """Best-effort delete of a single object from DigitalOcean Spaces.

    Returns True on success, False on failure.  Failures are logged but
    never raised so callers can treat this as fire-and-forget.
    """
    try:
        client = create_boto3_client()
        client.delete_object(Bucket=bucket, Key=key)
        logger.info("Deleted Spaces object %s/%s", bucket, key)
        return True
    except Exception:
        logger.warning(
            "Failed to delete Spaces object %s/%s", bucket, key, exc_info=True
        )
        return False