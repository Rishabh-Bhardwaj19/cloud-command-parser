FROM python:3.14-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TOKENIZERS_PARALLELISM=false \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    TORCH_NUM_THREADS=1

WORKDIR /app

COPY service/requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt

COPY service/app.py /app/app.py
COPY service/validation.py /app/validation.py
COPY data/schema.json /app/data/schema.json

RUN useradd --system --uid 10001 appuser && \
    chown -R appuser:appuser /app

USER 10001

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
