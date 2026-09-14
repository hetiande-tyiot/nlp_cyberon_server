#!/usr/bin/env bash
# 新機器安裝：git clone + push_nongit.sh 傳完模型之後，在「目標機」的 repo 根目錄執行。
#
# 用法：
#   bash deploy/setup_new_machine.sh --check          # 只檢查缺什麼，不動系統
#   bash deploy/setup_new_machine.sh                  # 檢查 + 建 venv + 建 log 目錄
#   bash deploy/setup_new_machine.sh --cuda-arch 120  # 順便編譯 GPU 版 llama-cpp-python（5090=120, 4090=89）
#   sudo bash deploy/setup_new_machine.sh --install-service   # 再裝 systemd 服務
#
# 不會做的事：不會自動 restart 線上服務（119 是緊急服務，換版/重啟前要先確認沒有通話中）。
set -euo pipefail

BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$BASE/deploy/nongit_manifest.txt"
TEMPLATE="$BASE/deploy/sop119.service.template"
SERVICE=/etc/systemd/system/sop119.service

CHECK_ONLY=0
CUDA_ARCH=""
INSTALL_SERVICE=0
VERSION=""
ADDRCHECK_TOKEN="${ADDRCHECK_API_TOKEN:-請自行填入}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check)            CHECK_ONLY=1; shift ;;
    --cuda-arch)        CUDA_ARCH="$2"; shift 2 ;;
    --install-service)  INSTALL_SERVICE=1; shift ;;
    --version)          VERSION="$2"; shift 2 ;;
    -h|--help)          sed -n '2,12p' "$0"; exit 0 ;;
    *)                  echo "未知選項：$1" >&2; exit 2 ;;
  esac
done

# 沒指定就用 ai/ 底下最新的 119_* 版本目錄
if [[ -z "$VERSION" ]]; then
  VERSION="$(ls -d "$BASE"/ai/119_* 2>/dev/null | grep -v '\.zip$' | sort | tail -1 | xargs -r basename)"
fi

echo "repo：   $BASE"
echo "版本：   ${VERSION:-（找不到 ai/119_* 目錄，clone 有成功嗎？）}"
echo

