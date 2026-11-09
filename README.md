# Cloud Command Parser — CS3081 Mini Project

**Student:** Rishabh Bhardwaj
**Roll number:** 230101059
**Programme / section:** B.Tech CSE Core, Section A
**Semester:** VII
**Instructor:** Dr Salam Michael Singh, Assistant Professor, CSE, IIIT Manipur

**GitHub repository:** https://github.com/Rishabh-Bhardwaj19/cloud-command-parser
**Model release:** https://github.com/Rishabh-Bhardwaj19/cloud-command-parser/releases/tag/v1.0.0

## Project summary

This project applies sequence-level knowledge distillation to an English command-parsing task. A Phi-3.5 teacher served through Ollama labels 3,000 commands. Two parallel workers write raw teacher responses to SeaweedFS object storage. The cleaned dataset is used to fine-tune EleutherAI/Pythia-70M on CPU. A FastAPI inference service downloads its selected model and tokenizer from S3-compatible storage and runs in a local k3d Kubernetes cluster.

## Repository layout

- `cluster/` — k3d cluster configuration.
- `data/` — source commands, validation labels, schema, rate card and cleaned training data.
- `prompts/` and `worker/` — teacher prompt, parallel labelling worker and cleaner.
- `training/` — training configuration, CPU training script and epoch loss log.
- `models/` — checksum metadata only; model weights are distributed as GitHub Release assets, not committed to Git.
- `service/` — FastAPI inference service, schema validation and pinned container dependencies.
- `k8s/` — SeaweedFS, worker and application Kubernetes manifests.
- `network/` — VLSM allocation, public-subnet NACL and test packets.
- `tests/` and `tools/` — automated tests, scoring, NACL/subnet validators, benchmarks and Locust helpers.
- `scripts/` — bootstrap, object-storage initialization and teardown.
- `results/` — cleaning, evaluation, inference, Kubernetes, NACL, CI and Locust evidence.
- `report/report.pdf` — technical report (eight main pages, plus references).
- `AI_USE.md` — AI-use disclosure and verification approach.

## Prerequisites

- Docker Desktop with WSL2 integration and sufficient disk/RAM for the local model image.
- Python 3, GNU Make, `kubectl`, `k3d`, Helm, `curl`, `tar` and `sha256sum`.
- Internet access to the GitHub Release and SeaweedFS Helm chart repository.

## Fresh-checkout deployment

From a shell with the prerequisites installed:

```bash
git clone https://github.com/Rishabh-Bhardwaj19/cloud-command-parser.git
cd cloud-command-parser
make up
```

`make up` runs `scripts/bootstrap.sh`. It creates the configured k3d cluster if absent (or reuses it), installs SeaweedFS chart 4.52.0, downloads the v1/v2 model archives from Release `v1.0.0`, verifies the v1 archive checksum, uploads datasets and model files to SeaweedFS, builds/imports the CPU inference image, applies the app manifests and waits for the Deployment rollout.

**Reproducibility qualification:** the bootstrap command was run repeatedly and completed successfully against the existing populated local cluster. The brand-new-cluster branch is implemented in the script but was not independently exercised because deleting the evidence-bearing cluster would remove the locally stored original teacher shards and object-store state. Do not interpret the existing-cluster rerun as a fresh-cluster test.

## Inference endpoint

The k3d configuration maps the ingress to `http://127.0.0.1:8080`. Send `Host: parser.local`:

```bash
curl -sS -X POST http://127.0.0.1:8080/parse \
  -H 'Host: parser.local' \
  -H 'Content-Type: application/json' \
  -d '{"text":"set an alarm for seven am tomorrow"}'
```

The service exposes `POST /parse`, `GET /healthz` and `GET /readyz`. A valid parse returns exactly the four schema keys and includes `X-Model-Version` and `X-Served-By` response headers.

## Training and checks

The training environment used for the recorded runs is Python 3.14.4, torch 2.15.0+cpu, Transformers 5.22.2 and PyYAML 6.0.3. Prepare the isolated CPU training environment once; training parameters are read from `training/config.yaml`.

```bash
python3 -m venv .venv-training
.venv-training/bin/python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.15.0+cpu
.venv-training/bin/python -m pip install transformers==5.22.2 PyYAML==6.0.3
make train
make train SUBSET=50
make train VERSION=v2 EPOCHS=4
make test
make lint
```

The instructor's validation file is evaluation-only and is never used for training. The standard Locust run is documented in `tools/locustfile.py`; captured outputs are under `results/`.

## CI/CD

GitHub Actions runs lint, then unit tests, then model evaluation/quality gates, followed by secret scanning. Model evaluation downloads the v1 archive from Release `v1.0.0` and enforces at least 95% JSON validity. The main workflow also verifies that intentionally bad predictions are rejected. A separate manually dispatched workflow, `Negative Model Quality Gate Demonstration`, runs untrained Pythia through the 95% gate to produce the expected failing-run evidence.

## Teardown warning

`make down` deletes the entire `cloud-command-parser` k3d cluster, including its namespaces, PVCs and SeaweedFS objects. It is intentionally destructive. Repository files and GitHub Release assets are not deleted. It was not run against the evidence-bearing cluster used for this submission.

## Results and known limitations

The measured results and limitations are documented in `report/report.pdf` and the machine-readable files in `results/`. In particular, the two-minute Locust run recorded 8 HTTP 500 invalid-model-output responses out of 194 attempts (4.12%); this is above the assignment's 1% error-rate target. The p95 latency was 4,800 ms, within the 5,000 ms target. The rolling-update experiment recorded 3 HTTP 502 responses in 220 attempts (1.36%), above the 0.5% target. Pod-deletion recovery achieved 150/150 successful requests. The local k3d environment is single-node and does not demonstrate multi-node fault tolerance.

## Dataset attribution

The command data are derived from SLURP (Bastianelli et al., EMNLP 2020), licensed under CC BY 4.0: https://github.com/pswietojanski/slurp
