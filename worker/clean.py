import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


# --------------------------------------------------
# 1. Configuration
# --------------------------------------------------

S3_ENDPOINT = os.getenv(
    "S3_ENDPOINT", "http://127.0.0.1:8333"
)

S3_BUCKET = os.getenv("S3_BUCKET", "datasets")
SHARD_COUNT = int(os.getenv("SHARD_COUNT", "2"))

SOURCE_KEY = "commands_pool.jsonl"
SHARD_PREFIX = "teacher"
OUTPUT_PREFIX = "v1"

EXPECTED_KEYS = {"intent", "date", "time", "place"}

ALLOWED_INTENTS = {
    "alarm_set",
    "alarm_query",
    "calendar_set",
    "calendar_query",
    "calendar_remove",
    "weather_query",
    "datetime_query",
    "recommendation_events"
}


# --------------------------------------------------
# 2. AWS CLI helper
# --------------------------------------------------

def aws_s3(*args):
    command = [
        "aws",
        "--endpoint-url", S3_ENDPOINT,
        *args
    ]

    subprocess.run(command, check=True)


# --------------------------------------------------
# 3. Read JSONL
# --------------------------------------------------

def read_jsonl(path):

    records = []

    with open(path, encoding="utf-8") as file:

        for line_number, line in enumerate(file):

            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Malformed JSONL at {path}:{line_number + 1}"
                ) from error

            if not isinstance(record, dict):
                raise ValueError(
                    f"Expected JSON object at {path}:{line_number + 1}"
                )

            records.append((line_number, record))

    return records


# --------------------------------------------------
# 4. Download original dataset and teacher shards
# --------------------------------------------------

def download_inputs(temp_dir):

    source_path = temp_dir / "commands_pool.jsonl"

    aws_s3(
        "s3", "cp",
        f"s3://{S3_BUCKET}/{SOURCE_KEY}",
        str(source_path)
    )

    source_records = read_jsonl(source_path)

    source_by_id = {}

    for line_number, record in source_records:

        if set(record) != {"id", "text"}:
            raise ValueError("Unexpected original dataset structure.")

        record_id = record["id"]
        text = record["text"]

        if not isinstance(record_id, str) or not isinstance(text, str):
            raise ValueError("Invalid source ID or text.")

        if record_id in source_by_id:
            raise ValueError(f"Duplicate source ID: {record_id}")

        source_by_id[record_id] = (text, line_number)

    all_records = []
    shard_counts = {}

    for shard_index in range(SHARD_COUNT):

        key = f"{SHARD_PREFIX}/shard-{shard_index}.jsonl"
        local_path = temp_dir / f"shard-{shard_index}.jsonl"

        aws_s3(
            "s3", "cp",
            f"s3://{S3_BUCKET}/{key}",
            str(local_path)
        )

        shard_records = read_jsonl(local_path)
        shard_counts[shard_index] = len(shard_records)

        for _, record in shard_records:

            if set(record) != {"id", "text", "teacher_raw"}:
                raise ValueError(
                    f"Invalid worker record in {key}"
                )

            record_id = record["id"]

            if record_id not in source_by_id:
                raise ValueError(f"Unknown source ID: {record_id}")

            original_text, original_line = source_by_id[record_id]

            if record["text"] != original_text:
                raise ValueError(
                    f"Command text mismatch for {record_id}"
                )

            if original_line % SHARD_COUNT != shard_index:
                raise ValueError(
                    f"Wrong shard assignment for {record_id}"
                )

            all_records.append(record)

    # Verify that every original command appears exactly once.
    all_ids = [record["id"] for record in all_records]

    if len(all_ids) != len(set(all_ids)):
        raise ValueError("Repeated command IDs across shards.")

    if set(all_ids) != set(source_by_id):
        missing = set(source_by_id) - set(all_ids)
        raise ValueError(
            f"Missing command IDs: {len(missing)}"
        )

    # Verify expected shard sizes.
    for shard_index in range(SHARD_COUNT):

        expected_count = sum(
            1 for line_number, record in source_records
            if line_number % SHARD_COUNT == shard_index
        )

        if shard_counts[shard_index] != expected_count:
            raise ValueError(
                f"Shard {shard_index} has an unexpected record count."
            )

    print("\nSource records:", len(source_records))
    print("Shard records:", len(all_records))

    for index, count in shard_counts.items():
        print(f"Shard {index}: {count} records")

    print("Shard coverage: VERIFIED")

    return source_records, all_records


# --------------------------------------------------
# 5. Validate teacher responses
# --------------------------------------------------

