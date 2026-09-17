#!/usr/bin/env bash
# 新機器安裝：git clone + push_nongit.sh 傳完模型之後，在「目標機」的 repo 根目錄執行。
#
# 用法：
#   bash deploy/setup_new_machine.sh --check          # 只檢查缺什麼，不動系統
#   bash deploy/setup_new_machine.sh                  # 檢查 + 建 venv + 建 log 目錄
#   bash deploy/setup_new_machine.sh --cuda-arch auto # 順便編譯 GPU 版 llama-cpp-python
#                                                     # auto = 照 nvidia-smi 讀顯卡（也可寫死 120 / 89）
#                                                     # 沒有 CUDA toolkit 會問你要不要一起裝
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
CUDA_VERSION="12.9"     # toolkit 版本；配 llama-cpp-python 0.3.23 已驗證可用
ASSUME_YES=0
INSTALL_SERVICE=0
VERSION=""
ADDRCHECK_TOKEN="${ADDRCHECK_API_TOKEN:-請自行填入}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check)            CHECK_ONLY=1; shift ;;
    --cuda-arch)        CUDA_ARCH="$2"; shift 2 ;;
    --cuda-version)     CUDA_VERSION="$2"; shift 2 ;;
    --yes|-y)           ASSUME_YES=1; shift ;;
    --install-service)  INSTALL_SERVICE=1; shift ;;
    --version)          VERSION="$2"; shift 2 ;;
    -h|--help)          awk 'NR>1 && /^#/ {sub(/^# ?/,""); print; next} NR>1 {exit}' "$0"; exit 0 ;;
    *)                  echo "未知選項：$1" >&2; exit 2 ;;
  esac
done


# ── 小工具 ──────────────────────────────────────────────────────────────────
# 從 nvidia-smi 讀 compute capability（12.0 → 120），失敗回空字串
detect_cuda_arch() {
  command -v nvidia-smi >/dev/null || return 0
  nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null \
    | head -1 | tr -d ' .' | grep -E '^[0-9]+$' || true
}

find_nvcc() {
  command -v nvcc 2>/dev/null && return 0
  # 沒裝 toolkit 時 ls 會失敗；pipefail 會把失敗往外傳，沒有 || true 會讓整支腳本靜默結束
  ls /usr/local/cuda*/bin/nvcc 2>/dev/null | sort -V | tail -1 || true
}

# 裝 CUDA toolkit（只裝 toolkit，不碰顯卡驅動）
install_cuda_toolkit() {
  local ver="$1" pkg="cuda-toolkit-${1//./-}"
  command -v apt-get >/dev/null || { echo "  ！這台不是 Debian/Ubuntu，請自行安裝 CUDA toolkit $ver" >&2; return 1; }
  local id rel repo
  id="$(. /etc/os-release && echo "$ID")"
  rel="$(. /etc/os-release && echo "$VERSION_ID")"
  repo="${id}${rel//./}"                    # ubuntu + 24.04 → ubuntu2404
  [[ "$id" == "ubuntu" || "$id" == "debian" ]] || { echo "  ！不認得的發行版 $id，請自行安裝 CUDA toolkit" >&2; return 1; }

  echo "  準備安裝 $pkg（NVIDIA 官方 apt 來源 $repo）"
  echo "  下載約 4 GB、佔用約 9 GB 磁碟；只裝 toolkit，不會動到現有顯卡驅動。"
  if [[ $ASSUME_YES -eq 0 ]]; then
    read -r -p "  要現在安裝嗎？[y/N] " ans
    [[ "$ans" =~ ^[Yy] ]] || { echo "  跳過。"; return 1; }
  fi

  local keyring="/tmp/cuda-keyring_1.1-1_all.deb"
  local url="https://developer.download.nvidia.com/compute/cuda/repos/${repo}/x86_64/cuda-keyring_1.1-1_all.deb"
  echo "  下載 keyring：$url"
  wget -q -O "$keyring" "$url" || { echo "  ！keyring 下載失敗，$repo 可能沒有對應來源" >&2; return 1; }
  sudo dpkg -i "$keyring"
  sudo apt-get update
  # build-essential/cmake/ninja/python3-dev 是編譯 llama.cpp 要的
  sudo apt-get install -y "$pkg" build-essential cmake ninja-build python3-dev \
    || { echo "  ！$pkg 安裝失敗。可用 apt-cache search cuda-toolkit 看有哪些版本" >&2; return 1; }
  rm -f "$keyring"
}

