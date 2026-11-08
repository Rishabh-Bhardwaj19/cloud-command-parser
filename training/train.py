import argparse
import csv
import json
import random
import sys
from pathlib import Path

import numpy as np
import torch
import yaml
from transformers import AutoModelForCausalLM, AutoTokenizer


# --------------------------------------------------
# 1. Load configuration
# --------------------------------------------------

CONFIG_PATH = Path("training/config.yaml")


def load_config():
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


# --------------------------------------------------
# 2. Set reproducibility
# --------------------------------------------------

def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)


# --------------------------------------------------
# 3. Load first N training examples
# --------------------------------------------------

def load_records(path, count):

    records = []

    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            record = json.loads(line)

            if set(record) != {"id", "text", "teacher_raw"}:
                raise ValueError("Unexpected training record structure.")

            records.append(record)

            if len(records) == count:
                break

    if len(records) != count:
        raise ValueError(
            f"Expected {count} records, found {len(records)}."
        )

    return records


# --------------------------------------------------
# 4. Tokenize with response-only labels
# --------------------------------------------------

def prepare_dataset(records, tokenizer, max_length):

    dataset = []

    eos_id = tokenizer.eos_token_id

    for record in records:

        prompt = (
            f"Command: {record['text']}\n"
            "JSON: "
        )

        target = record["teacher_raw"]

        prompt_ids = tokenizer(
            prompt,
            add_special_tokens=False
        )["input_ids"]

        target_ids = tokenizer(
            target,
            add_special_tokens=False
        )["input_ids"]

        input_ids = prompt_ids + target_ids + [eos_id]

        if len(input_ids) > max_length:
            raise ValueError(
                f"Example {record['id']} exceeds "
                f"MAX_LENGTH={max_length}. "
                f"Actual length: {len(input_ids)}"
            )

        # Ignore the command tokens in the loss.
        labels = (
            [-100] * len(prompt_ids)
            + target_ids
            + [eos_id]
        )

        dataset.append({
            "input_ids": input_ids,
            "labels": labels
        })

    return dataset


# --------------------------------------------------
# 5. Create padded batches
# --------------------------------------------------

def create_batch(examples, pad_token_id):

    max_len = max(len(x["input_ids"]) for x in examples)

    input_ids = []
    attention_masks = []
    labels = []

    for example in examples:

        ids = example["input_ids"]
        target = example["labels"]

        padding = max_len - len(ids)

        input_ids.append(
            ids + [pad_token_id] * padding
        )

        attention_masks.append(
            [1] * len(ids) + [0] * padding
        )

        labels.append(
            target + [-100] * padding
        )

    return {
        "input_ids": torch.tensor(input_ids, dtype=torch.long),
        "attention_mask": torch.tensor(
            attention_masks, dtype=torch.long
        ),
        "labels": torch.tensor(labels, dtype=torch.long)
    }


# --------------------------------------------------
# 6. Training loop
# --------------------------------------------------

