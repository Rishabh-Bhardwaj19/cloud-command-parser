import json
import logging
import os
import shutil
import socket
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

import boto3
import torch
from botocore.config import Config
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from transformers import AutoModelForCausalLM, AutoTokenizer
from validation import validate_prediction as validate_json_prediction


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger("cloud-command-parser")

MODEL_URI = os.getenv("MODEL_URI", "s3://models/v1/")
MODEL_VERSION = os.getenv("MODEL_VERSION", "v1")
S3_ENDPOINT = os.getenv(
    "S3_ENDPOINT",
    "http://seaweedfs-s3.data.svc.cluster.local:8333"
)
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "64"))
MODEL_DIR = Path(os.getenv("MODEL_DIR", "/tmp/cloud-command-parser-model"))
TORCH_THREADS = int(os.getenv("TORCH_NUM_THREADS", "1"))

torch.set_num_threads(TORCH_THREADS)
try:
    torch.set_num_interop_threads(1)
except RuntimeError:
    pass

MODEL = None
TOKENIZER = None
MODEL_READY = False
MODEL_LOAD_ERROR = None

SERVED_BY = os.getenv("POD_NAME", socket.gethostname())


def load_schema():
    configured_path = os.getenv("SCHEMA_PATH")

    if configured_path:
        schema_path = Path(configured_path)
    else:
        container_path = Path("/app/data/schema.json")
        local_path = Path(__file__).resolve().parents[1] / "data" / "schema.json"
        schema_path = container_path if container_path.exists() else local_path

    with schema_path.open(encoding="utf-8") as file:
        return json.load(file)


SCHEMA = load_schema()
EXPECTED_KEYS = set(SCHEMA["keys"])
ALLOWED_INTENTS = set(SCHEMA["intents"])


class ParseRequest(BaseModel):
    text: str = Field(min_length=1)


def download_model():
    """Download model files from S3, or copy a local directory for testing."""
    if MODEL_URI.startswith("s3://"):
        parsed = urlparse(MODEL_URI)
        bucket = parsed.netloc
        prefix = parsed.path.lstrip("/").rstrip("/")

        if not bucket or not prefix:
            raise ValueError("MODEL_URI must look like s3://bucket/model-prefix/")

        prefix += "/"
        MODEL_DIR.mkdir(parents=True, exist_ok=True)

        client = boto3.client(
            "s3",
            endpoint_url=S3_ENDPOINT,
            region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"}
            )
        )

        logger.info("Downloading model from s3://%s/%s", bucket, prefix)

        paginator = client.get_paginator("list_objects_v2")
        downloaded = 0

        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                key = item["Key"]
                relative_name = key[len(prefix):]

                if not relative_name:
                    continue

                relative_path = Path(relative_name)
                if relative_path.is_absolute() or ".." in relative_path.parts:
                    raise ValueError("Unsafe object key in model prefix")

                destination = MODEL_DIR / relative_path
                destination.parent.mkdir(parents=True, exist_ok=True)

                client.download_file(bucket, key, str(destination))
                downloaded += 1

        if downloaded == 0:
            raise RuntimeError("No model files were found at MODEL_URI")

        logger.info("Downloaded %d model files", downloaded)

    else:
        # Local-directory mode is useful for development and testing.
        source = MODEL_URI.removeprefix("file://")
        source_path = Path(source).expanduser().resolve()

        if not source_path.is_dir():
            raise FileNotFoundError(f"Local model directory not found: {source_path}")

        if MODEL_DIR.exists():
            shutil.rmtree(MODEL_DIR)

        shutil.copytree(source_path, MODEL_DIR)
        logger.info("Copied local model from %s", source_path)

    required_files = [
        "config.json",
        "model.safetensors",
        "tokenizer.json",
        "tokenizer_config.json"
    ]

    missing = [
        name for name in required_files
        if not (MODEL_DIR / name).is_file()
    ]

    if missing:
        raise RuntimeError(f"Model directory is missing files: {missing}")


def load_model():
    global MODEL, TOKENIZER, MODEL_READY, MODEL_LOAD_ERROR

    try:
        logger.info("Starting model download and loading")
        download_model()

        tokenizer = AutoTokenizer.from_pretrained(
            str(MODEL_DIR),
            local_files_only=True
        )

        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        model = AutoModelForCausalLM.from_pretrained(
            str(MODEL_DIR),
            dtype=torch.float32,
            local_files_only=True
        )

        model.to("cpu")
        model.eval()
        model.config.use_cache = True

        TOKENIZER = tokenizer
        MODEL = model
        MODEL_READY = True

        logger.info("Model version %s is ready", MODEL_VERSION)

    except Exception as error:
        MODEL_LOAD_ERROR = f"{type(error).__name__}: {error}"
        logger.exception("Model loading failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    loader = threading.Thread(
        target=load_model,
        name="model-loader",
        daemon=True
    )
    loader.start()
    yield


app = FastAPI(
    title="Cloud Command Parser",
    version="1.0.0",
    lifespan=lifespan
)


def response_headers():
    return {
        "X-Model-Version": MODEL_VERSION,
        "X-Served-By": SERVED_BY
    }


def validate_prediction(raw):
    """Validate output against the assignment's exact four-key schema."""
    return validate_json_prediction(
        raw,
        EXPECTED_KEYS,
        ALLOWED_INTENTS
    )


@app.get("/healthz")
def healthz():
    # Liveness: the API process is running.
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    # Readiness: do not receive traffic until the model is loaded.
    if not MODEL_READY:
        status = "failed" if MODEL_LOAD_ERROR else "loading"
        return JSONResponse(
            status_code=503,
            content={"status": status}
        )

    return {"status": "ready"}


@app.post("/parse")
def parse_command(request: ParseRequest):
    if not MODEL_READY or MODEL is None or TOKENIZER is None:
        return JSONResponse(
            status_code=503,
            content={"error": "model_not_ready"},
            headers=response_headers()
        )

    if os.getenv("FAULT_INJECT", "0") == "1":
        raw = "not json"
    else:
        prompt = f"Command: {request.text}\nJSON: "

        try:
            inputs = TOKENIZER(
                prompt,
                return_tensors="pt",
                truncation=True,
                max_length=128
            )

            with torch.inference_mode():
                generated = MODEL.generate(
                    **inputs,
                    max_new_tokens=MAX_NEW_TOKENS,
                    do_sample=False,
                    eos_token_id=TOKENIZER.eos_token_id,
                    pad_token_id=TOKENIZER.pad_token_id,
                    use_cache=True
                )

            input_length = inputs["input_ids"].shape[1]
            raw = TOKENIZER.decode(
                generated[0][input_length:],
                skip_special_tokens=True
            ).strip()

        except Exception:
            logger.exception("Inference failed")
            return JSONResponse(
                status_code=500,
                content={"error": "inference_failed"},
                headers=response_headers()
            )

    result = validate_prediction(raw)

    if result is None:
        logger.warning("Model returned invalid JSON or schema")
        return JSONResponse(
            status_code=500,
            content={"error": "invalid_model_output"},
            headers=response_headers()
        )

    return JSONResponse(
        content=result,
        headers=response_headers()
    )
