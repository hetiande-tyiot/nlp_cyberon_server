#!/usr/bin/env bash
# 模型檔 SHA-256 校驗，給隨身碟搬檔用。
#   ./checksum_models.sh gen      在來源機算，產出 model_checksums.sha256
#   ./checksum_models.sh verify   在新電腦的 repo 根目錄驗
set -e

cd "$(dirname "$0")"

FILES="
models/TW-119-Model.gguf
ai/TW-119-BERT_main/model.safetensors
ai/TW-119-BERT-sub_火警/model.safetensors
ai/TW-119-BERT-sub_救護/pytorch_model.bin
ai/TW-119-BERT-sub_緊急救援/model.safetensors
ai/TW-119-BERT-sub_其他案類/model.safetensors
"

case "$1" in
  gen)
    sha256sum $FILES > model_checksums.sha256
    cat model_checksums.sha256
    echo "已寫入 model_checksums.sha256"
    ;;
  verify)
    sha256sum -c model_checksums.sha256
    ;;
  *)
    echo "用法： $0 gen | verify"
    exit 1
    ;;
esac
