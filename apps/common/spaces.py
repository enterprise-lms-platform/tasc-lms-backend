import boto3
from botocore.config import Config
from django.conf import settings

def create_boto3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.DO_SPACES_ENDPOINT,  # https://lon1.digitaloceanspaces.com
        region_name=settings.DO_SPACES_REGION,     # lon1
        aws_access_key_id=settings.DO_SPACES_ACCESS_KEY_ID,
        aws_secret_access_key=settings.DO_SPACES_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
    )