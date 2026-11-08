# Task 7 — Performance, Cost and Review

## Load-test configuration

The instructor-provided Locust test was run for 120 seconds with four virtual
users, a spawn rate of four users per second and zero wait between requests.
Requests were routed through Traefik using the `Host: parser.local` header.

## Measured performance

| Metric | Result |
|---|---:|
| Total requests (Locust aggregate CSV) | 194 |
| Successful HTTP 200 requests | 186 |
| Failed requests | 8 |
| Success rate | 95.88% |
| Error rate | 4.12% |
| Average response latency | 2440.76 ms |
| p50 latency | 2800.00 ms |
| p95 latency | 4800.00 ms |
| Maximum latency | 10491.93 ms |
| Throughput (all attempts) | 1.63 requests/s |

The eight failures were HTTP 500 responses. Application logs reported
`Model returned invalid JSON or schema`. Locust recorded no client-side
exceptions. The model's offline validation JSON validity was 96%, which is
consistent with the invalid-output behavior observed under load.

## Per-replica request distribution

| Pod | Successful requests |
|---|---:|
| `command-parser-7f87c8f5fc-8pp74` | 115 |
| `command-parser-7f87c8f5fc-7cqb7` | 72 |

The custom response-header counter recorded 187 successful
responses, while the Locust aggregate CSV recorded 186. This is a
one-event instrumentation discrepancy; the Locust aggregate CSV is used for
the success and failure calculations in this report.

## CPU and memory

| Pod | Peak observed CPU | Peak observed memory |
|---|---:|---:|
| `command-parser-7f87c8f5fc-8pp74` | 1002m | 470 MiB |
| `command-parser-7f87c8f5fc-7cqb7` | 873m | 582 MiB |

The container resource limit was one vCPU and 1 GiB memory per replica.
Memory samples remained below the memory limit. CPU usage approached the
configured one-vCPU limit. The HPA scaled from one to two replicas during
the load test and later returned to one replica after load subsided.

Peak values are sampled observations from `kubectl top`, not exact
instantaneous maxima.

## Cost estimate

The assignment rate card is hypothetical and specifies INR 3.50 per vCPU-hour
and INR 0.45 per GiB-memory-hour.

- One replica: 1 vCPU × ₹3.50 + 1 GiB × ₹0.45 = ₹3.95/hour.
- Two replicas: ₹7.90/hour.
- Successful throughput derived from the test: 5556.85 successful requests/hour.
- Estimated cost: **₹1.42 per 1,000 successful requests**.

This is a steady-state two-replica estimate using CPU and memory limits.
It excludes SeaweedFS, Traefik, control-plane, storage, networking and
other infrastructure costs. It is not a real cloud-provider quotation.

## SLO and error budget

For this prototype, the proposed availability SLO is at least 95% of
`POST /parse` requests returning HTTP 200 with schema-valid JSON during
the measurement window. The corresponding error budget is 5%.

- Observed success rate: 95.88%.
- Observed error rate: 4.12%.
- Error budget consumed: 82.47%.
- Availability SLO: met.

The proposed latency SLO is p95 below 5,000 ms. The measured p95 was
4800.00 ms, so this target was
met.

These results describe a short laboratory test, not a 30-day production
availability measurement.

## Review: evidence, limitations and improvements

| Area | Measured evidence | Limitation | Improvement |
|---|---|---|---|
| API correctness | 186/194 Locust requests succeeded | 8 outputs failed JSON/schema validation | Constrained decoding; evaluate a safe retry or output repair |
| Latency | p95 4800 ms | Close to the 5-second target | Optimize CPU inference and token generation |
| CPU | Peak observed up to approximately 1,002m | CPU approached the 1-vCPU limit | Tune HPA and CPU allocation; benchmark further |
| Memory | Peak observed 582 MiB | Measurements are periodic samples | Continue monitoring under longer tests |
| Scaling | HPA used two replicas under load | Single-node k3d cluster | Test on multiple nodes for actual node-level resilience |
| Cost | ₹1.42/1,000 successful requests (two-replica estimate) | Hypothetical rate card excludes supporting services | Include storage, network and control-plane costs in a cloud deployment |

## Evidence files

- `results/loadtest_stats.csv`
- `results/loadtest_stats_history.csv`
- `results/loadtest_failures.csv`
- `results/loadtest_headers.json`
- `results/loadtest_resource_report.json`
- `results/loadtest_resource_samples.json`
- `results/task7_analysis.json`
