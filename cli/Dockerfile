FROM python:3.12-slim AS builder

WORKDIR /app

COPY . .

RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
    sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's/security.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources; \
    else \
    sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list && \
    sed -i 's/security.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list; \
    fi && \
    apt update && \
    apt install -y --no-install-recommends \
    build-essential \
    python3-dev \
    patchelf && \
    pip install --no-cache-dir -r requirements.txt && \
    rm -rf /var/lib/apt/lists/* && \
    python -m nuitka --standalone --onefile --output-filename=app.bin app.py

FROM gcr.io/distroless/cc-debian12

WORKDIR /app

COPY --from=builder /app/app.bin /app/app.bin

CMD ["./app.bin"]