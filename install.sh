#!/usr/bin/env bash
# Leochat CLI 一键安装
# curl -fsSL https://raw.githubusercontent.com/lxp731/leochat/main/install.sh | bash
set -e

BINARY="leochat"
REPO="lxp731/leochat"
DEST="${HOME}/.local/bin"
DL_URL="https://github.com/${REPO}/releases/latest/download/leochat-cli-linux"

echo ">>> Leochat CLI 一键安装"
echo "    下载: ${DL_URL}"

mkdir -p "$DEST"

tmpdir=$(mktemp -d)
trap "rm -rf $tmpdir" EXIT

cd "$tmpdir"

echo ">>> 正在下载..."
if command -v curl > /dev/null 2>&1; then
    curl -fsSL "$DL_URL" -o "$BINARY"
elif command -v wget > /dev/null 2>&1; then
    wget -q "$DL_URL" -O "$BINARY"
else
    echo "[ERROR] 请安装 curl 或 wget" >&2
    exit 1
fi

chmod +x "$BINARY"
mv "$BINARY" "$DEST/"

echo ""
echo "✔ 安装完成"
echo "  运行: leochat"

if ! echo "$PATH" | grep -q "$DEST"; then
    echo "  提示: 将 ${DEST} 添加到 PATH 或重启终端"
fi
