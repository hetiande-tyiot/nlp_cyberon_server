-- addrcheck_log 地址驗證 API 呼叫紀錄（fire119 資料庫，寫法比照 apiserver/schema_119.sql）
-- 119 引擎每呼叫一次 addrCheck /Verify 就寫入一筆，用來事後追查地址驗證的結果與耗時
-- 用法：sudo mysql fire119 < AddrCheckLog.sql

USE fire119;

CREATE TABLE IF NOT EXISTS addrcheck_log (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  uuid           VARCHAR(64),            -- 哪一通電話（與 cases.uuid 相同）；引擎以外的工具呼叫時為 NULL
  address        VARCHAR(500) NOT NULL,  -- 送出去驗證的地址
  addr_type      VARCHAR(20),            -- 送出的型態：House / Crossroad / Freeway / Landmark；沒帶型態時為 NULL
  status         TINYINT(1),             -- 1=有效、0=查無、NULL=API 無法使用（逾時或連不上）
  reason         VARCHAR(50),            -- API 回的失敗類別，例如 road_only、not_found
  hint           TEXT,                   -- API 回的提示文字
  elapsed_ms     INT,                    -- 這次呼叫花了幾毫秒
  error          TEXT,                   -- 逾時或連不上時的錯誤訊息
  created_at     DATETIME(3),            -- 呼叫驗證 API 的時間（記到毫秒，同一通的多次呼叫才排得出先後）
  INDEX idx_addrlog_uuid (uuid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
