import io
import json
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import boto3
from botocore.config import Config


# --------------------------------------------------
# 1. Read worker configuration
# --------------------------------------------------

SHARD_INDEX = int(os.environ["SHARD_INDEX"])
SHARD_COUNT = int(os.environ["SHARD_COUNT"])

if SHARD_COUNT < 1 or not 0 <= SHARD_INDEX < SHARD_COUNT:
    raise ValueError("Invalid SHARD_INDEX or SHARD_COUNT")

MODEL = os.getenv("TEACHER_MODEL", "phi3.5")

OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://host.k3d.internal:11434/api/generate"
)

S3_ENDPOINT = os.environ["S3_ENDPOINT"]
S3_BUCKET = os.getenv("S3_BUCKET", "datasets")
INPUT_KEY = os.getenv("INPUT_KEY", "commands_pool.jsonl")

OUTPUT_KEY = os.getenv(
    "OUTPUT_KEY",
    f"teacher/shard-{SHARD_INDEX}.jsonl"
)

MAX_SHARD_RECORDS = int(os.getenv("MAX_SHARD_RECORDS", "0"))

PROMPT_PATH = Path("/app/prompts/teacher_prompt.txt")
SCHEMA_PATH = Path("/app/data/schema.json")

TEMPERATURE = 0
SEED = 42
NUM_CTX = 2048


# --------------------------------------------------
# 2. Initialize S3 client
# --------------------------------------------------

s3 = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
    aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    config=Config(
        signature_version="s3v4",
        s3={"addressing_style": "path"},
        retries={"max_attempts": 5, "mode": "standard"}
    )
)


# --------------------------------------------------
# 3. Load prompt and JSON schema
# --------------------------------------------------

prompt_template = PROMPT_PATH.read_text(
    encoding="utf-8"
).strip()

schema_document = json.loads(
    SCHEMA_PATH.read_text(encoding="utf-8")
)

OUTPUT_SCHEMA = schema_document["json_schema"]


# --------------------------------------------------
# 4. Call Phi-3.5 through Ollama
# --------------------------------------------------

def call_teacher(command):

    prompt = prompt_template + "\n" + command

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "format": OUTPUT_SCHEMA,
        "stream": False,
        "keep_alive": "10m",
        "options": {
            "temperature": TEMPERATURE,
            "seed": SEED,
            "num_ctx": NUM_CTX
        }
    }

    request = Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    for attempt in range(1, 4):

        try:
            with urlopen(request, timeout=600) as response:
                result = json.loads(
                    response.read().decode("utf-8")
                )

            if "error" in result:
                raise RuntimeError(result["error"])

            teacher_raw = result["response"]

            if not isinstance(teacher_raw, str):
                raise ValueError("Teacher response is not text")

            # Return the exact generated response.
            # Do not parse, repair or modify it here.
            return teacher_raw

        except (HTTPError, URLError, TimeoutError) as error:
            print(
                f"Teacher request failed "
                f"(attempt {attempt}/3): {error}",
                flush=True
            )

            if attempt == 3:
                raise

            time.sleep(2 ** attempt)

    raise RuntimeError("Teacher inference failed")


# --------------------------------------------------
# 5. Download the original command dataset
# --------------------------------------------------

def download_commands():

    response = s3.get_object(
        Bucket=S3_BUCKET,
        Key=INPUT_KEY
    )

    content = response["Body"].read().decode("utf-8")

    records = []

    for line_number, line in enumerate(content.splitlines()):

        if not line.strip():
            continue

        record = json.loads(line)

        if not isinstance(record, dict):
            raise ValueError(
                f"Invalid record at line {line_number}"
            )

        if not isinstance(record.get("id"), str):
            raise ValueError(
                f"Missing ID at line {line_number}"
            )

        if not isinstance(record.get("text"), str):
            raise ValueError(
                f"Missing text at line {line_number}"
            )

        records.append((line_number, record))

    print(
        f"Downloaded {len(records)} command records.",
        flush=True
    )

    return records


# --------------------------------------------------
# 6. Process this worker's assigned shard
# --------------------------------------------------

def process_shard(records):

    output = io.StringIO()
    processed = 0

    for line_number, record in records:

        # Zero-based line-number sharding
        if line_number % SHARD_COUNT != SHARD_INDEX:
            continue

        teacher_raw = call_teacher(record["text"])

        output_record = {
            "id": record["id"],
            "text": record["text"],
            "teacher_raw": teacher_raw
        }

        output.write(
            json.dumps(output_record, ensure_ascii=False) + "\n"
        )

        processed += 1

        if processed % 10 == 0:
            print(
                f"Worker {SHARD_INDEX}: "
                f"{processed} commands processed",
                flush=True
            )

        # Optional smoke-test limit.
        # Leave this unset for the full assignment run.
        if (
            MAX_SHARD_RECORDS > 0
            and processed >= MAX_SHARD_RECORDS
        ):
            break

    return output.getvalue(), processed


# --------------------------------------------------
# 7. Upload this worker's independent shard
# --------------------------------------------------

def upload_shard(content):

    s3.put_object(
        Bucket=S3_BUCKET,
        Key=OUTPUT_KEY,
        Body=content.encode("utf-8"),
        ContentType="application/x-ndjson"
    )

    print(
        f"Uploaded s3://{S3_BUCKET}/{OUTPUT_KEY}",
        flush=True
    )


# --------------------------------------------------
# 8. Main execution
# --------------------------------------------------

def main():

    print(
        f"Starting worker: shard={SHARD_INDEX}, "
        f"count={SHARD_COUNT}",
        flush=True
    )

    records = download_commands()

    content, processed = process_shard(records)

    upload_shard(content)

    print(
        f"Worker {SHARD_INDEX} completed. "
        f"Records processed: {processed}",
        flush=True
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"WORKER FAILED: {error}", file=sys.stderr, flush=True)
        sys.exit(1)