# 沒指定就用 ai/ 底下最新的 119_* 版本目錄
if [[ -z "$VERSION" ]]; then
  # 同上：沒有 ai/119_* 時 ls 會失敗，pipefail 會讓腳本靜默結束，所以補 || true
  VERSION="$(ls -d "$BASE"/ai/119_* 2>/dev/null | grep -v '\.zip$' | sort | tail -1 | xargs -r basename || true)"
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

VENV_PY="$BASE/llmenv/bin/python"
VENV_PIP="$BASE/llmenv/bin/pip"

if [[ -x "$VENV_PY" && -x "$VENV_PIP" ]]; then
  echo "  [有] llmenv （$("$VENV_PY" -V 2>&1)）"
elif [[ -e "$BASE/llmenv" ]]; then
  # 缺 python3-venv 時 venv 會建到一半：有 python、沒有 pip。只檢查 python 會誤判成「已就緒」
  echo "  ！llmenv 不完整（有 python 但沒有 pip，通常是建立當下缺 python3-venv）"
  if [[ $CHECK_ONLY -eq 1 ]]; then
    echo "    本腳本會砍掉重建（不加 --check 執行即可）"
  else
    echo "    砍掉重建…"
    rm -rf "$BASE/llmenv"
    "$PY" -m venv "$BASE/llmenv"
  fi
elif [[ $CHECK_ONLY -eq 1 ]]; then
  echo "  [缺] llmenv（會由本腳本建立）"
else
  echo "  建立 llmenv…"
  "$PY" -m venv "$BASE/llmenv"
fi

# 套件：venv 好了才檢查。前一輪可能建到一半就中斷，所以每次都確認關鍵套件在不在
if [[ -x "$VENV_PIP" ]]; then
  if "$VENV_PY" -c 'import fastapi, uvicorn, transformers, torch' 2>/dev/null; then
    echo "  [有] 相依套件（fastapi / uvicorn / transformers / torch）"
  elif [[ $CHECK_ONLY -eq 1 ]]; then
    echo "  [缺] 相依套件（會由本腳本安裝 requirements-119.txt）"
  else
    echo "  安裝 requirements-119.txt（幾分鐘）…"
    "$VENV_PIP" install -U pip
    "$VENV_PIP" install -r "$BASE/requirements-119.txt"
    "$VENV_PY" -c 'import fastapi, uvicorn, transformers, torch' \
      || { echo "  ！套件裝完仍 import 失敗" >&2; exit 1; }
    echo "  llmenv 完成"
  fi
fi
echo

# ── 4. llama-cpp-python：一定要照顯卡自己編，pip 直裝會拿到 CPU 版
echo "== 4. llama-cpp-python (GPU) =="
DETECTED_ARCH="$(detect_cuda_arch)"
[[ "$CUDA_ARCH" == "auto" ]] && CUDA_ARCH="$DETECTED_ARCH"
[[ -n "$DETECTED_ARCH" ]] && echo "  顯卡 compute capability → arch $DETECTED_ARCH"

