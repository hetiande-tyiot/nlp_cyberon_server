#!/usr/bin/env bash
# 把「會用到但沒上 git」的檔案傳到目標機（在來源機 cyberon2 的 repo 根目錄執行）。
#
# 用法：
#   deploy/push_nongit.sh <user@host> [選項]
#   deploy/push_nongit.sh aitop6@100.88.252.34                 # 只傳 core（119 主服務必要）
#   deploy/push_nongit.sh aitop6@100.88.252.34 --all           # core + opt（STT/TTS/110）
#   deploy/push_nongit.sh aitop6@100.88.252.34 --only opt      # 只傳 opt
#   deploy/push_nongit.sh aitop6@100.88.252.34 --dry-run       # 只看會傳什麼、多大
#   deploy/push_nongit.sh aitop6@100.88.252.34 --dest /home/aitop6/nlp_cyberon_server
#
# 預設用 rsync（可斷點續傳，斷線自動重試；Tailscale 中繼很慢，20G 的 gguf 一定要這條）。
# 目標機沒有 rsync 時加 --scp 改用 scp（不能續傳，斷了要整包重來）。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$REPO_ROOT/deploy/nongit_manifest.txt"

TARGET=""
DEST=""
TIERS="core"
DRY_RUN=0
USE_SCP=0
MAX_RETRY=100

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all)      TIERS="core opt"; shift ;;
    --only)     TIERS="$2"; shift 2 ;;
    --dest)     DEST="$2"; shift 2 ;;
    --dry-run)  DRY_RUN=1; shift ;;
    --scp)      USE_SCP=1; shift ;;
    -h|--help)  sed -n '2,20p' "$0"; exit 0 ;;
    -*)         echo "未知選項：$1" >&2; exit 2 ;;
    *)          TARGET="$1"; shift ;;
  esac
done

[[ -n "$TARGET" ]] || { echo "用法：deploy/push_nongit.sh <user@host> [--all|--only core|opt] [--dest PATH] [--dry-run] [--scp]" >&2; exit 2; }
[[ -f "$MANIFEST" ]] || { echo "找不到清單：$MANIFEST" >&2; exit 1; }

# 沒指定 --dest 就沿用對方 home 底下的同名目錄（和來源機同結構）
if [[ -z "$DEST" ]]; then
  REMOTE_USER="${TARGET%@*}"
  DEST="/home/${REMOTE_USER}/$(basename "$REPO_ROOT")"
fi

echo "來源： $REPO_ROOT"
echo "目標： ${TARGET}:${DEST}"
echo "層級： $TIERS"
echo "方式： $([[ $USE_SCP -eq 1 ]] && echo scp || echo 'rsync(續傳)')$([[ $DRY_RUN -eq 1 ]] && echo ' [dry-run]')"
echo

# ── 讀清單，挑出要傳的路徑
PATHS=()
while IFS= read -r line; do
  line="${line%%$'\t'#*}"                       # 砍掉行尾註解
  [[ -z "${line// }" || "$line" == \#* ]] && continue
  tier="$(cut -f1 <<<"$line")"
  path="$(cut -f2 <<<"$line")"
  [[ -n "$path" ]] || continue
  for t in $TIERS; do [[ "$tier" == "$t" ]] && PATHS+=("$path"); done
done < "$MANIFEST"

[[ ${#PATHS[@]} -gt 0 ]] || { echo "清單裡沒有符合 '$TIERS' 的項目" >&2; exit 1; }

# ── 先檢查來源檔在不在、算總量
MISSING=()
TOTAL_KB=0
echo "== 要傳的檔案 =="
for p in "${PATHS[@]}"; do
  src="$REPO_ROOT/$p"
  if [[ -e "$src" ]]; then
    kb="$(du -sk "$src" | cut -f1)"
    TOTAL_KB=$((TOTAL_KB + kb))
    printf '  %8s  %s\n' "$(du -sh "$src" | cut -f1)" "$p"
  else
    MISSING+=("$p")
  fi
done
if [[ ${#MISSING[@]} -gt 0 ]]; then
  echo
  echo "== 來源機上不存在（清單過期或本來就沒有，會跳過）=="
  printf '  %s\n' "${MISSING[@]}"
fi
echo
echo "總計約 $((TOTAL_KB / 1024)) MB"
echo

[[ $DRY_RUN -eq 1 ]] && { echo "(dry-run，沒有實際傳送)"; exit 0; }

# ── 目標端先建好各檔案所屬目錄
echo "== 在目標機建立目錄結構 =="
DIRS="$(for p in "${PATHS[@]}"; do [[ "$p" == */ ]] && echo "$DEST/$p" || dirname "$DEST/$p"; done | sort -u)"
# shellcheck disable=SC2029
ssh "$TARGET" "mkdir -p $(printf '%q ' $DIRS)"

# ── 逐項傳送
for p in "${PATHS[@]}"; do
  src="$REPO_ROOT/$p"
  [[ -e "$src" ]] || continue
  if [[ "$p" == */ ]]; then
    dst="$DEST/$p"          # 目錄：整包同步到同名目錄底下
  else
    dst="$DEST/$(dirname "$p")/"
  fi
  echo
  echo "== $p =="
  if [[ $USE_SCP -eq 1 ]]; then
    if [[ "$p" == */ ]]; then
      # scp -r 會把目錄本身再包一層，所以目錄要傳到「上一層」
      scp -r "${src%/}" "${TARGET}:${DEST}/$(dirname "${p%/}")/"
    else
      scp "$src" "${TARGET}:${dst}"
    fi
  else
    # 遠端檔比本機大 = 不是傳到一半，是對方留著舊版本；續傳模式會跳過，先砍掉
    RSYNC_RESUME="--append-verify"
    if [[ "$p" == */ ]]; then
      RSYNC_RESUME=""
    else
      SRC_SIZE="$(stat -c %s "$src" 2>/dev/null || echo 0)"
      DST_SIZE="$(ssh "$TARGET" "stat -c %s '$DEST/$p'" 2>/dev/null || echo 0)"
      if [[ "$DST_SIZE" -gt 0 && "$DST_SIZE" -gt "$SRC_SIZE" ]]; then
        echo "  目標機上的比較大（$DST_SIZE > $SRC_SIZE），應是舊版本，先刪除"
        ssh "$TARGET" "rm -f '$DEST/$p'"
      fi
    fi
    n=0
    until rsync -avhP $RSYNC_RESUME -z --timeout=120 \
            --exclude='__pycache__/' --exclude='*.pyc' \
            "$src" "${TARGET}:${dst}"; do
      n=$((n + 1))
      [[ $n -ge $MAX_RETRY ]] && { echo "！$p 重試 $MAX_RETRY 次仍失敗" >&2; exit 1; }
      echo "  ...斷線，10 秒後續傳（第 $n 次重試）"
      sleep 10
    done
  fi
done

echo
echo "== 傳完了 =="
echo "接著在目標機上跑： cd $DEST && bash deploy/setup_new_machine.sh"
