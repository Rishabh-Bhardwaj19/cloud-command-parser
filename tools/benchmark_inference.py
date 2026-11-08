import collections
import csv
import json
import math
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TOTAL = 50
URL = "http://127.0.0.1:8080/parse"

ALLOWED_INTENTS = {
    "alarm_set", "alarm_query", "calendar_set",
    "calendar_query", "calendar_remove", "weather_query",
    "datetime_query", "recommendation_events"
}
EXPECTED_KEYS = {"intent", "date", "time", "place"}

latencies = []
rows = []
memory_samples = []
stop_monitor = threading.Event()


def to_mib(value):
    if value.endswith("Ki"):
        return float(value[:-2]) / 1024
    if value.endswith("Mi"):
        return float(value[:-2])
    if value.endswith("Gi"):
        return float(value[:-2]) * 1024
    if value.endswith("Ti"):
        return float(value[:-2]) * 1024 * 1024
    return float(value)


def sample_memory():
    try:
        result = subprocess.run(
            [
                "kubectl", "top", "pods", "-n", "app",
                "-l", "app=command-parser", "--no-headers"
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False
        )

        if result.returncode != 0:
            return

        timestamp = datetime.now(timezone.utc).isoformat()

        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) >= 3:
                memory_mib = to_mib(fields[2])
                memory_samples.append({
                    "timestamp": timestamp,
                    "pod": fields[0],
                    "memory_mib": round(memory_mib, 2)
                })

    except Exception as error:
        print("Memory sampling warning:", error)


def monitor_memory():
    while not stop_monitor.is_set():
        sample_memory()
        stop_monitor.wait(1)


def valid_schema(result):
    return (
        isinstance(result, dict)
        and set(result.keys()) == EXPECTED_KEYS
        and isinstance(result["intent"], str)
        and result["intent"] in ALLOWED_INTENTS
        and all(
            result[slot] is None or isinstance(result[slot], str)
            for slot in ("date", "time", "place")
        )
    )


print("Starting memory monitor...")
monitor = threading.Thread(target=monitor_memory, daemon=True)
monitor.start()

started = time.perf_counter()

for index in range(1, TOTAL + 1):
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

    request_started = time.perf_counter()
    status = 0
    pod = "UNKNOWN"
    version = "UNKNOWN"
    body = ""
    valid = False

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            status = response.status
            pod = response.headers.get("X-Served-By", "UNKNOWN")
            version = response.headers.get("X-Model-Version", "UNKNOWN")
            body = response.read().decode("utf-8")

    except urllib.error.HTTPError as error:
        status = error.code
        pod = error.headers.get("X-Served-By", "UNKNOWN")
        version = error.headers.get("X-Model-Version", "UNKNOWN")
        body = error.read().decode("utf-8")

    except Exception as error:
        body = str(error)

    latency_ms = (time.perf_counter() - request_started) * 1000
    latencies.append(latency_ms)

    try:
        valid = valid_schema(json.loads(body))
    except (json.JSONDecodeError, TypeError):
        valid = False

    rows.append({
        "request": index,
        "http_status": status,
        "latency_ms": round(latency_ms, 2),
        "model_version": version,
        "served_by": pod,
        "valid_schema": valid,
        "response": body
    })

    if index % 10 == 0:
        print(f"Completed {index}/{TOTAL} requests")

elapsed = time.perf_counter() - started

sample_memory()
stop_monitor.set()
monitor.join(timeout=3)

successful = [row for row in rows if row["http_status"] == 200]
failed = [row for row in rows if row["http_status"] != 200]
valid_count = sum(row["valid_schema"] for row in successful)

sorted_latencies = sorted(latencies)


def percentile(values, percentile_value):
    if not values:
        return None
    index = max(0, math.ceil(percentile_value * len(values)) - 1)
    return round(values[index], 2)


pod_distribution = collections.Counter(
    row["served_by"] for row in successful
)
version_distribution = collections.Counter(
    row["model_version"] for row in successful
)
status_distribution = collections.Counter(
    str(row["http_status"]) for row in rows
)

peak_by_pod = {}
for sample in memory_samples:
    pod = sample["pod"]
    peak_by_pod[pod] = max(
        peak_by_pod.get(pod, 0),
        sample["memory_mib"]
    )

report = {
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "total_requests": TOTAL,
    "successful_requests": len(successful),
    "failed_requests": len(failed),
    "valid_schema_responses": valid_count,
    "http_status_distribution": dict(status_distribution),
    "duration_seconds": round(elapsed, 3),
    "throughput_requests_per_second": round(TOTAL / elapsed, 3),
    "latency_ms": {
        "minimum": round(min(latencies), 2),
        "average": round(sum(latencies) / len(latencies), 2),
        "p50": percentile(sorted_latencies, 0.50),
        "p95": percentile(sorted_latencies, 0.95),
        "maximum": round(max(latencies), 2)
    },
    "model_version_distribution": dict(version_distribution),
    "pod_distribution": dict(pod_distribution),
    "memory_monitoring": {
        "sample_count": len(memory_samples),
        "peak_observed_memory_mib_per_pod": peak_by_pod,
        "overall_peak_observed_memory_mib": (
            max(peak_by_pod.values()) if peak_by_pod else None
        ),
        "sampling_method": "kubectl top pods, approximately 1-second polling"
    }
}

Path("results/inference_benchmark.json").write_text(
    json.dumps(report, indent=2),
    encoding="utf-8"
)

with Path("results/inference_benchmark.csv").open(
    "w", newline="", encoding="utf-8"
) as file:
    writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)

Path("results/inference_memory_samples.json").write_text(
    json.dumps(memory_samples, indent=2),
    encoding="utf-8"
)

print("\n=== INFERENCE BENCHMARK REPORT ===")
print(json.dumps(report, indent=2))
print("\nEvidence saved:")
print("results/inference_benchmark.json")
print("results/inference_benchmark.csv")
print("results/inference_memory_samples.json")
