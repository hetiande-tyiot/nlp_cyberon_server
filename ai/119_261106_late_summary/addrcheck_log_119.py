"""地址驗證 API（addrCheck /Verify）呼叫紀錄寫入 MySQL fire119.addrcheck_log。

寫法比照 apiserver/db.py。建表 SQL 在 docs/AddrCheckLog.sql。
連線資訊讀同目錄的 db_config_119.py（含密碼，不進 git；範本是 db_config_119.example.py）；
沒有這個檔就完全不寫（測試、離線腳本不受影響）。
寫入放在背景執行緒，資料庫慢或連不上都不會拖慢通話；失敗只印警告。
"""
import threading
from datetime import datetime
from typing import Optional

try:
    import db_config_119
except ImportError:
    db_config_119 = None


def _insert(row: tuple) -> None:
    try:
        import pymysql  # 只有真的要寫時才載入，沒裝套件的環境照樣能跑引擎

        db = pymysql.connect(
            host=db_config_119.MYSQL_HOST, user=db_config_119.MYSQL_USER,
            password=db_config_119.MYSQL_PASS, database=db_config_119.MYSQL_DB,
            charset="utf8mb4", autocommit=True,
        )
        with db.cursor() as cur:
            cur.execute(
                """INSERT INTO addrcheck_log
                   (uuid, address, addr_type, status, reason, hint, elapsed_ms, error, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                row,
            )
        db.close()
    except Exception as e:
        print(f"⚠️  MySQL addrcheck_log insert 失敗：{e}", flush=True)


def log_addrcheck(
    call_uuid: Optional[str],
    address: str,
    addr_type: Optional[str],
    status: Optional[bool],
    reason: Optional[str],
    hint: Optional[str],
    elapsed_ms: float,
    error: Optional[str],
    called_at: datetime,
) -> None:
    """記下一次地址驗證。status=None 代表 API 無法使用（逾時或連不上），原因放 error。"""
    if db_config_119 is None:
        return
    row = (
        call_uuid or None, address, addr_type,
        None if status is None else int(status),
        reason, hint, int(elapsed_ms), error, called_at,
    )
    threading.Thread(target=_insert, args=(row,), daemon=True).start()
