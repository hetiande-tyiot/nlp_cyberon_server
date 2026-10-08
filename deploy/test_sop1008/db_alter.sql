-- cases 加兩個欄位，分辨這通電話撥的是哪個號碼（911 正式 / 912 SOP 調整測試環境）
-- 用法：sudo mysql fire119 < db_alter.sql
-- 只新增欄位，舊資料不受影響（舊資料這兩欄是 NULL）。要在套用 apiserver.patch、重啟 apiserver 之前執行。
ALTER TABLE cases
  ADD COLUMN dialed_number VARCHAR(32) NULL COMMENT '撥打的號碼：911 正式 / 912 SOP 調整測試環境' AFTER channel,
  ADD COLUMN caller_number VARCHAR(32) NULL COMMENT '來電號碼（分機或外線號碼）' AFTER dialed_number;
