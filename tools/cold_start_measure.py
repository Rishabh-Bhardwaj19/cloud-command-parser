import json
import statistics
import subprocess
import time
from datetime import datetime
from pathlib import Path


NAMESPACE = "app"
TIMEOUT = 600


def kubectl(*args, check=True):
    return subprocess.run(
        ["kubectl", *args],
        capture_output=True,
        text=True,
        check=check
    )


def get_pods():
    result = kubectl(
        "get", "pods", "-n", NAMESPACE,
        "-l", "app=command-parser", "-o", "json"
    )
    return json.loads(result.stdout)["items"]


def ready_pod(pod):
    return any(
        condition.get("type") == "Ready"
        and condition.get("status") == "True"
        for condition in pod.get("status", {}).get("conditions", [])
    )


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def wait_for_single_ready_pod():
    deadline = time.monotonic() + TIMEOUT

    while time.monotonic() < deadline:
        active = [
            pod for pod in get_pods()
            if not pod["metadata"].get("deletionTimestamp")
        ]

        ready = [pod for pod in active if ready_pod(pod)]

        if len(active) == 1 and len(ready) == 1:
            return ready[0]

        time.sleep(2)

    raise TimeoutError("Could not reach exactly one Ready Pod.")


def wait_for_replacement(old_name):
    deadline = time.monotonic() + TIMEOUT
    replacement = None

    while time.monotonic() < deadline:
        candidates = [
            pod for pod in get_pods()
            if pod["metadata"]["name"] != old_name
            and not pod["metadata"].get("deletionTimestamp")
        ]

        if candidates:
            candidates.sort(
                key=lambda item: item["metadata"]["creationTimestamp"]
            )
            replacement = candidates[-1]
            break

        time.sleep(1)

    if replacement is None:
        raise TimeoutError("Replacement Pod was not created.")

    name = replacement["metadata"]["name"]

    while time.monotonic() < deadline:
        result = kubectl(
            "get", "pod", name, "-n", NAMESPACE, "-o", "json",
            check=False
        )

        if result.returncode == 0:
            pod = json.loads(result.stdout)

            if ready_pod(pod):
                return pod

            if pod.get("status", {}).get("phase") == "Failed":
                raise RuntimeError(f"Replacement Pod {name} failed.")

        time.sleep(1)

    raise TimeoutError(f"Replacement Pod {name} did not become Ready.")


report = {
    "test": "Three Kubernetes model cold starts",
    "measurement": "Pod creationTimestamp to Ready condition lastTransitionTime",
    "hpa_during_test": {"minReplicas": 1, "maxReplicas": 1},
    "runs": []
}

try:
    print("=== Temporarily pinning HPA to one replica ===")
    kubectl(
        "patch", "hpa", "command-parser", "-n", NAMESPACE,
        "--type=merge",
        "-p", '{"spec":{"minReplicas":1,"maxReplicas":1}}'
    )

    kubectl(
        "scale", "deployment/command-parser",
        "-n", NAMESPACE, "--replicas=1"
    )

    current = wait_for_single_ready_pod()
    print("Initial Pod:", current["metadata"]["name"])

    for run_number in range(1, 4):
        old_name = current["metadata"]["name"]

        print(f"\n=== Cold-start run {run_number}/3 ===")
        print("Deleting:", old_name)

        kubectl(
            "delete", "pod", old_name, "-n", NAMESPACE,
            "--wait=false"
        )

        current = wait_for_replacement(old_name)

        metadata = current["metadata"]
        conditions = current["status"]["conditions"]

        ready_condition = next(
            condition for condition in conditions
            if condition["type"] == "Ready"
            and condition["status"] == "True"
        )

        created_at = parse_time(metadata["creationTimestamp"])
        ready_at = parse_time(ready_condition["lastTransitionTime"])

        duration = (ready_at - created_at).total_seconds()

        logs = kubectl(
            "logs", metadata["name"], "-n", NAMESPACE
        ).stdout

        download_seen = "Downloading model from s3://models/v1/" in logs
        files_seen = "Downloaded 6 model files" in logs
        ready_seen = "Model version v1 is ready" in logs

        run = {
            "run": run_number,
            "pod": metadata["name"],
            "creation_timestamp": metadata["creationTimestamp"],
            "ready_timestamp": ready_condition["lastTransitionTime"],
            "pod_creation_to_ready_seconds": round(duration, 3),
            "model_download_started": download_seen,
            "six_model_files_downloaded": files_seen,
            "model_ready_log_confirmed": ready_seen
        }

        report["runs"].append(run)
        print(json.dumps(run, indent=2))

        if not (download_seen and files_seen and ready_seen):
            raise RuntimeError(
                f"Run {run_number} did not show all expected download logs."
            )

    durations = [
        run["pod_creation_to_ready_seconds"]
        for run in report["runs"]
    ]

    report["median_cold_start_seconds"] = round(
        statistics.median(durations), 3
    )
    report["all_three_runs_confirmed"] = True

finally:
    print("\n=== Restoring assignment HPA settings ===")
    kubectl(
        "patch", "hpa", "command-parser", "-n", NAMESPACE,
        "--type=merge",
        "-p", '{"spec":{"minReplicas":1,"maxReplicas":2}}',
        check=False
    )

    Path("results").mkdir(exist_ok=True)

    if report["runs"]:
        Path("results/cold_start_report.json").write_text(
            json.dumps(report, indent=2),
            encoding="utf-8"
        )
        print("\nPartial or final cold-start evidence saved.")


if len(report["runs"]) == 3:
    print("\n=== FINAL COLD-START REPORT ===")
    print(json.dumps(report, indent=2))
    print("\nEvidence: results/cold_start_report.json")
else:
    print("\nCold-start test incomplete. Inspect the error above.")
    raise SystemExit(1)
