FROM python:3.14.4-slim AS builder

WORKDIR /app

ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

COPY . .

RUN pip install uv && \
    uv sync

FROM python:3.14.4-slim

WORKDIR /app

COPY --from=builder /app/.venv/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages

COPY --from=builder /app /app

EXPOSE 5000

CMD ["python", "app.py"]
