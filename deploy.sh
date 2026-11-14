#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

echo "[1/4] 拉取最新代码..."
git pull origin main

echo "[2/4] 构建 Docker 镜像..."
docker build -t ai-search-api .

echo "[3/4] 停止并移除旧容器..."
docker rm -f ai-search-api 2>/dev/null || true

echo "[4/4] 启动新容器..."
mkdir -p "$APP_DIR/data"
docker run -d \
  --name ai-search-api \
  --restart unless-stopped \
  -p 127.0.0.1:8787:8787 \
  -v "$APP_DIR/data:/app/data" \
  ai-search-api

echo "完成！当前状态："
docker ps --filter "name=ai-search-api"
