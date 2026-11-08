import csv
import json
from pathlib import Path

root = Path(".")
results = root / "results"

with (results / "loadtest_stats.csv").open(encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

aggregate = next(row for row in rows if row.get("Name") == "Aggregated")

with (results / "loadtest_headers.json").open(encoding="utf-8") as f:
    headers = json.load(f)

with (results / "loadtest_resource_report.json").open(encoding="utf-8") as f:
    resources = json.load(f)

with (root / "data/rate_card.json").open(encoding="utf-8") as f:
    rate = json.load(f)

total = int(aggregate["Request Count"])
failures = int(aggregate["Failure Count"])
successes = total - failures

duration = float(resources["sampling_duration_seconds"])
cpu_limit = 1.0
memory_limit_gib = 1.0
replicas = 2

per_replica_hourly = (
    cpu_limit * rate["vcpu_hour"]
    + memory_limit_gib * rate["gib_memory_hour"]
)

two_replica_hourly = replicas * per_replica_hourly
successful_per_hour = successes / duration * 3600
cost_per_1000 = two_replica_hourly / successful_per_hour * 1000

success_rate = successes / total * 100
error_rate = failures / total * 100

slo_target = 95.0
error_budget = 100 - slo_target
budget_consumed = error_rate / error_budget * 100

header_successes = sum(headers["per_replica"].values())

analysis = {
    "test": {
        "tool": "Locust",
        "duration_seconds": duration,
        "users": 4,
        "spawn_rate_per_second": 4,
        "wait_between_requests_seconds": 0,
        "total_requests": total,
        "successful_requests_from_locust_stats": successes,
        "failed_requests": failures,
        "success_rate_percent": round(success_rate, 2),
        "error_rate_percent": round(error_rate, 2),
        "average_latency_ms": float(aggregate["Average Response Time"]),
        "p50_latency_ms": float(aggregate["50%"]),
        "p95_latency_ms": float(aggregate["95%"]),
        "maximum_latency_ms": float(aggregate["Max Response Time"]),
        "throughput_all_requests_per_second": float(aggregate["Requests/s"]),
        "failure_breakdown": {
            "http_500_invalid_model_output": failures,
            "locust_exceptions": 0
        }
    },
    "successful_response_headers": {
        "per_replica": headers["per_replica"],
        "per_model_version": headers["per_model_version"],
        "header_count_total": header_successes,
        "locust_stats_success_total": successes,
        "count_difference": header_successes - successes,
        "note": "The custom header counter differs by one event from the Locust aggregate CSV. Locust aggregate statistics are used for success and error percentages."
    },
    "resources": resources,
    "cost_estimate": {
        "currency": rate["currency"],
        "source": "data/rate_card.json (hypothetical rates)",
        "cpu_limit_per_replica_vcpu": cpu_limit,
        "memory_limit_per_replica_gib": memory_limit_gib,
        "replicas_assumed": replicas,
        "hourly_cost_per_replica": round(per_replica_hourly, 4),
        "hourly_cost_two_replicas": round(two_replica_hourly, 4),
        "successful_requests_per_hour": round(successful_per_hour, 2),
        "cost_per_1000_successful_requests": round(cost_per_1000, 4),
        "two_minute_two_replica_cost": round(two_replica_hourly * 2 / 60, 4),
        "limitations": "Steady-state two-replica estimate. Excludes SeaweedFS, Traefik, control-plane, storage, network and other infrastructure costs."
    },
    "slo_and_error_budget": {
        "availability_slo_percent": slo_target,
        "error_budget_percent": error_budget,
        "observed_success_percent": round(success_rate, 2),
        "observed_error_percent": round(error_rate, 2),
        "error_budget_consumed_percent": round(budget_consumed, 2),
        "availability_slo_met": success_rate >= slo_target,
        "latency_slo": "p95 below 5000 ms",
        "observed_p95_ms": float(aggregate["95%"]),
        "latency_slo_met": float(aggregate["95%"]) < 5000,
        "scope": "A short two-minute laboratory load test, not a production 30-day SLO measurement."
    },
    "limitations_and_improvements": [
        "Eight requests returned HTTP 500 because generated model output failed JSON/schema validation.",
        "The offline v1 validation set measured 96% JSON validity, consistent with the invalid-output issue under load.",
        "CPU peaks approached the one-vCPU limit; HPA scaled to two replicas during load.",
        "The p95 latency was close to the proposed five-second target.",
        "The cluster uses one k3d node and does not demonstrate multi-node high availability.",
        "Potential improvements include constrained decoding, a carefully tested output-repair retry, better training coverage, CPU/GPU optimization, and repeated longer-duration load tests."
    ]
}

(results / "task7_analysis.json").write_text(
    json.dumps(analysis, indent=2),
    encoding="utf-8"
)

review = f"""# Task 7 — Performance, Cost and Review

## Load-test configuration

The instructor-provided Locust test was run for 120 seconds with four virtual
users, a spawn rate of four users per second and zero wait between requests.
Requests were routed through Traefik using the `Host: parser.local` header.

## Measured performance

| Metric | Result |
|---|---:|
| Total requests (Locust aggregate CSV) | {total} |
| Successful HTTP 200 requests | {successes} |
| Failed requests | {failures} |
| Success rate | {success_rate:.2f}% |
| Error rate | {error_rate:.2f}% |
| Average response latency | {float(aggregate["Average Response Time"]):.2f} ms |
| p50 latency | {float(aggregate["50%"]):.2f} ms |
| p95 latency | {float(aggregate["95%"]):.2f} ms |
| Maximum latency | {float(aggregate["Max Response Time"]):.2f} ms |
| Throughput (all attempts) | {float(aggregate["Requests/s"]):.2f} requests/s |

The eight failures were HTTP 500 responses. Application logs reported
`Model returned invalid JSON or schema`. Locust recorded no client-side
exceptions. The model's offline validation JSON validity was 96%, which is
consistent with the invalid-output behavior observed under load.

## Per-replica request distribution

| Pod | Successful requests |
|---|---:|
"""
for pod, count in headers["per_replica"].items():
    review += f"| `{pod}` | {count} |\n"

review += f"""
The custom response-header counter recorded {header_successes} successful
responses, while the Locust aggregate CSV recorded {successes}. This is a
one-event instrumentation discrepancy; the Locust aggregate CSV is used for
the success and failure calculations in this report.

## CPU and memory

| Pod | Peak observed CPU | Peak observed memory |
|---|---:|---:|
"""
for pod, item in resources["per_pod_peak_usage"].items():
    review += (
        f"| `{pod}` | {item['peak_cpu_millicores']:.0f}m | "
        f"{item['peak_memory_mib']:.0f} MiB |\n"
    )

review += f"""
The container resource limit was one vCPU and 1 GiB memory per replica.
Memory samples remained below the memory limit. CPU usage approached the
configured one-vCPU limit. The HPA scaled from one to two replicas during
the load test and later returned to one replica after load subsided.

Peak values are sampled observations from `kubectl top`, not exact
instantaneous maxima.

## Cost estimate

The assignment rate card is hypothetical and specifies INR 3.50 per vCPU-hour
and INR 0.45 per GiB-memory-hour.

- One replica: 1 vCPU × ₹3.50 + 1 GiB × ₹0.45 = ₹{per_replica_hourly:.2f}/hour.
- Two replicas: ₹{two_replica_hourly:.2f}/hour.
- Successful throughput derived from the test: {successful_per_hour:.2f} successful requests/hour.
- Estimated cost: **₹{cost_per_1000:.2f} per 1,000 successful requests**.

This is a steady-state two-replica estimate using CPU and memory limits.
It excludes SeaweedFS, Traefik, control-plane, storage, networking and
other infrastructure costs. It is not a real cloud-provider quotation.

## SLO and error budget

For this prototype, the proposed availability SLO is at least 95% of
`POST /parse` requests returning HTTP 200 with schema-valid JSON during
the measurement window. The corresponding error budget is 5%.

- Observed success rate: {success_rate:.2f}%.
- Observed error rate: {error_rate:.2f}%.
- Error budget consumed: {budget_consumed:.2f}%.
- Availability SLO: {"met" if success_rate >= slo_target else "not met"}.

The proposed latency SLO is p95 below 5,000 ms. The measured p95 was
{float(aggregate["95%"]):.2f} ms, so this target was
{"met" if float(aggregate["95%"]) < 5000 else "not met"}.

These results describe a short laboratory test, not a 30-day production
availability measurement.

## Review: evidence, limitations and improvements

| Area | Measured evidence | Limitation | Improvement |
|---|---|---|---|
| API correctness | {successes}/{total} Locust requests succeeded | {failures} outputs failed JSON/schema validation | Constrained decoding; evaluate a safe retry or output repair |
| Latency | p95 {float(aggregate["95%"]):.0f} ms | Close to the 5-second target | Optimize CPU inference and token generation |
| CPU | Peak observed up to approximately 1,002m | CPU approached the 1-vCPU limit | Tune HPA and CPU allocation; benchmark further |
| Memory | Peak observed {max(x["peak_memory_mib"] for x in resources["per_pod_peak_usage"].values()):.0f} MiB | Measurements are periodic samples | Continue monitoring under longer tests |
| Scaling | HPA used two replicas under load | Single-node k3d cluster | Test on multiple nodes for actual node-level resilience |
| Cost | ₹{cost_per_1000:.2f}/1,000 successful requests (two-replica estimate) | Hypothetical rate card excludes supporting services | Include storage, network and control-plane costs in a cloud deployment |

## Evidence files

- `results/loadtest_stats.csv`
- `results/loadtest_stats_history.csv`
- `results/loadtest_failures.csv`
- `results/loadtest_headers.json`
- `results/loadtest_resource_report.json`
- `results/loadtest_resource_samples.json`
- `results/task7_analysis.json`
"""

(results / "task7_review.md").write_text(review, encoding="utf-8")

print("Task 7 analysis saved.")
print(json.dumps(analysis, indent=2))
print("\nReview saved to results/task7_review.md")
