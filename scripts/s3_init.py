"""Initialize SeaweedFS buckets and upload project datasets and models."""

import argparse
import time
from pathlib import Path

import boto3
from botocore.config import Config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-v1", required=True)
    parser.add_argument("--model-v2", required=True)
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument("--prompt", required=True)
    args = parser.parse_args()

    endpoint = "http://127.0.0.1:8333"
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name="us-east-1",
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"}
        )
    )

    # Wait for the S3 API to accept authenticated requests.
    last_error = None
    for attempt in range(30):
        try:
            client.list_buckets()
            break
        except Exception as error:
            last_error = error
            if attempt == 29:
                raise RuntimeError(
                    "SeaweedFS S3 did not become available."
                ) from last_error
            time.sleep(2)

    for bucket in ("datasets", "models"):
        try:
            client.head_bucket(Bucket=bucket)
        except Exception:
            client.create_bucket(Bucket=bucket)
            print(f"Created bucket: {bucket}")

    def upload_file(path, bucket, key):
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(path)
        client.upload_file(str(path), bucket, key)
        print(f"Uploaded s3://{bucket}/{key}")

    def upload_directory(directory, bucket, prefix):
        directory = Path(directory)
        if not directory.is_dir():
            raise FileNotFoundError(directory)

        files = sorted(path for path in directory.rglob("*") if path.is_file())
        if not files:
            raise RuntimeError(f"No files found in {directory}")

        for path in files:
            key = prefix.rstrip("/") + "/" + path.relative_to(directory).as_posix()
            upload_file(path, bucket, key)

    root = Path(args.dataset_root)

    dataset_files = [
        (root / "commands_pool.jsonl", "commands_pool.jsonl"),
        (root / "validation.jsonl", "validation.jsonl"),
        (root / "schema.json", "schema.json"),
        (root / "rate_card.json", "rate_card.json"),
        (root / "v1" / "train.jsonl", "v1/train.jsonl"),
        (root / "v1" / "train.sha256", "v1/train.sha256"),
        (Path(args.prompt), "teacher_prompt.txt"),
    ]

    for local_path, object_key in dataset_files:
        upload_file(local_path, "datasets", object_key)

    upload_directory(args.model_v1, "models", "v1")
    upload_directory(args.model_v2, "models", "v2")

    print("SeaweedFS initialization and uploads completed.")


if __name__ == "__main__":
    main()
