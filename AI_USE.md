# AI Usage Disclosure

## Project development

Generative AI assistance was used as a development aid during this
Cloud Computing mini-project.

The assistance included:
- Discussing the architecture of the object-storage, model-training,
  inference-service and Kubernetes components.
- Drafting and reviewing portions of Python, Docker and Kubernetes
  configuration.
- Explaining errors encountered during local development and testing.
- Suggesting test cases, validation checks and report organization.

All commands and code were reviewed and executed in the project
environment. Test outputs and performance figures in the project report
are based on the observed command output and saved result files.

## Teacher-generated training labels

The Phi-3.5 model served through Ollama was used as the teacher to
generate structured command-parser labels. The worker pipeline saved
the teacher's raw responses. The cleaning stage then checked JSON
validity, the required keys, allowed intents, slot values and duplicate
commands before creating the training dataset.

## Student model

EleutherAI/pythia-70m was fine-tuned using PyTorch and Transformers on
the cleaned teacher-labelled dataset. Two student versions were trained
and evaluated. The model evaluation used a separate validation dataset.

## Human responsibility

AI assistance does not replace the project's implementation,
verification or academic responsibility. The project author is
responsible for understanding the design, checking the code, validating
the results and explaining the submitted work.