# ── 1. 檢查非 git 檔案到齊沒
echo "== 1. 檢查非 git 檔案（core）=="
MISSING=0
while IFS= read -r line; do
  line="${line%%$'\t'#*}"
  [[ -z "${line// }" || "$line" == \#* ]] && continue
  [[ "$(cut -f1 <<<"$line")" == "core" ]] || continue
  p="$(cut -f2 <<<"$line")"
  if [[ -e "$BASE/$p" ]]; then
    printf '  [有] %8s  %s\n' "$(du -sh "$BASE/$p" | cut -f1)" "$p"
  else
    printf '  [缺] %8s  %s\n' "-" "$p"
    MISSING=$((MISSING + 1))
  fi
done < "$MANIFEST"
if [[ $MISSING -gt 0 ]]; then
  echo
  echo "！少了 $MISSING 個必要檔案 —— 回來源機跑： deploy/push_nongit.sh <這台>"
  [[ $CHECK_ONLY -eq 1 ]] || exit 1
fi
echo

# ── 2. log 目錄
echo "== 2. log 目錄 =="
if [[ $CHECK_ONLY -eq 1 ]]; then
  [[ -d "$BASE/log_119" ]] && echo "  [有] log_119/" || echo "  [缺] log_119/（會由本腳本建立）"
else
  mkdir -p "$BASE/log_119"
  echo "  log_119/ 就緒"
fi
echo

# ── 3. venv（不從來源機複製，一定要在本機重建）
echo "== 3. venv (llmenv) =="
# 用系統 python 建 venv，避免在已啟用的 venv 裡再包一層
PY="$( [[ -x /usr/bin/python3 ]] && echo /usr/bin/python3 || command -v python3 || true )"
echo "  system python： ${PY:-沒有！} $( [[ -n "$PY" ]] && "$PY" -V 2>&1 )"
if [[ -x "$BASE/llmenv/bin/python" ]]; then
  echo "  [有] llmenv （$("$BASE/llmenv/bin/python" -V 2>&1)）"
elif [[ $CHECK_ONLY -eq 1 ]]; then
  echo "  [缺] llmenv（會由本腳本建立）"
else
  echo "  建立 llmenv 並安裝 requirements-119.txt（幾分鐘）…"
  "$PY" -m venv "$BASE/llmenv"
  "$BASE/llmenv/bin/pip" install -U pip
  "$BASE/llmenv/bin/pip" install -r "$BASE/requirements-119.txt"
  echo "  llmenv 完成"
fi
echo

# ── 4. llama-cpp-python：一定要照顯卡自己編，pip 直裝會拿到 CPU 版
echo "== 4. llama-cpp-python (GPU) =="
if [[ -x "$BASE/llmenv/bin/python" ]] && "$BASE/llmenv/bin/python" -c 'import llama_cpp' 2>/dev/null; then
  echo "  [有] $("$BASE/llmenv/bin/python" -c 'import llama_cpp; print(llama_cpp.__version__)')"
elif [[ -n "$CUDA_ARCH" && $CHECK_ONLY -eq 0 ]]; then
  NVCC="$(command -v nvcc || ls /usr/local/cuda*/bin/nvcc 2>/dev/null | sort | tail -1)"
  [[ -n "$NVCC" ]] || { echo "  ！找不到 nvcc，先裝 CUDA toolkit" >&2; exit 1; }
  echo "  用 $NVCC 編譯 CUDA arch=$CUDA_ARCH（十幾分鐘）…"
  CMAKE_ARGS="-DGGML_CUDA=on -DCMAKE_CUDA_COMPILER=$NVCC -DCMAKE_CUDA_ARCHITECTURES=$CUDA_ARCH" \
    "$BASE/llmenv/bin/pip" install llama-cpp-python==0.3.23 --no-cache-dir
else
  echo "  [缺] 未安裝。要裝請加 --cuda-arch（RTX 5090=120、RTX 4090=89），例如："
  echo "       bash deploy/setup_new_machine.sh --cuda-arch 120"
fi
echo

# ── 5. systemd 服務
echo "== 5. systemd (sop119.service) =="
if [[ $INSTALL_SERVICE -eq 1 ]]; then
  [[ $EUID -eq 0 ]] || { echo "  ！--install-service 要用 sudo 跑" >&2; exit 1; }
  [[ -n "$VERSION" ]] || { echo "  ！沒有版本目錄，無法產生 unit" >&2; exit 1; }
  if [[ -f "$SERVICE" ]]; then
    cp -a "$SERVICE" "${SERVICE}.bak.$(date +%Y%m%d_%H%M%S)"
    echo "  舊 unit 已備份"
  fi
  RUN_USER="${SUDO_USER:-$(stat -c '%U' "$BASE")}"
  sed -e "s#__BASE__#${BASE}#g" \
      -e "s#__USER__#${RUN_USER}#g" \
      -e "s#__VERSION__#${VERSION}#g" \
      -e "s#__ADDRCHECK_TOKEN__#${ADDRCHECK_TOKEN}#g" \
      "$TEMPLATE" > "$SERVICE"
  systemctl daemon-reload
  systemctl enable sop119.service
  echo "  已寫入 $SERVICE（User=$RUN_USER, 版本=$VERSION）"
  grep -E 'WorkingDirectory|ExecStart|ADDRCHECK_API_TOKEN' "$SERVICE" | sed 's/^/    /'
  echo
  echo "  ⚠ ADDRCHECK_API_TOKEN 若顯示「請自行填入」，請手動改 $SERVICE 後 systemctl daemon-reload"
  echo "  啟動： systemctl start sop119.service"
  echo "  檢查： curl -s http://127.0.0.1:8200/health   # 三個 loaded 都 true 才算成功"
else
  if [[ -f "$SERVICE" ]]; then
    echo "  [有] $SERVICE"
  else
    echo "  [缺] 未安裝。要裝： sudo bash deploy/setup_new_machine.sh --install-service"
  fi
fi
echo
echo "== 檢查完畢 =="
