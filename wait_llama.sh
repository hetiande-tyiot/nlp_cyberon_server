#!/bin/bash
# 等 llama-server 的 8081 起來（不用 curl，避免機器沒裝）
for i in $(seq 1 60); do (echo > /dev/tcp/127.0.0.1/8081) 2>/dev/null && exit 0; sleep 2; done
echo "llama-server 8081 not ready" >&2; exit 1
