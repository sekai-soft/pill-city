import os
from typing import Tuple

import boto3


def get_s3_client() -> Tuple[any, str]:
    s3_client = boto3.client(
        "s3",
        endpoint_url=os.environ["S3_URL"],
        region_name=os.environ["S3_REGION"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
    )
    s3_bucket_name = os.environ["S3_BUCKET_NAME"]
    return s3_client, s3_bucket_name
