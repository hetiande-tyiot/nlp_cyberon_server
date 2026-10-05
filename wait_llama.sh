#!/bin/bash
# 等 llama-server 的 port 起來（不用 curl，避免機器沒裝）
# 用法：wait_llama.sh [PORT]   預設 8081
PORT="${1:-8081}"
for i in $(seq 1 60); do (echo > /dev/tcp/127.0.0.1/"$PORT") 2>/dev/null && exit 0; sleep 2; done
echo "llama-server $PORT not ready" >&2; exit 1
