# Syncthing 連線測試（機器A → 機器B）

- 發送時間：2026-05-29
- 發送端：機器A（sipuser@wlas20，192.168.5.95）
- 連線方式：TCP 直連 192.168.5.204:22000（同區網，未走 relay）
- 連線狀態：`connected=True`

如果機器B 端的 `/home/aitop4/nlp_cyberon_server/docs/shared_with_A/` 出現這個檔案，
代表 Syncthing 雙向同步已成功運作。

請機器B 端在這份檔案下方追加一行回執，再讓 Syncthing 同步回來：

---

機器B 確認收到時間：__________

機器B 端可用任何方式回應（編輯本檔、或新建 `handshake-test-from-B.md`）。
