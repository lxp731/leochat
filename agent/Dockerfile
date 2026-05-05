FROM python:3.14.4-slim AS builder

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN pip install uv && \
    uv sync --frozen --no-dev

FROM python:3.14.4-slim

WORKDIR /app

COPY --from=builder /app/.venv/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages

COPY app.py ./
COPY config.toml ./
COPY IDENTIFY.md ./

CMD ["python", "app.py"]
