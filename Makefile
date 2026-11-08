SHELL := /bin/bash

PYTHON := .venv-training/bin/python
VERSION ?= v1
SUBSET ?=
EPOCHS ?=

.PHONY: train up down test bootstrap-tools lint

train:
	$(PYTHON) training/train.py --version "$(VERSION)" $(if $(SUBSET),--subset "$(SUBSET)",) $(if $(EPOCHS),--epochs "$(EPOCHS)",)

bootstrap-tools:
	python3 -m venv .venv-bootstrap || true
	.venv-bootstrap/bin/python -m pip install -r requirements-bootstrap.txt

up:
	bash scripts/bootstrap.sh

down:
	bash scripts/teardown.sh

test:
	python3 -m unittest discover -s tests -v

lint: bootstrap-tools
	.venv-bootstrap/bin/ruff check service tests tools/score.py tools/nacl_sim.py tools/validate_subnets.py tools/make_bad_predictions.py tools/locustfile.py tools/sample_k8s_resources.py tools/run_locust_benchmark.py tools/build_task7_report.py
