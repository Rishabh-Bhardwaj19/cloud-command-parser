# AI Use Disclosure

This project used AI systems as development aids and as the teacher/student components required by the assignment. Their outputs were reviewed and tested rather than accepted automatically.

## ChatGPT (OpenAI)

ChatGPT was used to explain cloud-computing and knowledge-distillation concepts, help debug Python, Docker and Kubernetes issues, review implementation ideas, suggest test cases and organise the report. I ran suggested commands in the project environment, inspected the resulting files and logs, and used tests and validators to check the implementation. ChatGPT was not used to generate the teacher labels or the validation answers.

## Ollama with Phi-3.5-mini-instruct (teacher model)

Ollama served the required Phi-3.5-mini-instruct teacher with temperature 0 and seed 42. It generated the command-parsing responses used as sequence-level training targets. The worker saved each raw response without manual editing. The cleaning program checked JSON syntax, the exact four-key schema, allowed intents, slot values against the original command and duplicate commands. The cleaning counts and dataset checksum are preserved in `results/cleaning_report.json` and `data/v1/train.sha256`.

## EleutherAI/Pythia-70M with Hugging Face Transformers

Pythia-70M was the student model specified by the assignment. It was fine-tuned locally with PyTorch and Transformers on the teacher-generated training set. The untrained model and both trained versions were evaluated against the separate 100-example validation set. Raw predictions and score reports are preserved in `results/`.

## Verification and responsibility

I reviewed the implementation and used repeatable checks rather than accepting generated suggestions without validation. Verification included Python unit tests, Ruff linting, the scoring script and its 95% JSON-validity quality gate, the NACL simulator, subnet validation, container API and fault-injection checks, Kubernetes probes and recovery tests, Locust measurements, SHA-256 checks and GitHub Actions. Measured results and known failures are reported as observed. I remain responsible for understanding, explaining and maintaining the submitted work.
