import json
import os
import subprocess
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)

LOCUST = ROOT / ".venv-bootstrap/bin/locust"
LOG = RESULTS / "loadtest_console.log"

if not LOCUST.exists():
    raise SystemExit("Locust is not installed in .venv-bootstrap.")

env = os.environ.copy()
env["LOADTEST_HEADERS_OUT"] = str(RESULTS / "loadtest_headers.json")

command = [
    str(LOCUST),
    "-f", "tools/locustfile.py",
    "--headless",
    "--users", "4",
    "--spawn-rate", "4",
    "--run-time", "2m",
    "--host", "http://localhost:8080",
    "--csv", "results/loadtest",
]

samples = []
deadline_duration = 120

print("Starting the instructor-prescribed Locust benchmark.")
print("Four users, spawn rate four, duration 120 seconds.")
print("Process is detached from the interactive terminal.")

start = time.monotonic()

with LOG.open("w", encoding="utf-8") as logfile:
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=logfile,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    print("Locust PID:", process.pid)

    while process.poll() is None:
        timestamp = datetime.now(timezone.utc).isoformat()

        try:
            result = subprocess.run(
                [
                    "kubectl", "top", "pods", "-n", "app",
                    "-l", "app=command-parser", "--no-headers"
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )

            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    fields = line.split()
                    if len(fields) >= 3:
                        cpu = fields[1]
                        memory = fields[2]

                        samples.append({
                            "timestamp_utc": timestamp,
                            "pod": fields[0],
                            "cpu": cpu,
                            "memory": memory,
                        })

        except Exception as error:
            print("Resource sampling warning:", error)

        elapsed = int(time.monotonic() - start)
        if elapsed and elapsed % 15 == 0:
            print(f"Benchmark running: approximately {elapsed}s elapsed.")

        time.sleep(1)

    return_code = process.wait()

elapsed = time.monotonic() - start

(RESULTS / "loadtest_resource_samples.json").write_text(
    json.dumps(samples, indent=2),
    encoding="utf-8",
)

def cpu_millicores(value):
    return float(value[:-1]) if value.endswith("m") else float(value) * 1000

def memory_mib(value):
    factors = {"Ki": 1/1024, "Mi": 1, "Gi": 1024}
    for unit, factor in factors.items():
        if value.endswith(unit):
            return float(value[:-len(unit)]) * factor
    raise ValueError(value)

peaks = defaultdict(lambda: {
    "peak_cpu_millicores": 0,
    "peak_memory_mib": 0,
    "samples": 0,
})

for item in samples:
    entry = peaks[item["pod"]]
    entry["peak_cpu_millicores"] = max(
        entry["peak_cpu_millicores"],
        cpu_millicores(item["cpu"]),
    )
    entry["peak_memory_mib"] = max(
        entry["peak_memory_mib"],
        memory_mib(item["memory"]),
    )
    entry["samples"] += 1

resource_report = {
    "sampling_duration_seconds": round(elapsed, 2),
    "sample_count": len(samples),
    "per_pod_peak_usage": dict(peaks),
    "note": "Peak observed values from periodic kubectl top sampling.",
}

(RESULTS / "loadtest_resource_report.json").write_text(
    json.dumps(resource_report, indent=2),
    encoding="utf-8",
)

print("\n=== Locust process exit code ===")
print(return_code)

print("\n=== Locust console output ===")
print(LOG.read_text(encoding="utf-8")[-12000:])

headers_path = RESULTS / "loadtest_headers.json"
if headers_path.exists():
    print("\n=== Successful requests by Pod and model version ===")
    print(headers_path.read_text(encoding="utf-8"))
else:
    print("\nWARNING: Locust header report was not produced.")

print("\n=== Resource monitoring report ===")
print(json.dumps(resource_report, indent=2))

print("\nElapsed seconds:", round(elapsed, 2))
print("\nAll evidence is saved in results/loadtest*")

if return_code != 0:
    raise SystemExit(return_code)
