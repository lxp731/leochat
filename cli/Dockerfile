FROM python:3.12-slim AS builder

WORKDIR /app

COPY . .

RUN cp /etc/apt/sources.list.d/debian.sources /etc/apt/sources.list.d/debian.sources.bak && \
    > /etc/apt/sources.list.d/debian.sources && \
    echo 'Types: deb' >> /etc/apt/sources.list.d/debian.sources && \
    echo 'URIs: https://mirrors.tuna.tsinghua.edu.cn/debian ' >> /etc/apt/sources.list.d/debian.sources && \
    echo 'Suites: bookworm bookworm-updates' >> /etc/apt/sources.list.d/debian.sources && \
    echo 'Components: main' >> /etc/apt/sources.list.d/debian.sources && \
    echo 'Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg' >> /etc/apt/sources.list.d/debian.sources && \
    echo '' >> /etc/apt/sources.list.d/debian.sources && \
    echo 'Types: deb' >> /etc/apt/sources.list.d/debian.sources && \
    echo 'URIs: https://mirrors.tuna.tsinghua.edu.cn/debian-security ' >> /etc/apt/sources.list.d/debian.sources && \
    echo 'Suites: bookworm-security' >> /etc/apt/sources.list.d/debian.sources && \
    echo 'Components: main' >> /etc/apt/sources.list.d/debian.sources && \
    echo 'Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg' >> /etc/apt/sources.list.d/debian.sources && \
    apt update && \
    apt install -y --no-install-recommends \
    build-essential \
    patchelf && \
    pip install --no-cache-dir -r requirements.txt && \
    rm -rf /var/lib/apt/lists/* && \
    python -m nuitka --standalone --onefile app.py

FROM gcr.io/distroless/static-debian12

WORKDIR /app

COPY --from=builder /app/app.bin /app/app.bin

CMD ["./app.bin"]