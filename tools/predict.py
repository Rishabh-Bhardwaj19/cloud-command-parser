import argparse
import json
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM


BASE_MODEL = "EleutherAI/pythia-70m"
TEACHER_URL = "http://127.0.0.1:11434/api/generate"
THREADS = 4
MAX_NEW_TOKENS = 64


def load_validation():
    rows = []

    with open("data/validation.jsonl", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))

    if len(rows) != 100:
        raise ValueError(
            f"Expected 100 validation examples, found {len(rows)}"
        )

    return rows


def generate_teacher(rows):

    prompt = Path(
        "prompts/teacher_prompt.txt"
    ).read_text(encoding="utf-8").strip()

    with open("data/schema.json", encoding="utf-8") as f:
        schema = json.load(f)["json_schema"]

    output_path = Path("results/teacher_predictions.jsonl")

    with output_path.open("w", encoding="utf-8") as out:

        for index, record in enumerate(rows, 1):

            payload = {
                "model": "phi3.5",
                "prompt": prompt + "\n" + record["text"],
                "format": schema,
                "stream": False,
                "keep_alive": "10m",
                "options": {
                    "temperature": 0,
                    "seed": 42,
                    "num_ctx": 2048
                }
            }

            request = Request(
                TEACHER_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )

            for attempt in range(3):
                try:
                    with urlopen(request, timeout=600) as response:
                        result = json.loads(response.read())

                    if "error" in result:
                        raise RuntimeError(result["error"])

                    raw = result["response"]

                    if not isinstance(raw, str):
                        raise ValueError("Teacher returned non-text output")

                    break

                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(2 ** (attempt + 1))

            out.write(json.dumps({
                "id": record["id"],
                "prediction": raw
            }, ensure_ascii=False) + "\n")

            out.flush()

            if index % 10 == 0:
                print(
                    f"Teacher: {index}/{len(rows)} completed",
                    flush=True
                )

    print("Teacher predictions saved:", output_path)


def generate_student(rows, version):

    if version == "base":
        model_source = BASE_MODEL
        output_path = Path("results/pythia_base_predictions.jsonl")
    elif version == "v1":
        model_source = "models/v1"
        output_path = Path("results/pythia_v1_predictions.jsonl")
    else:
        model_source = "models/v2"
        output_path = Path("results/pythia_v2_predictions.jsonl")

    torch.set_num_threads(THREADS)

    print("Loading student tokenizer:", model_source)

    tokenizer = AutoTokenizer.from_pretrained(model_source)
    tokenizer.pad_token = tokenizer.eos_token

    print("Loading student model:", model_source)

    model = AutoModelForCausalLM.from_pretrained(
        model_source,
        dtype=torch.float32
    )

    model.to("cpu")
    model.eval()

    # Enable KV caching for inference.
    model.config.use_cache = True

    with output_path.open("w", encoding="utf-8") as out:

        for index, record in enumerate(rows, 1):

            prompt = (
                f"Command: {record['text']}\n"
                "JSON: "
            )

            inputs = tokenizer(
                prompt,
                return_tensors="pt"
            )

            with torch.inference_mode():
                generated = model.generate(
                    **inputs,
                    max_new_tokens=MAX_NEW_TOKENS,
                    do_sample=False,
                    eos_token_id=tokenizer.eos_token_id,
                    pad_token_id=tokenizer.pad_token_id,
                    use_cache=True
                )

            input_length = inputs["input_ids"].shape[1]

            raw = tokenizer.decode(
                generated[0][input_length:],
                skip_special_tokens=True
            )

            out.write(json.dumps({
                "id": record["id"],
                "prediction": raw.strip()
            }, ensure_ascii=False) + "\n")

            out.flush()

            if index % 10 == 0:
                print(
                    f"Pythia {version}: "
                    f"{index}/{len(rows)} completed",
                    flush=True
                )

    del model
    del tokenizer

    print("Student predictions saved:", output_path)


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "model",
        choices=["teacher", "base", "v1", "v2"]
    )

    args = parser.parse_args()

    Path("results").mkdir(exist_ok=True)

    rows = load_validation()

    print("Validation records:", len(rows))

    if args.model == "teacher":
        generate_teacher(rows)
    else:
        generate_student(rows, args.model)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"PREDICTION FAILED: {error}", file=sys.stderr)
        sys.exit(1)
