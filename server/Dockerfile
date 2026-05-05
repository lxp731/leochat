FROM python:3.14.4-slim AS builder

WORKDIR /app

ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

COPY . .

RUN pip install uv && \
    uv sync

FROM python:3.14.4-slim

WORKDIR /app

COPY --from=builder /app/.venv/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /app/app.py /app/
COPY --from=builder /app/templates /app/templates
COPY --from=builder /app/static /app/static

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python -c "from urllib.request import urlopen; urlopen('http://localhost:5000/login')"

CMD ["python", "-m", "gunicorn", "-k", "geventwebsocket.gunicorn.workers.GeventWebSocketWorker", "-w", "1", "-b", "0.0.0.0:5000", "app:app"]
