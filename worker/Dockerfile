FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY worker/requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY worker/label.py /app/label.py

COPY prompts/teacher_prompt.txt /app/prompts/teacher_prompt.txt
COPY data/schema.json /app/data/schema.json

RUN useradd --system --uid 10001 appuser && \
    chown -R appuser:appuser /app

USER 10001

ENTRYPOINT ["python", "/app/label.py"]
