import argparse
import json
import re
import subprocess
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def run_kubectl(*args):
    result = subprocess.run(
        ["kubectl", *args],
        capture_output=True,
        text=True,
        timeout=10,
        check=True
    )
    return result.stdout


def cpu_millicores(value):
    if value.endswith("m"):
        return float(value[:-1])
    return float(value) * 1000


def memory_mib(value):
    units = {
        "Ki": 1 / 1024,
        "Mi": 1,
        "Gi": 1024,
    }
    match = re.fullmatch(r"([0-9.]+)(Ki|Mi|Gi)", value)
    if not match:
        raise ValueError(f"Unknown memory unit: {value}")
    return float(match.group(1)) * units[match.group(2)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=140)
    parser.add_argument("--interval", type=float, default=1)
    args = parser.parse_args()

    samples = []
    deadline = time.monotonic() + args.duration

    print("Resource monitoring started.", flush=True)

    while time.monotonic() < deadline:
        timestamp = datetime.now(timezone.utc).isoformat()

        try:
            raw = run_kubectl(
                "top", "pods", "-n", "app",
                "-l", "app=command-parser", "--no-headers"
            )

            for line in raw.splitlines():
                fields = line.split()
                if len(fields) < 3:
                    continue

                samples.append({
                    "timestamp_utc": timestamp,
                    "pod": fields[0],
                    "cpu_millicores": round(cpu_millicores(fields[1]), 2),
                    "memory_mib": round(memory_mib(fields[2]), 2)
                })

        except Exception as error:
            print(f"Sampling warning: {error}", flush=True)

        time.sleep(args.interval)

    Path("results").mkdir(exist_ok=True)

    Path("results/loadtest_resource_samples.json").write_text(
        json.dumps(samples, indent=2),
        encoding="utf-8"
    )

    summary = defaultdict(lambda: {
        "max_cpu_millicores": 0,
        "max_memory_mib": 0,
        "samples": 0
    })

    for sample in samples:
        pod = summary[sample["pod"]]
        pod["max_cpu_millicores"] = max(
            pod["max_cpu_millicores"],
            sample["cpu_millicores"]
        )
        pod["max_memory_mib"] = max(
            pod["max_memory_mib"],
            sample["memory_mib"]
        )
        pod["samples"] += 1

    report = {
        "duration_seconds": args.duration,
        "sampling_interval_seconds": args.interval,
        "sample_count": len(samples),
        "per_pod_peak_usage": dict(summary),
        "note": "Peak observed values from periodic kubectl top sampling."
    }

    Path("results/loadtest_resource_report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8"
    )

    print("\n=== RESOURCE MONITOR REPORT ===")
    print(json.dumps(report, indent=2))
    print("\nEvidence saved:")
    print("results/loadtest_resource_samples.json")
    print("results/loadtest_resource_report.json")


if __name__ == "__main__":
    main()
