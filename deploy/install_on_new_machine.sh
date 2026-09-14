#!/usr/bin/env bash
# ============================================================================
#  119 專案 — 新電腦一鍵安裝（在「要安裝的那台電腦」上執行）
#
#  這支腳本是獨立的：clone 之前就能跑，只要先把這一個檔案帶過去即可。
#    scp cyberon2@100.127.225.115:~/nlp_cyberon_server/deploy/install_on_new_machine.sh .
#    bash install_on_new_machine.sh
#
#  它會依序做完：
#    1. 檢查工具 (git / python3 / rsync / ssh)
#    2. git clone 程式碼
#    3. 依 deploy/nongit_manifest.txt 抓非 git 檔案（模型/憑證，約 21G）
#    4. 建 log_119/、建 venv、裝 requirements-119.txt
#    5. （選）照顯卡編譯 GPU 版 llama-cpp-python
#    6. （選）安裝 systemd 服務 sop119.service
#
#  每一步都可重複執行：已完成的會自動跳過，傳到一半斷線再跑一次會續傳。
#
#  常用：
#    bash install_on_new_machine.sh                          # 走完 1~4，模型從 cyberon2 拉
#    bash install_on_new_machine.sh --from-dir /media/usb/nlp # 模型改從 USB 複製
#    bash install_on_new_machine.sh --skip-files             # 模型晚點再處理，先把環境弄好
#    bash install_on_new_machine.sh --all                    # 連 STT/TTS/110 模型一起（約 44G）
#    bash install_on_new_machine.sh --cuda-arch 120 --install-service   # 一路做到服務裝好
#
#  顯卡對應 --cuda-arch： RTX 5090 = 120、RTX 4090 = 89
# ============================================================================
set -euo pipefail

# ── 預設值（要改這裡就好）
REPO_URL="https://github.com/hetiande-tyiot/nlp_cyberon_server.git"
BRANCH="master"
DEST="$HOME/nlp_cyberon_server"
SRC_SSH="cyberon2@100.127.225.115"        # 來源機 cyberon2（Tailscale IP；同區網可改 192.168.5.132）
SRC_REPO="/home/cyberon2/nlp_cyberon_server"
FROM_DIR=""                                # 改從本機目錄/USB 取模型時用
TIERS="core"
SKIP_FILES=0
CUDA_ARCH=""
INSTALL_SERVICE=0
ADDRCHECK_TOKEN="${ADDRCHECK_API_TOKEN:-}"
MAX_RETRY=100

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)             REPO_URL="$2"; shift 2 ;;
    --branch)           BRANCH="$2"; shift 2 ;;
    --dest)             DEST="$2"; shift 2 ;;
    --from-ssh)         SRC_SSH="$2"; shift 2 ;;
    --src-repo)         SRC_REPO="$2"; shift 2 ;;
    --from-dir)         FROM_DIR="$2"; shift 2 ;;
    --all)              TIERS="core opt"; shift ;;
    --skip-files)       SKIP_FILES=1; shift ;;
    --cuda-arch)        CUDA_ARCH="$2"; shift 2 ;;
    --install-service)  INSTALL_SERVICE=1; shift ;;
    -h|--help)          sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)                  echo "未知選項：$1（用 --help 看說明）" >&2; exit 2 ;;
  esac
done

# SSH 連線共用：走密碼登入時只要輸入一次，之後每個 ssh/rsync 都重用同一條連線
SSH_CTL="${TMPDIR:-/tmp}/nlp-ssh-$$"
SSH_OPTS=(-o ControlMaster=auto -o ControlPath="$SSH_CTL" -o ControlPersist=10m -o ConnectTimeout=15)
RSH="ssh -o ControlMaster=auto -o ControlPath=$SSH_CTL -o ControlPersist=10m -o ConnectTimeout=15"
cleanup_ssh() { [[ -S "$SSH_CTL" ]] && ssh -o ControlPath="$SSH_CTL" -O exit "$SRC_SSH" 2>/dev/null; true; }
trap cleanup_ssh EXIT