def train(model, dataset, config, epochs, version, is_smoke):

    params = config["training"]

    learning_rate = float(params["learning_rate"])
    batch_size = int(params["batch_size"])
    seed = int(params["seed"])
    weight_decay = float(params["weight_decay"])
    max_grad_norm = float(params["max_grad_norm"])

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=learning_rate,
        weight_decay=weight_decay
    )

    loss_path = (
        Path("training/loss_subset.csv")
        if is_smoke
        else Path("training/loss.csv")
    )

    loss_path.parent.mkdir(parents=True, exist_ok=True)

    # New v1 run creates the official loss file.
    # v2 appends its epoch results.
    if is_smoke or version == "v1":
        mode = "w"
    else:
        mode = "a"

    write_header = (
        mode == "w" or not loss_path.exists()
    )

    with loss_path.open(
        mode,
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.writer(file)

        if write_header:
            writer.writerow([
                "version",
                "epoch",
                "average_loss",
                "examples"
            ])

        for epoch in range(epochs):

            model.train()

            indices = list(range(len(dataset)))

            rng = random.Random(seed + epoch)
            rng.shuffle(indices)

            total_loss = 0.0
            total_tokens = 0
            steps = 0

            print(
                f"\n========== {version.upper()} "
                f"EPOCH {epoch + 1}/{epochs} =========="
            )

            for start in range(0, len(indices), batch_size):

                batch_indices = indices[
                    start:start + batch_size
                ]

                examples = [
                    dataset[i] for i in batch_indices
                ]

                batch = create_batch(
                    examples,
                    model.config.pad_token_id
                )

                optimizer.zero_grad(set_to_none=True)

                outputs = model(**batch)

                loss = outputs.loss

                supervised_tokens = int(
                    (batch["labels"][:, 1:] != -100).sum().item()
                )

                loss.backward()

                torch.nn.utils.clip_grad_norm_(
                    model.parameters(),
                    max_grad_norm
                )

                optimizer.step()

                total_loss += (
                    loss.detach().item() * supervised_tokens
                )

                total_tokens += supervised_tokens
                steps += 1

                if steps % 25 == 0:
                    print(
                        f"Epoch {epoch + 1}: "
                        f"Step {steps}, "
                        f"Batch loss: {loss.item():.4f}",
                        flush=True
                    )

            average_loss = total_loss / total_tokens

            writer.writerow([
                version,
                epoch + 1,
                f"{average_loss:.6f}",
                len(dataset)
            ])

            file.flush()

            print(
                f"Epoch {epoch + 1} completed | "
                f"Average loss: {average_loss:.6f} | "
                f"Supervised tokens: {total_tokens}",
                flush=True
            )

    return model


# --------------------------------------------------
# 7. Main execution
# --------------------------------------------------

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--version",
        choices=["v1", "v2"],
        default="v1"
    )

    parser.add_argument(
        "--subset",
        type=int,
        default=None
    )

    parser.add_argument(
        "--epochs",
        type=int,
        default=None
    )

    args = parser.parse_args()

    config = load_config()

    params = config["training"]

    seed = int(params["seed"])
    max_length = int(params["max_sequence_length"])
    epochs = args.epochs or int(params["epochs"])

    if epochs < 1:
        raise ValueError("Epochs must be positive.")

    set_seed(seed)

    torch.set_num_threads(
        int(params["num_threads"])
    )

    device = torch.device("cpu")

    model_name = config["model"]["name"]

    full_count = int(
        config["dataset"]["train_records"]
    )

    subset = args.subset

    if subset is not None:
        if not 1 <= subset <= full_count:
            raise ValueError(
                f"SUBSET must be between 1 and {full_count}."
            )

        count = subset
        is_smoke = True

    else:
        count = full_count
        is_smoke = False

    print("========== TRAINING CONFIGURATION ==========")
    print("Model:", model_name)
    print("Version:", args.version)
    print("Training records:", count)
    print("Epochs:", epochs)
    print("Batch size:", params["batch_size"])
    print("Learning rate:", params["learning_rate"])
    print("Maximum sequence length:", max_length)
    print("Device:", device)

    # Load tokenizer
    print("\nLoading tokenizer...", flush=True)

    tokenizer = AutoTokenizer.from_pretrained(model_name)

    if tokenizer.eos_token_id is None:
        raise ValueError("Tokenizer EOS token is missing.")

    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    # Load original records
    print("Loading training records...", flush=True)

    records = load_records(
        config["dataset"]["path"],
        count
    )

    dataset = prepare_dataset(
        records,
        tokenizer,
        max_length
    )

    print(
        f"Prepared {len(dataset)} training examples.",
        flush=True
    )

    # Load student model
    print("\nLoading Pythia-70M...", flush=True)

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        dtype=torch.float32
    )

    model.to(device)

    model.config.pad_token_id = tokenizer.pad_token_id
    model.config.use_cache = False

    # Train
    model = train(
        model,
        dataset,
        config,
        epochs,
        args.version,
        is_smoke
    )

    # Save final model
    if is_smoke:
        output_dir = Path("training/smoke-model")
    else:
        output_dir = (
            Path(config["model"]["output_base"])
            / args.version
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    print("\nSaving model to:", output_dir)

    model.save_pretrained(
        output_dir,
        safe_serialization=True
    )

    tokenizer.save_pretrained(output_dir)

    print("\n========== TRAINING COMPLETED ==========")
    print("Model directory:", output_dir)
    print("Loss file:", (
        "training/loss_subset.csv"
        if is_smoke
        else "training/loss.csv"
    ))


if __name__ == "__main__":

    try:
        main()

    except Exception as error:
        print("\nTRAINING FAILED:", error, file=sys.stderr)
        sys.exit(1)
