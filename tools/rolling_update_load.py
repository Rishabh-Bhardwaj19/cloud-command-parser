import argparse
import collections
import concurrent.futures
import csv
import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--duration", type=int, default=100)
parser.add_argument("--workers", type=int, default=4)
args = parser.parse_args()

URL = "http://127.0.0.1:8080/parse"
deadline = time.monotonic() + args.duration
rows = []
lock = threading.Lock()


def worker(worker_id):
    sequence = 0

    while time.monotonic() < deadline:
        sequence += 1
        payload = json.dumps({
            "text": "Set an alarm for seven am tomorrow"
        }).encode("utf-8")

        request = urllib.request.Request(
            URL,
            data=payload,
            headers={
                "Host": "parser.local",
                "Content-Type": "application/json",
                "Connection": "close"
            },
            method="POST"
        )

        status = 0
        version = "UNKNOWN"
        pod = "UNKNOWN"
        body = ""

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                status = response.status
                version = response.headers.get("X-Model-Version", "UNKNOWN")
                pod = response.headers.get("X-Served-By", "UNKNOWN")
                body = response.read().decode("utf-8")

        except urllib.error.HTTPError as error:
            status = error.code
            version = error.headers.get("X-Model-Version", "UNKNOWN")
            pod = error.headers.get("X-Served-By", "UNKNOWN")
            body = error.read().decode("utf-8")

        except Exception as error:
            body = str(error)

        record = {
            "worker": worker_id,
            "sequence": sequence,
            "http_status": status,
            "model_version": version,
            "served_by": pod,
            "response": body
        }

        with lock:
            rows.append(record)

        time.sleep(0.05)


with concurrent.futures.ThreadPoolExecutor(
    max_workers=args.workers
) as executor:
    futures = [
        executor.submit(worker, worker_id)
        for worker_id in range(1, args.workers + 1)
    ]
    for future in futures:
        future.result()

rows.sort(key=lambda row: (row["worker"], row["sequence"]))

output = Path("results/rolling_update_load.csv")
with output.open("w", newline="", encoding="utf-8") as file:
    writer = csv.DictWriter(
        file,
        fieldnames=[
            "worker", "sequence", "http_status",
            "model_version", "served_by", "response"
        ]
    )
    writer.writeheader()
    writer.writerows(rows)

successful = [row for row in rows if row["http_status"] == 200]
failed = [row for row in rows if row["http_status"] != 200]

versions = collections.Counter(
    row["model_version"] for row in successful
)
pods = collections.Counter(
    row["served_by"] for row in successful
)
errors = collections.Counter(
    str(row["http_status"]) for row in failed
)

report = {
    "duration_seconds": args.duration,
    "concurrent_workers": args.workers,
    "total_requests": len(rows),
    "successful_requests": len(successful),
    "failed_requests": len(failed),
    "http_error_counts": dict(errors),
    "model_version_distribution": dict(versions),
    "pod_distribution": dict(pods)
}

Path("results/rolling_update_report.json").write_text(
    json.dumps(report, indent=2),
    encoding="utf-8"
)

print("\n=== ROLLING UPDATE LOAD REPORT ===")
print(json.dumps(report, indent=2))
print("\nEvidence saved:")
print(output)
print("results/rolling_update_report.json")