if [[ -x "$BASE/llmenv/bin/python" ]] && "$BASE/llmenv/bin/python" -c 'import llama_cpp' 2>/dev/null; then
  echo "  [有] $("$BASE/llmenv/bin/python" -c 'import llama_cpp; print(llama_cpp.__version__)')"
  if "$BASE/llmenv/bin/python" -c 'from llama_cpp import llama_cpp; exit(0 if llama_cpp.llama_supports_gpu_offload() else 1)' 2>/dev/null; then
    echo "  [有] GPU offload：開啟"
  else
    echo "  ！警告：裝的是 CPU 版（GPU offload 關閉），gguf 會慢到不能用"
    echo "    重編： $BASE/llmenv/bin/pip uninstall -y llama-cpp-python"
    echo "           bash deploy/setup_new_machine.sh --cuda-arch ${DETECTED_ARCH:-120}"
  fi
elif [[ -n "$CUDA_ARCH" && $CHECK_ONLY -eq 0 ]]; then
  NVCC="$(find_nvcc)"
  if [[ -z "$NVCC" ]]; then
    echo "  找不到 nvcc（有驅動不代表有 CUDA toolkit，編譯需要 toolkit）"
    install_cuda_toolkit "$CUDA_VERSION" || { echo "  ！沒有 CUDA toolkit，無法編譯" >&2; exit 1; }
    NVCC="$(find_nvcc)"
    [[ -n "$NVCC" ]] || { echo "  ！裝完仍找不到 nvcc" >&2; exit 1; }
  fi
  echo "  用 $NVCC 編譯 CUDA arch=$CUDA_ARCH（十幾分鐘）…"
  CMAKE_ARGS="-DGGML_CUDA=on -DCMAKE_CUDA_COMPILER=$NVCC -DCMAKE_CUDA_ARCHITECTURES=$CUDA_ARCH" \
    "$BASE/llmenv/bin/pip" install llama-cpp-python==0.3.23 --no-cache-dir
  # 編完立刻驗證：CPU 版也會 import 成功，只有這支 API 分得出來
  if "$BASE/llmenv/bin/python" -c 'from llama_cpp import llama_cpp; exit(0 if llama_cpp.llama_supports_gpu_offload() else 1)'; then
    echo "  ✓ 編譯完成，GPU offload 開啟"
  else
    echo "  ！編出來是 CPU 版（GPU offload 關閉）。檢查 nvcc 與顯卡 arch 是否相符" >&2
    exit 1
  fi
else
  echo "  [缺] 未安裝。要裝："
  echo "       bash deploy/setup_new_machine.sh --cuda-arch ${DETECTED_ARCH:-auto}"
  echo "       （沒有 CUDA toolkit 會先問你要不要一起裝）"
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
    # 機器上可能留著舊的 unit，指向別的目錄或舊版本，光看「有」會誤判
    UNIT_WD="$(grep -oP '(?<=^WorkingDirectory=).*' "$SERVICE" | tail -1 || true)"
    UNIT_EXEC="$(grep -oP '(?<=^ExecStart=)\S+' "$SERVICE" | tail -1 || true)"
    if [[ "$UNIT_WD" != "$BASE/ai/"* ]]; then
      echo "  ！unit 指向別的地方： $UNIT_WD"
      echo "    這份安裝在 $BASE，兩者不一致。要改指這裡："
      echo "    sudo ADDRCHECK_API_TOKEN='<token>' bash deploy/setup_new_machine.sh --install-service"
    else
      echo "      版本目錄： ${UNIT_WD##*/}$( [[ "${UNIT_WD##*/}" == "$VERSION" ]] && echo "" || echo "   ← 與偵測到的最新版 $VERSION 不同" )"
      [[ "$UNIT_EXEC" == "$BASE/llmenv/"* ]] || echo "  ！ExecStart 用的不是這份的 llmenv： $UNIT_EXEC"
      grep -q 'ADDRCHECK_API_TOKEN=請自行填入' "$SERVICE" && echo "  ！ADDRCHECK_API_TOKEN 還沒填"
    fi
  else
    echo "  [缺] 未安裝。要裝： sudo bash deploy/setup_new_machine.sh --install-service"
  fi
fi
echo
echo "== 檢查完畢 =="
