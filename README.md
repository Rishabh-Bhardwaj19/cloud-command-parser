# Student Kit: Cloud Computing Mini Project

Read the project handout first. It explains every file here.

    data/commands_pool.jsonl     3,000 commands (text only)
    data/validation.jsonl        100 labelled commands, for evaluation only (never train on them)
    data/schema.json             the four keys, the eight intents and the slot rules
    data/rate_card.json          hypothetical prices for the cost exercise
    tools/score.py               python tools/score.py PREDICTIONS data/validation.jsonl [--min-validity 95]
    tools/locustfile.py          pip install locust, then:
                                 locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 2m --host http://localhost:8080 --csv results/loadtest
    tools/nacl_sim.py            python tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check
    network/packets_sample.jsonl six sample packets with expected decisions

score.py and nacl_sim.py need only Python 3 (standard library); run them with -h for help. The load test needs Locust (https://locust.io).

Data: commands from SLURP (Bastianelli et al., EMNLP 2020), licensed CC BY 4.0.
https://github.com/pswietojanski/slurp

## Reproducible deployment

### Prerequisites
- Docker Desktop with WSL2 integration
- Python 3 and virtual environment support
- kubectl, k3d, Helm, curl, tar, sha256sum and GNU Make
- Internet access to GitHub Releases and the SeaweedFS Helm repository

### Fresh-clone deployment

Clone the repository and run make up:

git clone https://github.com/Rishabh-Bhardwaj19/cloud-command-parser.git
cd cloud-command-parser
make up

The bootstrap process creates or reuses k3d, installs SeaweedFS chart 4.52.0, downloads both model archives, verifies the v1 checksum, uploads datasets and models, builds the inference image and applies Kubernetes manifests.

### Inference endpoint
http://127.0.0.1:8080/parse
Send the HTTP header Host: parser.local.

### Teardown warning
make down deletes the entire cloud-command-parser k3d cluster, including Kubernetes namespaces, PVCs and SeaweedFS objects. Local repository files and GitHub Release assets are not deleted.

### Training
make train
make train SUBSET=50
make train VERSION=v2 EPOCHS=4

### Automated checks
make test
make lint

GitHub Actions performs linting, unit tests, model evaluation, the 95 percent JSON-validity quality gate, its negative test and secret scanning.
