"""119 引擎寫資料庫（MySQL fire119）用的連線設定範本。

複製成同目錄的 db_config_119.py 再填入帳號密碼；db_config_119.py 已列在 .gitignore，不會進 git。
沒有 db_config_119.py 時，引擎不寫資料庫，其他功能照常。
值與 apiserver/config.py 的 MYSQL_* 相同。
"""

MYSQL_HOST = "127.0.0.1"
MYSQL_USER = "api119"
MYSQL_PASS = ""
MYSQL_DB = "fire119"
