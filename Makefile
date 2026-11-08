PYTHON := .venv-training/bin/python
VERSION ?= v1
SUBSET ?=
EPOCHS ?=

.PHONY: train

train:
	$(PYTHON) training/train.py --version "$(VERSION)" $(if $(SUBSET),--subset "$(SUBSET)",) $(if $(EPOCHS),--epochs "$(EPOCHS)",)