def clean_records(records):

    rejected = {
        "a_invalid_json": 0,
        "b_incorrect_keys": 0,
        "c_invalid_intent": 0,
        "d_invalid_slots": 0
    }

    valid_records = []

    for record in records:

        raw = record["teacher_raw"]

        # (a) Teacher reply must be valid JSON.
        try:
            teacher = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            rejected["a_invalid_json"] += 1
            continue

        # (b) Exactly four keys are required.
        if not isinstance(teacher, dict) or set(teacher) != EXPECTED_KEYS:
            rejected["b_incorrect_keys"] += 1
            continue

        # (c) Intent must belong to the allowed eight.
        if (
            not isinstance(teacher["intent"], str)
            or teacher["intent"] not in ALLOWED_INTENTS
        ):
            rejected["c_invalid_intent"] += 1
            continue

        # (d) Every slot must be null or meaningful text
        # appearing exactly in the original command.
        invalid_slot = False

        for slot in ("date", "time", "place"):

            value = teacher[slot]

            if value is None:
                continue

            if (
                not isinstance(value, str)
                or not value.strip()
                or value not in record["text"]
            ):
                invalid_slot = True
                break

        if invalid_slot:
            rejected["d_invalid_slots"] += 1
            continue

        valid_records.append(record)

    # --------------------------------------------------
    # 6. Remove duplicate commands.
    # Keep the record with the smallest ID.
    # --------------------------------------------------

    valid_records.sort(key=lambda r: r["id"])

    seen_texts = set()
    final_records = []
    duplicates = 0

    for record in valid_records:

        command_text = record["text"]

        if command_text in seen_texts:
            duplicates += 1
            continue

        seen_texts.add(command_text)
        final_records.append(record)

    return final_records, rejected, duplicates


# --------------------------------------------------
# 7. Save dataset and SHA-256 checksum
# --------------------------------------------------

def save_outputs(final_records, rejected, duplicates, input_count):

    data_dir = Path("data/v1")
    results_dir = Path("results")

    data_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    train_path = data_dir / "train.jsonl"
    checksum_path = data_dir / "train.sha256"
    report_path = results_dir / "cleaning_report.json"

    # Preserve teacher_raw exactly as generated.
    train_bytes = "".join(
        json.dumps(record, ensure_ascii=False) + "\n"
        for record in final_records
    ).encode("utf-8")

    train_path.write_bytes(train_bytes)

    checksum = hashlib.sha256(train_bytes).hexdigest()

    checksum_path.write_text(
        f"{checksum}  train.jsonl\n",
        encoding="utf-8"
    )

    rejected_total = sum(rejected.values())
    kept = len(final_records)

    assert (
        input_count
        == rejected_total + duplicates + kept
    ), "Cleaning accounting does not balance!"

    report = {
        "input_records": input_count,
        "rejected": rejected,
        "duplicates": duplicates,
        "kept": kept,
        "accounting_total": rejected_total + duplicates + kept,
        "sha256": checksum
    }

    report_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8"
    )

    print("\n========== CLEANING REPORT ==========")
    print("Input records:", input_count)

    for reason, count in rejected.items():
        print(f"{reason}: {count}")

    print("Duplicates:", duplicates)
    print("Records kept:", kept)

    print("\nAccounting check:")
    print(
        f"{input_count} = {rejected_total} + "
        f"{duplicates} + {kept}"
    )

    print("SHA-256:", checksum)
    print("Local dataset:", train_path)
    print("Local checksum:", checksum_path)
    print("Report:", report_path)

    return train_path, checksum_path


# --------------------------------------------------
# 8. Upload final artefacts to SeaweedFS
# --------------------------------------------------

def upload_outputs(train_path, checksum_path):

    aws_s3(
        "s3", "cp",
        str(train_path),
        f"s3://{S3_BUCKET}/{OUTPUT_PREFIX}/train.jsonl"
    )

    aws_s3(
        "s3", "cp",
        str(checksum_path),
        f"s3://{S3_BUCKET}/{OUTPUT_PREFIX}/train.sha256"
    )

    print("\nUploaded final dataset and checksum to SeaweedFS.")


# --------------------------------------------------
# 9. Main execution
# --------------------------------------------------

def main():

    if SHARD_COUNT < 1:
        raise ValueError("SHARD_COUNT must be at least 1")

    if not os.environ.get("AWS_ACCESS_KEY_ID"):
        raise RuntimeError("AWS_ACCESS_KEY_ID is not set")

    if not os.environ.get("AWS_SECRET_ACCESS_KEY"):
        raise RuntimeError("AWS_SECRET_ACCESS_KEY is not set")

    with tempfile.TemporaryDirectory(
        prefix="teacher-clean-"
    ) as temporary:

        temp_dir = Path(temporary)

        _, records = download_inputs(temp_dir)

        final_records, rejected, duplicates = clean_records(records)

        train_path, checksum_path = save_outputs(
            final_records,
            rejected,
            duplicates,
            len(records)
        )

        upload_outputs(train_path, checksum_path)

    print("\nTASK 1 CLEANING COMPLETED SUCCESSFULLY.")


if __name__ == "__main__":

    try:
        main()
    except Exception as error:
        print(f"\nCLEANING FAILED: {error}", file=sys.stderr)
        sys.exit(1)