say()  { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# ── 1. 環境檢查 ─────────────────────────────────────────────────────────────
say "1/6 檢查工具"
for cmd in git python3; do
  command -v "$cmd" >/dev/null || die "缺少 $cmd，請先安裝： sudo apt install -y $cmd"
  ok "$cmd  $($cmd --version 2>&1 | head -1)"
done
if command -v rsync >/dev/null; then
  ok "rsync $(rsync --version | head -1 | awk '{print $3}')（可續傳）"
  HAVE_RSYNC=1
else
  warn "沒有 rsync，會改用 scp（不能續傳，20G 斷線要整包重來）"
  warn "建議先裝： sudo apt install -y rsync"
  HAVE_RSYNC=0
fi
PY="$( [[ -x /usr/bin/python3 ]] && echo /usr/bin/python3 || command -v python3 )"
PYVER="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
[[ "$PYVER" == "3.12" ]] || warn "來源機是 Python 3.12，這台是 $PYVER；套件版本可能要微調"
"$PY" -c 'import venv' 2>/dev/null || die "缺少 venv： sudo apt install -y python3-venv"

# ── 2. clone 程式碼 ─────────────────────────────────────────────────────────
say "2/6 取得程式碼"
if [[ -d "$DEST/.git" ]]; then
  ok "已存在 $DEST，改用 git pull"
  git -C "$DEST" pull --ff-only origin "$BRANCH" || warn "pull 失敗（本機可能有改動），沿用現有內容"
else
  [[ -e "$DEST" ]] && die "$DEST 已存在但不是 git repo，請先處理"
  echo "  git clone $REPO_URL"
  git clone --branch "$BRANCH" "$REPO_URL" "$DEST"
  ok "clone 完成"
fi
cd "$DEST"
MANIFEST="$DEST/deploy/nongit_manifest.txt"
if [[ ! -f "$MANIFEST" ]]; then
  # deploy/ 還沒 push 上 GitHub 是最常見的原因；直接從來源機補一份，不用等 push
  warn "clone 出來沒有 deploy/nongit_manifest.txt（deploy/ 還沒 push 上 GitHub？）"
  if [[ -n "$FROM_DIR" && -f "$FROM_DIR/deploy/nongit_manifest.txt" ]]; then
    echo "  從 $FROM_DIR/deploy 補上"
    cp -r "$FROM_DIR/deploy" "$DEST/"
  elif [[ -n "$SRC_SSH" ]]; then
    echo "  從 ${SRC_SSH}:${SRC_REPO}/deploy 補上"
    scp -r -o ControlMaster=auto -o ControlPath="$SSH_CTL" -o ControlPersist=10m \
        "${SRC_SSH}:${SRC_REPO}/deploy" "$DEST/" || die "補 deploy/ 失敗"
  fi
  [[ -f "$MANIFEST" ]] || die "仍然沒有 deploy/nongit_manifest.txt。請先在來源機把 deploy/ commit 並 push，或用 --from-dir 指定一份"
  ok "deploy/ 已補齊（等來源機 push 之後，git pull 會蓋回正式版）"
fi

# ── 3. 抓非 git 檔案 ────────────────────────────────────────────────────────
say "3/6 取得非 git 檔案（模型／憑證）"
if [[ $SKIP_FILES -eq 1 ]]; then
  warn "--skip-files：跳過。之後可單獨補跑："
  warn "  bash $DEST/deploy/install_on_new_machine.sh --dest $DEST"
else
  # 解析清單，挑出這次要的層級
  PATHS=()
  while IFS= read -r line; do
    line="${line%%$'\t'#*}"
    [[ -z "${line// }" || "$line" == \#* ]] && continue
    tier="$(cut -f1 <<<"$line")"; path="$(cut -f2 <<<"$line")"
    [[ -n "$path" ]] || continue
    for t in $TIERS; do [[ "$tier" == "$t" ]] && PATHS+=("$path"); done
  done < "$MANIFEST"
  [[ ${#PATHS[@]} -gt 0 ]] || die "清單裡沒有 '$TIERS' 的項目"

  if [[ -n "$FROM_DIR" ]]; then
    echo "  來源：本機目錄 $FROM_DIR"
    [[ -d "$FROM_DIR" ]] || die "找不到 $FROM_DIR"
  else
    echo "  來源：${SRC_SSH}:${SRC_REPO}"
    echo "  測試 SSH 連線…"
    echo "  （走密碼登入的話這裡會問一次，之後不再問；免密碼請先 ssh-copy-id $SRC_SSH）"
    if ! ssh "${SSH_OPTS[@]}" "$SRC_SSH" "test -d '$SRC_REPO'"; then
      echo
      warn "連不上 ${SRC_SSH}（或對方沒有 $SRC_REPO）。兩種解法："
      warn "  (a) 把這台的公鑰加到來源機 —— 在這台執行："
      warn "        ssh-keygen -t ed25519            # 沒有金鑰才要跑"
      warn "        ssh-copy-id ${SRC_SSH}"
      warn "  (b) 反過來從來源機推過來 —— 在 cyberon2 上執行："
      warn "        cd ~/nlp_cyberon_server && deploy/push_nongit.sh $(whoami)@<這台的IP> --dest $DEST"
      warn "      推完再回來跑： bash $DEST/deploy/install_on_new_machine.sh --skip-files"
      die "無法取得模型檔案"
    fi
    ok "SSH 通了"
  fi

  for p in "${PATHS[@]}"; do
    # 目錄項目（結尾是 /）整包同步，檔案項目同步到所屬目錄
    if [[ "$p" == */ ]]; then local_dst="$DEST/$p"; else local_dst="$DEST/$(dirname "$p")/"; fi
    mkdir -p "$local_dst"

    if [[ -n "$FROM_DIR" ]]; then
      src="$FROM_DIR/$p"
      [[ -e "${src%/}" ]] || { warn "$p 在 $FROM_DIR 裡沒有，跳過"; continue; }
    else
      src="${SRC_SSH}:${SRC_REPO}/$p"
    fi

    # 已經完整存在就跳過（比對大小；遠端比不了就交給 rsync 判斷）
    echo
    echo "  ── $p"
    # 目標檔比來源大 = 不可能是「傳到一半」，多半是換了模型；續傳模式會直接跳過它，
    # 所以先砍掉重傳，免得留下舊權重卻以為傳好了。
    RSYNC_RESUME="--append-verify"
    if [[ "$p" == */ ]]; then
      RSYNC_RESUME=""                      # 目錄整包同步，不用續傳模式
    else
      if [[ -n "$FROM_DIR" ]]; then
        SRC_SIZE="$(stat -c %s "$src" 2>/dev/null || echo 0)"
      else
        SRC_SIZE="$(ssh "${SSH_OPTS[@]}" "$SRC_SSH" "stat -c %s '$SRC_REPO/$p'" 2>/dev/null || echo 0)"
      fi
      DST_FILE="$local_dst$(basename "$p")"
      DST_SIZE="$(stat -c %s "$DST_FILE" 2>/dev/null || echo 0)"
      if [[ "$DST_SIZE" -gt 0 && "$SRC_SIZE" -gt 0 && "$DST_SIZE" -gt "$SRC_SIZE" ]]; then
        warn "本機的比來源大（$DST_SIZE > $SRC_SIZE），應是舊版本，砍掉重傳"
        rm -f "$DST_FILE"
      fi
    fi
    if [[ $HAVE_RSYNC -eq 1 ]]; then
      n=0
      until rsync -avhP $RSYNC_RESUME -z --timeout=120 -e "$RSH" \
              --exclude='__pycache__/' --exclude='*.pyc' \
              "$src" "$local_dst"; do
        n=$((n + 1))
        [[ $n -ge $MAX_RETRY ]] && die "$p 重試 $MAX_RETRY 次仍失敗"
        echo "     …斷線，10 秒後續傳（第 $n 次）"
        sleep 10
      done
    else
      SCP_OPTS=(-o ControlMaster=auto -o ControlPath="$SSH_CTL" -o ControlPersist=10m)
      if [[ "$p" == */ ]]; then
        scp -r "${SCP_OPTS[@]}" "${src%/}" "$DEST/$(dirname "${p%/}")/"
      else
        scp "${SCP_OPTS[@]}" "$src" "$local_dst"
      fi
    fi
  done
  ok "檔案取得完成"
fi

# ── 4~6. 交給 setup_new_machine.sh（建 venv／編譯／裝服務）────────────────
SETUP="$DEST/deploy/setup_new_machine.sh"
[[ -f "$SETUP" ]] || die "找不到 $SETUP"

say "4/6 建立 venv 與 log 目錄"
SETUP_ARGS=()
[[ -n "$CUDA_ARCH" ]] && SETUP_ARGS+=(--cuda-arch "$CUDA_ARCH")
bash "$SETUP" "${SETUP_ARGS[@]}"

say "5/6 llama-cpp-python"
if [[ -z "$CUDA_ARCH" ]]; then
  warn "沒指定 --cuda-arch，略過編譯（上面第 4 步已印出指令）"
  warn "沒有 GPU 版 llama-cpp-python，模型會跑在 CPU 上，慢到不能用"
fi

say "6/6 systemd 服務"
if [[ $INSTALL_SERVICE -eq 1 ]]; then
  [[ -n "$ADDRCHECK_TOKEN" ]] || warn "沒帶 ADDRCHECK_API_TOKEN，unit 裡會留「請自行填入」，等一下要手動改"
  sudo env ADDRCHECK_API_TOKEN="$ADDRCHECK_TOKEN" bash "$SETUP" --install-service
else
  warn "略過。要裝服務："
  warn "  sudo ADDRCHECK_API_TOKEN='<token>' bash $SETUP --install-service"
fi

# ── 收尾 ────────────────────────────────────────────────────────────────────
say "安裝流程結束"
cat <<EOF
  專案位置： $DEST

  下一步：
    bash $DEST/deploy/setup_new_machine.sh --check     # 再確認一次每項都到齊
    sudo systemctl start sop119.service                # 啟動（載入模型要數十秒~數分）
    curl -s http://127.0.0.1:8200/health               # 三個 loaded 都 true 才算成功
    journalctl -u sop119.service -f                    # 起不來就看這裡

  提醒：119 是緊急服務。restart 前先看 /health 的 sessions，有通話中不要重啟。
EOF
