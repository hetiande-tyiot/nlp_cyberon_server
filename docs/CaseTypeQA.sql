-- CaseTypeQA 初始資料
-- 來源：1106 垂片規格 xlsx（docs/(all)火警、救護、災害、緊急救援垂片規格_關鍵要素與問句_1106.xlsx），經程式用的題號對照表 scripts/CaseTypeQA.xlsx 整理；CaseTypeId 對照 案類資料表.csv
-- 2 救護（00-未知）、200 救護-未知 不在 1106 垂片 xlsx 裡，保留原本的內容
-- QuestionId、SeqNo 都是各次案類內的題號，就是程式送給前端的「次案類編號-第N題」的 N；Serial 為資料庫自動編號不寫入；Type：1=必問(主動) 2=條件式必問(條件) 3=選問(被動)；Answer：xlsx 用一句話問兩個關鍵要素的題目（例如性別和年齡），兩題各寫自己的單獨問句；被動題（報案人自己會講、不主動問）沒有問句，寫空字串

-- 2 救護（00-未知）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (2, 1, 1, N'病徵', N'請問發生什麼事？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (2, 2, 2, N'患者人數', N'現場有幾個人需要救護？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (2, 3, 3, N'意識', N'他現在人清醒嗎？叫他有沒有反應？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (2, 4, 4, N'呼吸', N'他還有沒有呼吸？胸口、肚子有沒有一上一下起伏？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (2, 5, 5, N'年齡', N'他大概幾歲？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (2, 6, 6, N'性別', N'他是男生還是女生？', 1);

-- 101 火警-透天厝（01-垂片A_建築物火警）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (101, 1, 1, N'場所用途', N'請問是哪一種建築物？住宅還是工廠呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (101, 2, 2, N'建築物類型', N'是公寓、透天還是大樓？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (101, 3, 3, N'建築物類型', N'現場是什麼用途？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (101, 4, 4, N'建物總樓層', N'總共幾層樓？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (101, 5, 5, N'火煙狀況', N'現在有看到火嗎？還是只有看到煙？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (101, 6, 6, N'濃煙顏色', N'是黑煙還是白煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (101, 7, 7, N'起火樓層', N'是幾樓在冒火冒煙呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (101, 8, 8, N'燃燒物', N'知道是什麼東西在燒嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (101, 9, 9, N'是否延燒', N'火大概燒多大？會波及到旁邊的房子嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (101, 10, 10, N'報案身分', N'請問您是住在附近，還是路人？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (101, 11, 11, N'人員受困', N'裡面還有沒有人沒出來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (101, 12, 12, N'起火戶應門', N'有去敲過門嗎？裡面有人回應嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (101, 13, 13, N'建物構造', N'請問是鐵皮工廠嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (101, 14, 14, N'危險物品', N'裡面有什麼易燃物品嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (101, 15, 15, N'有無爆炸', N'剛剛有沒有聽到爆炸的聲音？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (101, 16, 16, N'水源狀況', N'那邊消防車進得去嗎？附近有水源嗎？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (101, 17, 17, N'燃燒面積', N'現在燒起來的範圍大概多大？', 3);

-- 102 火警-集合住宅（01-垂片A_建築物火警）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (102, 1, 1, N'場所用途', N'請問是哪一種建築物？住宅還是工廠呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (102, 2, 2, N'建築物類型', N'是公寓、透天還是大樓？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (102, 3, 3, N'建築物類型', N'現場是什麼用途？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (102, 4, 4, N'建物總樓層', N'總共幾層樓？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (102, 5, 5, N'火煙狀況', N'現在有看到火嗎？還是只有看到煙？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (102, 6, 6, N'濃煙顏色', N'是黑煙還是白煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (102, 7, 7, N'起火樓層', N'是幾樓在冒火冒煙呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (102, 8, 8, N'燃燒物', N'知道是什麼東西在燒嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (102, 9, 9, N'是否延燒', N'火大概燒多大？會波及到旁邊的房子嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (102, 10, 10, N'報案身分', N'請問您是住在附近，還是路人？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (102, 11, 11, N'人員受困', N'裡面還有沒有人沒出來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (102, 12, 12, N'起火戶應門', N'有去敲過門嗎？裡面有人回應嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (102, 13, 13, N'建物構造', N'請問是鐵皮工廠嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (102, 14, 14, N'危險物品', N'裡面有什麼易燃物品嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (102, 15, 15, N'有無爆炸', N'剛剛有沒有聽到爆炸的聲音？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (102, 16, 16, N'水源狀況', N'那邊消防車進得去嗎？附近有水源嗎？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (102, 17, 17, N'燃燒面積', N'現在燒起來的範圍大概多大？', 3);

-- 103 火警-倉庫（01-垂片A_建築物火警）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (103, 1, 1, N'場所用途', N'請問是哪一種建築物？住宅還是工廠呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (103, 2, 2, N'建築物類型', N'是公寓、透天還是大樓？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (103, 3, 3, N'建築物類型', N'現場是什麼用途？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (103, 4, 4, N'建物總樓層', N'總共幾層樓？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (103, 5, 5, N'火煙狀況', N'現在有看到火嗎？還是只有看到煙？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (103, 6, 6, N'濃煙顏色', N'是黑煙還是白煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (103, 7, 7, N'起火樓層', N'是幾樓在冒火冒煙呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (103, 8, 8, N'燃燒物', N'知道是什麼東西在燒嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (103, 9, 9, N'是否延燒', N'火大概燒多大？會波及到旁邊的房子嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (103, 10, 10, N'報案身分', N'請問您是住在附近，還是路人？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (103, 11, 11, N'人員受困', N'裡面還有沒有人沒出來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (103, 12, 12, N'起火戶應門', N'有去敲過門嗎？裡面有人回應嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (103, 13, 13, N'建物構造', N'請問是鐵皮工廠嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (103, 14, 14, N'危險物品', N'裡面有什麼易燃物品嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (103, 15, 15, N'有無爆炸', N'剛剛有沒有聽到爆炸的聲音？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (103, 16, 16, N'水源狀況', N'那邊消防車進得去嗎？附近有水源嗎？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (103, 17, 17, N'燃燒面積', N'現在燒起來的範圍大概多大？', 3);

-- 104 火警-旅館、百貨商場用途建築物（01-垂片A_建築物火警）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (104, 1, 1, N'場所用途', N'請問是哪一種建築物？住宅還是工廠呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (104, 2, 2, N'建築物類型', N'是公寓、透天還是大樓？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (104, 3, 3, N'建築物類型', N'現場是什麼用途？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (104, 4, 4, N'建物總樓層', N'總共幾層樓？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (104, 5, 5, N'火煙狀況', N'現在有看到火嗎？還是只有看到煙？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (104, 6, 6, N'濃煙顏色', N'是黑煙還是白煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (104, 7, 7, N'起火樓層', N'是幾樓在冒火冒煙呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (104, 8, 8, N'燃燒物', N'知道是什麼東西在燒嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (104, 9, 9, N'是否延燒', N'火大概燒多大？會波及到旁邊的房子嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (104, 10, 10, N'報案身分', N'請問您是住在附近，還是路人？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (104, 11, 11, N'人員受困', N'裡面還有沒有人沒出來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (104, 12, 12, N'起火戶應門', N'有去敲過門嗎？裡面有人回應嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (104, 13, 13, N'建物構造', N'請問是鐵皮工廠嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (104, 14, 14, N'危險物品', N'裡面有什麼易燃物品嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (104, 15, 15, N'有無爆炸', N'剛剛有沒有聽到爆炸的聲音？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (104, 16, 16, N'水源狀況', N'那邊消防車進得去嗎？附近有水源嗎？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (104, 17, 17, N'燃燒面積', N'現在燒起來的範圍大概多大？', 3);

-- 105 火警-運輸中樞用途建築物（01-垂片A_建築物火警）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (105, 1, 1, N'場所用途', N'請問是哪一種建築物？住宅還是工廠呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (105, 2, 2, N'建築物類型', N'是公寓、透天還是大樓？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (105, 3, 3, N'建築物類型', N'現場是什麼用途？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (105, 4, 4, N'建物總樓層', N'總共幾層樓？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (105, 5, 5, N'火煙狀況', N'現在有看到火嗎？還是只有看到煙？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (105, 6, 6, N'濃煙顏色', N'是黑煙還是白煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (105, 7, 7, N'起火樓層', N'是幾樓在冒火冒煙呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (105, 8, 8, N'燃燒物', N'知道是什麼東西在燒嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (105, 9, 9, N'是否延燒', N'火大概燒多大？會波及到旁邊的房子嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (105, 10, 10, N'報案身分', N'請問您是住在附近，還是路人？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (105, 11, 11, N'人員受困', N'裡面還有沒有人沒出來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (105, 12, 12, N'起火戶應門', N'有去敲過門嗎？裡面有人回應嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (105, 13, 13, N'建物構造', N'請問是鐵皮工廠嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (105, 14, 14, N'危險物品', N'裡面有什麼易燃物品嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (105, 15, 15, N'有無爆炸', N'剛剛有沒有聽到爆炸的聲音？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (105, 16, 16, N'水源狀況', N'那邊消防車進得去嗎？附近有水源嗎？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (105, 17, 17, N'燃燒面積', N'現在燒起來的範圍大概多大？', 3);

-- 106 火警-電影院用途建築物（01-垂片A_建築物火警）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (106, 1, 1, N'場所用途', N'請問是哪一種建築物？住宅還是工廠呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (106, 2, 2, N'建築物類型', N'是公寓、透天還是大樓？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (106, 3, 3, N'建築物類型', N'現場是什麼用途？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (106, 4, 4, N'建物總樓層', N'總共幾層樓？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (106, 5, 5, N'火煙狀況', N'現在有看到火嗎？還是只有看到煙？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (106, 6, 6, N'濃煙顏色', N'是黑煙還是白煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (106, 7, 7, N'起火樓層', N'是幾樓在冒火冒煙呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (106, 8, 8, N'燃燒物', N'知道是什麼東西在燒嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (106, 9, 9, N'是否延燒', N'火大概燒多大？會波及到旁邊的房子嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (106, 10, 10, N'報案身分', N'請問您是住在附近，還是路人？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (106, 11, 11, N'人員受困', N'裡面還有沒有人沒出來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (106, 12, 12, N'起火戶應門', N'有去敲過門嗎？裡面有人回應嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (106, 13, 13, N'建物構造', N'請問是鐵皮工廠嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (106, 14, 14, N'危險物品', N'裡面有什麼易燃物品嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (106, 15, 15, N'有無爆炸', N'剛剛有沒有聽到爆炸的聲音？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (106, 16, 16, N'水源狀況', N'那邊消防車進得去嗎？附近有水源嗎？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (106, 17, 17, N'燃燒面積', N'現在燒起來的範圍大概多大？', 3);

-- 107 火警-學校、醫院、老人院建築物（01-垂片A_建築物火警）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (107, 1, 1, N'場所用途', N'請問是哪一種建築物？住宅還是工廠呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (107, 2, 2, N'建築物類型', N'是公寓、透天還是大樓？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (107, 3, 3, N'建築物類型', N'現場是什麼用途？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (107, 4, 4, N'建物總樓層', N'總共幾層樓？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (107, 5, 5, N'火煙狀況', N'現在有看到火嗎？還是只有看到煙？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (107, 6, 6, N'濃煙顏色', N'是黑煙還是白煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (107, 7, 7, N'起火樓層', N'是幾樓在冒火冒煙呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (107, 8, 8, N'燃燒物', N'知道是什麼東西在燒嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (107, 9, 9, N'是否延燒', N'火大概燒多大？會波及到旁邊的房子嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (107, 10, 10, N'報案身分', N'請問您是住在附近，還是路人？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (107, 11, 11, N'人員受困', N'裡面還有沒有人沒出來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (107, 12, 12, N'起火戶應門', N'有去敲過門嗎？裡面有人回應嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (107, 13, 13, N'建物構造', N'請問是鐵皮工廠嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (107, 14, 14, N'危險物品', N'裡面有什麼易燃物品嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (107, 15, 15, N'有無爆炸', N'剛剛有沒有聽到爆炸的聲音？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (107, 16, 16, N'水源狀況', N'那邊消防車進得去嗎？附近有水源嗎？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (107, 17, 17, N'燃燒面積', N'現在燒起來的範圍大概多大？', 3);

-- 108 火警-毒災場所（01-垂片A_建築物火警）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (108, 1, 1, N'場所用途', N'請問是哪一種建築物？住宅還是工廠呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (108, 2, 2, N'建築物類型', N'是公寓、透天還是大樓？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (108, 3, 3, N'建築物類型', N'現場是什麼用途？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (108, 4, 4, N'建物總樓層', N'總共幾層樓？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (108, 5, 5, N'火煙狀況', N'現在有看到火嗎？還是只有看到煙？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (108, 6, 6, N'濃煙顏色', N'是黑煙還是白煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (108, 7, 7, N'起火樓層', N'是幾樓在冒火冒煙呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (108, 8, 8, N'燃燒物', N'知道是什麼東西在燒嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (108, 9, 9, N'是否延燒', N'火大概燒多大？會波及到旁邊的房子嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (108, 10, 10, N'報案身分', N'請問您是住在附近，還是路人？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (108, 11, 11, N'人員受困', N'裡面還有沒有人沒出來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (108, 12, 12, N'起火戶應門', N'有去敲過門嗎？裡面有人回應嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (108, 13, 13, N'建物構造', N'請問是鐵皮工廠嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (108, 14, 14, N'危險物品', N'裡面有什麼易燃物品嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (108, 15, 15, N'有無爆炸', N'剛剛有沒有聽到爆炸的聲音？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (108, 16, 16, N'水源狀況', N'那邊消防車進得去嗎？附近有水源嗎？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (108, 17, 17, N'燃燒面積', N'現在燒起來的範圍大概多大？', 3);

-- 109 火警-大型違章建築區與傳統市場(含工廠)（01-垂片A_建築物火警）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (109, 1, 1, N'場所用途', N'請問是哪一種建築物？住宅還是工廠呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (109, 2, 2, N'建築物類型', N'是公寓、透天還是大樓？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (109, 3, 3, N'建築物類型', N'現場是什麼用途？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (109, 4, 4, N'建物總樓層', N'總共幾層樓？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (109, 5, 5, N'火煙狀況', N'現在有看到火嗎？還是只有看到煙？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (109, 6, 6, N'濃煙顏色', N'是黑煙還是白煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (109, 7, 7, N'起火樓層', N'是幾樓在冒火冒煙呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (109, 8, 8, N'燃燒物', N'知道是什麼東西在燒嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (109, 9, 9, N'是否延燒', N'火大概燒多大？會波及到旁邊的房子嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (109, 10, 10, N'報案身分', N'請問您是住在附近，還是路人？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (109, 11, 11, N'人員受困', N'裡面還有沒有人沒出來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (109, 12, 12, N'起火戶應門', N'有去敲過門嗎？裡面有人回應嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (109, 13, 13, N'建物構造', N'請問是鐵皮工廠嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (109, 14, 14, N'危險物品', N'裡面有什麼易燃物品嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (109, 15, 15, N'有無爆炸', N'剛剛有沒有聽到爆炸的聲音？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (109, 16, 16, N'水源狀況', N'那邊消防車進得去嗎？附近有水源嗎？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (109, 17, 17, N'燃燒面積', N'現在燒起來的範圍大概多大？', 3);

-- 110 火警-石化廠建築物（01-垂片A_建築物火警）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (110, 1, 1, N'場所用途', N'請問是哪一種建築物？住宅還是工廠呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (110, 2, 2, N'建築物類型', N'是公寓、透天還是大樓？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (110, 3, 3, N'建築物類型', N'現場是什麼用途？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (110, 4, 4, N'建物總樓層', N'總共幾層樓？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (110, 5, 5, N'火煙狀況', N'現在有看到火嗎？還是只有看到煙？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (110, 6, 6, N'濃煙顏色', N'是黑煙還是白煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (110, 7, 7, N'起火樓層', N'是幾樓在冒火冒煙呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (110, 8, 8, N'燃燒物', N'知道是什麼東西在燒嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (110, 9, 9, N'是否延燒', N'火大概燒多大？會波及到旁邊的房子嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (110, 10, 10, N'報案身分', N'請問您是住在附近，還是路人？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (110, 11, 11, N'人員受困', N'裡面還有沒有人沒出來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (110, 12, 12, N'起火戶應門', N'有去敲過門嗎？裡面有人回應嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (110, 13, 13, N'建物構造', N'請問是鐵皮工廠嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (110, 14, 14, N'危險物品', N'裡面有什麼易燃物品嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (110, 15, 15, N'有無爆炸', N'剛剛有沒有聽到爆炸的聲音？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (110, 16, 16, N'水源狀況', N'那邊消防車進得去嗎？附近有水源嗎？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (110, 17, 17, N'燃燒面積', N'現在燒起來的範圍大概多大？', 3);

-- 111 火警-古蹟、文化財（01-垂片A_建築物火警）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (111, 1, 1, N'場所用途', N'請問是哪一種建築物？住宅還是工廠呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (111, 2, 2, N'建築物類型', N'是公寓、透天還是大樓？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (111, 3, 3, N'建築物類型', N'現場是什麼用途？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (111, 4, 4, N'建物總樓層', N'總共幾層樓？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (111, 5, 5, N'火煙狀況', N'現在有看到火嗎？還是只有看到煙？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (111, 6, 6, N'濃煙顏色', N'是黑煙還是白煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (111, 7, 7, N'起火樓層', N'是幾樓在冒火冒煙呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (111, 8, 8, N'燃燒物', N'知道是什麼東西在燒嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (111, 9, 9, N'是否延燒', N'火大概燒多大？會波及到旁邊的房子嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (111, 10, 10, N'報案身分', N'請問您是住在附近，還是路人？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (111, 11, 11, N'人員受困', N'裡面還有沒有人沒出來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (111, 12, 12, N'起火戶應門', N'有去敲過門嗎？裡面有人回應嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (111, 13, 13, N'建物構造', N'請問是鐵皮工廠嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (111, 14, 14, N'危險物品', N'裡面有什麼易燃物品嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (111, 15, 15, N'有無爆炸', N'剛剛有沒有聽到爆炸的聲音？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (111, 16, 16, N'水源狀況', N'那邊消防車進得去嗎？附近有水源嗎？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (111, 17, 17, N'燃燒面積', N'現在燒起來的範圍大概多大？', 3);

-- 112 火警-地下建築物(如地下街)（01-垂片A_建築物火警）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (112, 1, 1, N'場所用途', N'請問是哪一種建築物？住宅還是工廠呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (112, 2, 2, N'建築物類型', N'是公寓、透天還是大樓？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (112, 3, 3, N'建築物類型', N'現場是什麼用途？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (112, 4, 4, N'建物總樓層', N'總共幾層樓？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (112, 5, 5, N'火煙狀況', N'現在有看到火嗎？還是只有看到煙？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (112, 6, 6, N'濃煙顏色', N'是黑煙還是白煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (112, 7, 7, N'起火樓層', N'是幾樓在冒火冒煙呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (112, 8, 8, N'燃燒物', N'知道是什麼東西在燒嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (112, 9, 9, N'是否延燒', N'火大概燒多大？會波及到旁邊的房子嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (112, 10, 10, N'報案身分', N'請問您是住在附近，還是路人？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (112, 11, 11, N'人員受困', N'裡面還有沒有人沒出來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (112, 12, 12, N'起火戶應門', N'有去敲過門嗎？裡面有人回應嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (112, 13, 13, N'建物構造', N'請問是鐵皮工廠嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (112, 14, 14, N'危險物品', N'裡面有什麼易燃物品嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (112, 15, 15, N'有無爆炸', N'剛剛有沒有聽到爆炸的聲音？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (112, 16, 16, N'水源狀況', N'那邊消防車進得去嗎？附近有水源嗎？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (112, 17, 17, N'燃燒面積', N'現在燒起來的範圍大概多大？', 3);

-- 113 火警-高層建築物(10層樓以上)（01-垂片A_建築物火警）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (113, 1, 1, N'場所用途', N'請問是哪一種建築物？住宅還是工廠呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (113, 2, 2, N'建築物類型', N'是公寓、透天還是大樓？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (113, 3, 3, N'建築物類型', N'現場是什麼用途？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (113, 4, 4, N'建物總樓層', N'總共幾層樓？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (113, 5, 5, N'火煙狀況', N'現在有看到火嗎？還是只有看到煙？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (113, 6, 6, N'濃煙顏色', N'是黑煙還是白煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (113, 7, 7, N'起火樓層', N'是幾樓在冒火冒煙呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (113, 8, 8, N'燃燒物', N'知道是什麼東西在燒嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (113, 9, 9, N'是否延燒', N'火大概燒多大？會波及到旁邊的房子嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (113, 10, 10, N'報案身分', N'請問您是住在附近，還是路人？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (113, 11, 11, N'人員受困', N'裡面還有沒有人沒出來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (113, 12, 12, N'起火戶應門', N'有去敲過門嗎？裡面有人回應嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (113, 13, 13, N'建物構造', N'請問是鐵皮工廠嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (113, 14, 14, N'危險物品', N'裡面有什麼易燃物品嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (113, 15, 15, N'有無爆炸', N'剛剛有沒有聽到爆炸的聲音？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (113, 16, 16, N'水源狀況', N'那邊消防車進得去嗎？附近有水源嗎？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (113, 17, 17, N'燃燒面積', N'現在燒起來的範圍大概多大？', 3);

-- 120 火警-汽車（02-垂片B1_交通工具）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (120, 1, 1, N'交通工具', N'請問是什麼車燒起來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (120, 2, 2, N'車輛動力(汽車)', N'請問是油車、油電車還是電動車呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (120, 3, 3, N'車輛動力(機車)', N'請問是油車還是電動車呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (120, 4, 4, N'腳踏車車型', N'請問是一般腳踏車、U bike 還是電輔車？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (120, 5, 5, N'火煙狀況', N'現在有看到火嗎？還是只有看到煙？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (120, 6, 6, N'濃煙顏色', N'請問是黑煙還是白煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (120, 7, 7, N'報案身分', N'請問您是車主或駕駛嗎？還是路人呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (120, 8, 8, N'是否延燒', N'火有沒有燒到旁邊的東西？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (120, 9, 9, N'起火部位', N'是車頭還是後車廂燒起來了呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (120, 10, 10, N'起火車輛數量', N'現場有幾台在燒呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (120, 11, 11, N'熄火狀態', N'車子引擎關掉了嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (120, 12, 12, N'人員受困', N'車上的人都出來了嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (120, 13, 13, N'患者人數', N'有人受傷嗎？幾個人受傷呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (120, 14, 14, N'載運物', N'車上有易燃物品之類的嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (120, 15, 15, N'滅火狀況', N'現場有人在滅火嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (120, 16, 16, N'車輛行駛狀況', N'車子是行駛中還是停在路邊呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (120, 17, 17, N'車牌號碼', N'車牌號碼看得到嗎？', 3);

-- 121 火警-機車（02-垂片B1_交通工具）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (121, 1, 1, N'交通工具', N'請問是什麼車燒起來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (121, 2, 2, N'車輛動力(汽車)', N'請問是油車、油電車還是電動車呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (121, 3, 3, N'車輛動力(機車)', N'請問是油車還是電動車呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (121, 4, 4, N'腳踏車車型', N'請問是一般腳踏車、U bike 還是電輔車？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (121, 5, 5, N'火煙狀況', N'現在有看到火嗎？還是只有看到煙？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (121, 6, 6, N'濃煙顏色', N'請問是黑煙還是白煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (121, 7, 7, N'報案身分', N'請問您是車主或駕駛嗎？還是路人呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (121, 8, 8, N'是否延燒', N'火有沒有燒到旁邊的東西？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (121, 9, 9, N'起火部位', N'是車頭還是後車廂燒起來了呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (121, 10, 10, N'起火車輛數量', N'現場有幾台在燒呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (121, 11, 11, N'熄火狀態', N'車子引擎關掉了嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (121, 12, 12, N'人員受困', N'車上的人都出來了嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (121, 13, 13, N'患者人數', N'有人受傷嗎？幾個人受傷呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (121, 14, 14, N'載運物', N'車上有易燃物品之類的嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (121, 15, 15, N'滅火狀況', N'現場有人在滅火嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (121, 16, 16, N'車輛行駛狀況', N'車子是行駛中還是停在路邊呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (121, 17, 17, N'車牌號碼', N'車牌號碼看得到嗎？', 3);

-- 122 火警-隧道（02-垂片B1_交通工具）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (122, 1, 1, N'交通工具', N'請問是什麼車燒起來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (122, 2, 2, N'車輛動力(汽車)', N'請問是油車、油電車還是電動車呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (122, 3, 3, N'車輛動力(機車)', N'請問是油車還是電動車呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (122, 4, 4, N'腳踏車車型', N'請問是一般腳踏車、U bike 還是電輔車？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (122, 5, 5, N'火煙狀況', N'現在有看到火嗎？還是只有看到煙？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (122, 6, 6, N'濃煙顏色', N'請問是黑煙還是白煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (122, 7, 7, N'報案身分', N'請問您是車主或駕駛嗎？還是路人呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (122, 8, 8, N'是否延燒', N'火有沒有燒到旁邊的東西？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (122, 9, 9, N'起火部位', N'是車頭還是後車廂燒起來了呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (122, 10, 10, N'起火車輛數量', N'現場有幾台在燒呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (122, 11, 11, N'熄火狀態', N'車子引擎關掉了嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (122, 12, 12, N'人員受困', N'車上的人都出來了嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (122, 13, 13, N'患者人數', N'有人受傷嗎？幾個人受傷呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (122, 14, 14, N'載運物', N'車上有易燃物品之類的嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (122, 15, 15, N'滅火狀況', N'現場有人在滅火嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (122, 16, 16, N'車輛行駛狀況', N'車子是行駛中還是停在路邊呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (122, 17, 17, N'車牌號碼', N'車牌號碼看得到嗎？', 3);

-- 123 火警-軌道型交通工具（02-垂片B1_交通工具）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (123, 1, 1, N'交通工具', N'請問是什麼車燒起來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (123, 2, 2, N'車輛動力(汽車)', N'請問是油車、油電車還是電動車呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (123, 3, 3, N'車輛動力(機車)', N'請問是油車還是電動車呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (123, 4, 4, N'腳踏車車型', N'請問是一般腳踏車、U bike 還是電輔車？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (123, 5, 5, N'火煙狀況', N'現在有看到火嗎？還是只有看到煙？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (123, 6, 6, N'濃煙顏色', N'請問是黑煙還是白煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (123, 7, 7, N'報案身分', N'請問您是車主或駕駛嗎？還是路人呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (123, 8, 8, N'是否延燒', N'火有沒有燒到旁邊的東西？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (123, 9, 9, N'起火部位', N'是車頭還是後車廂燒起來了呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (123, 10, 10, N'起火車輛數量', N'現場有幾台在燒呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (123, 11, 11, N'熄火狀態', N'車子引擎關掉了嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (123, 12, 12, N'人員受困', N'車上的人都出來了嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (123, 13, 13, N'患者人數', N'有人受傷嗎？幾個人受傷呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (123, 14, 14, N'載運物', N'車上有易燃物品之類的嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (123, 15, 15, N'滅火狀況', N'現場有人在滅火嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (123, 16, 16, N'車輛行駛狀況', N'車子是行駛中還是停在路邊呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (123, 17, 17, N'車牌號碼', N'車牌號碼看得到嗎？', 3);

-- 124 火警-化學、毒劑交通工具（02-垂片B1_交通工具）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (124, 1, 1, N'交通工具', N'請問是什麼車燒起來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (124, 2, 2, N'車輛動力(汽車)', N'請問是油車、油電車還是電動車呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (124, 3, 3, N'車輛動力(機車)', N'請問是油車還是電動車呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (124, 4, 4, N'腳踏車車型', N'請問是一般腳踏車、U bike 還是電輔車？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (124, 5, 5, N'火煙狀況', N'現在有看到火嗎？還是只有看到煙？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (124, 6, 6, N'濃煙顏色', N'請問是黑煙還是白煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (124, 7, 7, N'報案身分', N'請問您是車主或駕駛嗎？還是路人呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (124, 8, 8, N'是否延燒', N'火有沒有燒到旁邊的東西？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (124, 9, 9, N'起火部位', N'是車頭還是後車廂燒起來了呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (124, 10, 10, N'起火車輛數量', N'現場有幾台在燒呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (124, 11, 11, N'熄火狀態', N'車子引擎關掉了嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (124, 12, 12, N'人員受困', N'車上的人都出來了嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (124, 13, 13, N'患者人數', N'有人受傷嗎？幾個人受傷呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (124, 14, 14, N'載運物', N'車上有易燃物品之類的嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (124, 15, 15, N'滅火狀況', N'現場有人在滅火嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (124, 16, 16, N'車輛行駛狀況', N'車子是行駛中還是停在路邊呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (124, 17, 17, N'車牌號碼', N'車牌號碼看得到嗎？', 3);

-- 125 火警-船舶（02-垂片B1_交通工具）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (125, 1, 1, N'交通工具', N'請問是什麼車燒起來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (125, 2, 2, N'車輛動力(汽車)', N'請問是油車、油電車還是電動車呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (125, 3, 3, N'車輛動力(機車)', N'請問是油車還是電動車呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (125, 4, 4, N'腳踏車車型', N'請問是一般腳踏車、U bike 還是電輔車？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (125, 5, 5, N'火煙狀況', N'現在有看到火嗎？還是只有看到煙？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (125, 6, 6, N'濃煙顏色', N'請問是黑煙還是白煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (125, 7, 7, N'報案身分', N'請問您是車主或駕駛嗎？還是路人呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (125, 8, 8, N'是否延燒', N'火有沒有燒到旁邊的東西？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (125, 9, 9, N'起火部位', N'是車頭還是後車廂燒起來了呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (125, 10, 10, N'起火車輛數量', N'現場有幾台在燒呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (125, 11, 11, N'熄火狀態', N'車子引擎關掉了嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (125, 12, 12, N'人員受困', N'車上的人都出來了嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (125, 13, 13, N'患者人數', N'有人受傷嗎？幾個人受傷呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (125, 14, 14, N'載運物', N'車上有易燃物品之類的嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (125, 15, 15, N'滅火狀況', N'現場有人在滅火嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (125, 16, 16, N'車輛行駛狀況', N'車子是行駛中還是停在路邊呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (125, 17, 17, N'車牌號碼', N'車牌號碼看得到嗎？', 3);

-- 126 火警-航空器（02-垂片B1_交通工具）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (126, 1, 1, N'交通工具', N'請問是什麼車燒起來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (126, 2, 2, N'車輛動力(汽車)', N'請問是油車、油電車還是電動車呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (126, 3, 3, N'車輛動力(機車)', N'請問是油車還是電動車呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (126, 4, 4, N'腳踏車車型', N'請問是一般腳踏車、U bike 還是電輔車？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (126, 5, 5, N'火煙狀況', N'現在有看到火嗎？還是只有看到煙？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (126, 6, 6, N'濃煙顏色', N'請問是黑煙還是白煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (126, 7, 7, N'報案身分', N'請問您是車主或駕駛嗎？還是路人呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (126, 8, 8, N'是否延燒', N'火有沒有燒到旁邊的東西？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (126, 9, 9, N'起火部位', N'是車頭還是後車廂燒起來了呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (126, 10, 10, N'起火車輛數量', N'現場有幾台在燒呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (126, 11, 11, N'熄火狀態', N'車子引擎關掉了嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (126, 12, 12, N'人員受困', N'車上的人都出來了嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (126, 13, 13, N'患者人數', N'有人受傷嗎？幾個人受傷呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (126, 14, 14, N'載運物', N'車上有易燃物品之類的嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (126, 15, 15, N'滅火狀況', N'現場有人在滅火嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (126, 16, 16, N'車輛行駛狀況', N'車子是行駛中還是停在路邊呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (126, 17, 17, N'車牌號碼', N'車牌號碼看得到嗎？', 3);

-- 127 火警-山林田野(平地)（03-垂片B2_山林田野）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (127, 1, 1, N'燃燒物', N'知道是什麼東西在燒嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (127, 2, 2, N'火煙狀況', N'現在有看到火嗎？還是只有看到煙？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (127, 3, 3, N'濃煙顏色', N'請問是黑煙還是白煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (127, 4, 4, N'報案身分', N'請問您是住在附近，還是剛好經過？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (127, 5, 5, N'燃燒面積', N'可以描述一下大概燒多大嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (127, 6, 6, N'是否延燒', N'火有沒有燒到旁邊的東西？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (127, 7, 7, N'山林火警', N'是山上還是路邊空地呢？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (127, 8, 8, N'滅火狀況', N'現場有人在滅火嗎？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (127, 9, 9, N'水源狀況', N'附近有水源嗎？', 3);

-- 128 火警-山林田野(山地)（03-垂片B2_山林田野）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (128, 1, 1, N'燃燒物', N'知道是什麼東西在燒嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (128, 2, 2, N'火煙狀況', N'現在有看到火嗎？還是只有看到煙？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (128, 3, 3, N'濃煙顏色', N'請問是黑煙還是白煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (128, 4, 4, N'報案身分', N'請問您是住在附近，還是剛好經過？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (128, 5, 5, N'燃燒面積', N'可以描述一下大概燒多大嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (128, 6, 6, N'是否延燒', N'火有沒有燒到旁邊的東西？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (128, 7, 7, N'山林火警', N'是山上還是路邊空地呢？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (128, 8, 8, N'滅火狀況', N'現場有人在滅火嗎？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (128, 9, 9, N'水源狀況', N'附近有水源嗎？', 3);

-- 130 火警-垃圾（04-垂片C_輕微火警）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (130, 1, 1, N'火警類型', N'是警報器作響嗎？還是有聞到燒焦味？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (130, 2, 2, N'場所用途', N'請問是住宅還是工廠呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (130, 3, 3, N'建築物類型', N'是公寓還是大樓？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (130, 4, 4, N'建築物類型', N'現場是什麼用途？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (130, 5, 5, N'建物總樓層', N'總共幾層樓？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (130, 6, 6, N'火煙狀況', N'現在有看到火嗎？還是只有看到煙？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (130, 7, 7, N'濃煙顏色', N'請問是黑煙還是白煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (130, 8, 8, N'警報器狀態', N'警報器現在還在響嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (130, 9, 9, N'氣味類型', N'現場有聞到燒焦味嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (130, 10, 10, N'是否延燒', N'火有沒有燒到旁邊的東西？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (130, 11, 11, N'燃燒面積', N'燒起來的範圍大概多大？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (130, 12, 12, N'報案身分', N'請問您是住在附近，還是剛好經過？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (130, 13, 13, N'人員受困', N'有聽到有人在呼救嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (130, 14, 14, N'來源確認', N'知道是哪一戶、哪一層傳出來的嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (130, 15, 15, N'標的物', N'是哪裡在冒煙？電線桿、電表，還是水溝蓋？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (130, 16, 16, N'起火戶應門', N'', 3);

-- 131 火警-電線桿(電纜)（04-垂片C_輕微火警）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (131, 1, 1, N'火警類型', N'是警報器作響嗎？還是有聞到燒焦味？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (131, 2, 2, N'場所用途', N'請問是住宅還是工廠呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (131, 3, 3, N'建築物類型', N'是公寓還是大樓？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (131, 4, 4, N'建築物類型', N'現場是什麼用途？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (131, 5, 5, N'建物總樓層', N'總共幾層樓？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (131, 6, 6, N'火煙狀況', N'現在有看到火嗎？還是只有看到煙？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (131, 7, 7, N'濃煙顏色', N'請問是黑煙還是白煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (131, 8, 8, N'警報器狀態', N'警報器現在還在響嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (131, 9, 9, N'氣味類型', N'現場有聞到燒焦味嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (131, 10, 10, N'是否延燒', N'火有沒有燒到旁邊的東西？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (131, 11, 11, N'燃燒面積', N'燒起來的範圍大概多大？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (131, 12, 12, N'報案身分', N'請問您是住在附近，還是剛好經過？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (131, 13, 13, N'人員受困', N'有聽到有人在呼救嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (131, 14, 14, N'來源確認', N'知道是哪一戶、哪一層傳出來的嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (131, 15, 15, N'標的物', N'是哪裡在冒煙？電線桿、電表，還是水溝蓋？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (131, 16, 16, N'起火戶應門', N'', 3);

-- 133 火警-警報器作響（04-垂片C_輕微火警）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (133, 1, 1, N'火警類型', N'是警報器作響嗎？還是有聞到燒焦味？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (133, 2, 2, N'場所用途', N'請問是住宅還是工廠呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (133, 3, 3, N'建築物類型', N'是公寓還是大樓？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (133, 4, 4, N'建築物類型', N'現場是什麼用途？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (133, 5, 5, N'建物總樓層', N'總共幾層樓？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (133, 6, 6, N'火煙狀況', N'現在有看到火嗎？還是只有看到煙？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (133, 7, 7, N'濃煙顏色', N'請問是黑煙還是白煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (133, 8, 8, N'警報器狀態', N'警報器現在還在響嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (133, 9, 9, N'氣味類型', N'現場有聞到燒焦味嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (133, 10, 10, N'是否延燒', N'火有沒有燒到旁邊的東西？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (133, 11, 11, N'燃燒面積', N'燒起來的範圍大概多大？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (133, 12, 12, N'報案身分', N'請問您是住在附近，還是剛好經過？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (133, 13, 13, N'人員受困', N'有聽到有人在呼救嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (133, 14, 14, N'來源確認', N'知道是哪一戶、哪一層傳出來的嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (133, 15, 15, N'標的物', N'是哪裡在冒煙？電線桿、電表，還是水溝蓋？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (133, 16, 16, N'起火戶應門', N'', 3);

-- 134 火警-查看案件（04-垂片C_輕微火警）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (134, 1, 1, N'火警類型', N'是警報器作響嗎？還是有聞到燒焦味？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (134, 2, 2, N'場所用途', N'請問是住宅還是工廠呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (134, 3, 3, N'建築物類型', N'是公寓還是大樓？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (134, 4, 4, N'建築物類型', N'現場是什麼用途？總共有幾層樓？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (134, 5, 5, N'建物總樓層', N'總共幾層樓？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (134, 6, 6, N'火煙狀況', N'現在有看到火嗎？還是只有看到煙？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (134, 7, 7, N'濃煙顏色', N'請問是黑煙還是白煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (134, 8, 8, N'警報器狀態', N'警報器現在還在響嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (134, 9, 9, N'氣味類型', N'現場有聞到燒焦味嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (134, 10, 10, N'是否延燒', N'火有沒有燒到旁邊的東西？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (134, 11, 11, N'燃燒面積', N'燒起來的範圍大概多大？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (134, 12, 12, N'報案身分', N'請問您是住在附近，還是剛好經過？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (134, 13, 13, N'人員受困', N'有聽到有人在呼救嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (134, 14, 14, N'來源確認', N'知道是哪一戶、哪一層傳出來的嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (134, 15, 15, N'標的物', N'是哪裡在冒煙？電線桿、電表，還是水溝蓋？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (134, 16, 16, N'起火戶應門', N'', 3);

-- 200 救護-未知（00-未知）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (200, 1, 1, N'病徵', N'請問發生什麼事？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (200, 2, 2, N'患者人數', N'現場有幾個人需要救護？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (200, 3, 3, N'意識', N'他現在人清醒嗎？叫他有沒有反應？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (200, 4, 4, N'呼吸', N'他還有沒有呼吸？胸口、肚子有沒有一上一下起伏？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (200, 5, 5, N'年齡', N'他大概幾歲？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (200, 6, 6, N'性別', N'他是男生還是女生？', 1);

-- 201 救護-急病（01-急病）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (201, 1, 1, N'病徵', N'請問患者是哪裡不舒服？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (201, 2, 2, N'患者人數', N'現場有幾個人需要救護？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (201, 3, 3, N'報案身分', N'請問你認識患者嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (201, 4, 4, N'性別', N'請問患者是男生還是女生？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (201, 5, 5, N'年齡', N'請問患者大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (201, 6, 6, N'意識', N'他現在人清醒嗎？叫他有沒有反應？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (201, 7, 7, N'呼吸', N'他還有沒有呼吸？胸部有沒有一上一下起伏呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (201, 8, 8, N'報案人位置', N'', 3);

-- 202 救護-車禍（02-車禍）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (202, 1, 1, N'事故車種', N'請問是什麼車跟什麼車的車禍？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (202, 2, 2, N'患者人數', N'現場有幾個人需要救護？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (202, 3, 3, N'人員受困', N'有沒有人被卡在車子裡面，或是車子底下？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (202, 4, 4, N'受傷部位', N'傷到哪裡？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (202, 5, 5, N'傷勢', N'傷得嚴不嚴重？有沒有一直流血？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (202, 6, 6, N'報案身分', N'請問你認識患者嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (202, 7, 7, N'性別', N'請問患者是男生還是女生？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (202, 8, 8, N'年齡', N'請問患者大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (202, 9, 9, N'意識', N'他現在人清醒嗎？叫他有沒有反應？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (202, 10, 10, N'呼吸', N'他還有沒有呼吸？胸部有沒有一上一下起伏呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (202, 11, 11, N'報案人位置', N'', 3);

-- 203 救護-刀傷(切割傷)（03-刀傷(切割傷)）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (203, 1, 1, N'受傷原因', N'請問是自己不小心割到，還是被別人弄傷的？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (203, 2, 2, N'工具', N'請問是被什麼東西割到？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (203, 3, 3, N'受傷部位', N'傷到哪裡？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (203, 4, 4, N'傷勢', N'傷得嚴不嚴重？有沒有一直流血？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (203, 5, 5, N'報案身分', N'請問你認識患者嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (203, 6, 6, N'性別', N'請問患者是男生還是女生？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (203, 7, 7, N'年齡', N'請問患者大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (203, 8, 8, N'意識', N'他現在人清醒嗎？叫他有沒有反應？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (203, 9, 9, N'呼吸', N'他還有沒有呼吸？胸部有沒有一上一下起伏呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (203, 10, 10, N'患者人數', N'現場有幾個人需要救護？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (203, 11, 11, N'是否飲酒', N'他有喝酒嗎？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (203, 12, 12, N'報案人位置', N'', 3);

-- 204 救護-槍傷（04-槍傷）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (204, 1, 1, N'受傷部位', N'傷到哪裡？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (204, 2, 2, N'傷勢', N'傷得嚴不嚴重？有沒有一直流血？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (204, 3, 3, N'患者人數', N'現場有幾個人需要救護？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (204, 4, 4, N'報案身分', N'請問你認識患者嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (204, 5, 5, N'性別', N'請問患者是男生還是女生？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (204, 6, 6, N'年齡', N'請問患者大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (204, 7, 7, N'意識', N'他現在人清醒嗎？叫他有沒有反應？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (204, 8, 8, N'呼吸', N'他還有沒有呼吸？胸部有沒有一上一下起伏呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (204, 9, 9, N'受傷原因', N'', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (204, 10, 10, N'報案人位置', N'', 3);

-- 205 救護-壓傷（05-壓傷）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (205, 1, 1, N'受傷部位', N'傷到哪裡？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (205, 2, 2, N'傷勢', N'傷得嚴不嚴重？有沒有一直流血？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (205, 3, 3, N'患者人數', N'現場有幾個人需要救護？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (205, 4, 4, N'報案身分', N'請問你認識患者嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (205, 5, 5, N'性別', N'請問患者是男生還是女生？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (205, 6, 6, N'年齡', N'請問患者大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (205, 7, 7, N'意識', N'他現在人清醒嗎？叫他有沒有反應？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (205, 8, 8, N'呼吸', N'他還有沒有呼吸？胸部有沒有一上一下起伏呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (205, 9, 9, N'受傷原因', N'', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (205, 10, 10, N'報案人位置', N'', 3);

-- 206 救護-墜落傷（06-墜落傷）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (206, 1, 1, N'墜落狀況', N'已經跳下來了嗎？還是還在上面？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (206, 2, 2, N'墜落高度', N'請問是從幾樓或多高的地方掉下來？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (206, 3, 3, N'報案身分', N'請問你認識患者嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (206, 4, 4, N'性別', N'請問患者是男生還是女生？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (206, 5, 5, N'年齡', N'請問患者大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (206, 6, 6, N'患者位置', N'目前人掉在哪個地方？地面上還是哪裡？有卡住嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (206, 7, 7, N'卡住位置', N'目前是在遮雨棚上卡住還是女兒牆上？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (206, 8, 8, N'報案人位置', N'你有在傷者旁邊嗎？可以靠近嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (206, 9, 9, N'意識', N'他現在人清醒嗎？叫他有沒有反應？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (206, 10, 10, N'呼吸', N'他還有沒有呼吸？胸部有沒有一上一下起伏呢？', 2);

-- 207 救護-電擊傷（07-電擊傷）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (207, 1, 1, N'電擊種類', N'請問是被什麼電到? 高壓電還是雷電?', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (207, 2, 2, N'現場是否已斷電', N'那邊的電源有沒有先關掉？現在斷電了嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (207, 3, 3, N'患者人數', N'現場有幾個人需要救護？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (207, 4, 4, N'傷患身分', N'患者是工地工人嗎？還是外籍移工呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (207, 5, 5, N'報案身分', N'請問你認識患者嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (207, 6, 6, N'性別', N'請問患者是男生還是女生？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (207, 7, 7, N'年齡', N'請問患者大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (207, 8, 8, N'意識', N'他現在人清醒嗎？叫他有沒有反應？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (207, 9, 9, N'呼吸', N'他還有沒有呼吸？胸部有沒有一上一下起伏呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (207, 10, 10, N'報案人位置', N'', 3);

-- 208 救護-燒燙傷（08-燒燙傷）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (208, 1, 1, N'燒燙傷原因', N'請問是被什麼東西燙到？或什麼原因燙傷？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (208, 2, 2, N'燙傷傷勢', N'有無起水泡，燒燙傷部位？大概範圍多大呢?', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (208, 3, 3, N'報案身分', N'請問你認識患者嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (208, 4, 4, N'性別', N'請問患者是男生還是女生？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (208, 5, 5, N'年齡', N'請問患者大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (208, 6, 6, N'意識', N'現在人清醒嗎？叫他有沒有反應？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (208, 7, 7, N'呼吸', N'還有沒有呼吸？胸部有沒有一上一下起伏呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (208, 8, 8, N'報案人位置', N'', 3);

-- 209 救護-打架受傷（09-打架受傷）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (209, 1, 1, N'衝突狀況', N'現在還有在打嗎？您那邊安全嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (209, 2, 2, N'患者人數', N'現場有幾個人需要救護？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (209, 3, 3, N'是否飲酒', N'他有喝酒嗎？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (209, 4, 4, N'持械', N'請問他們手上有沒有拿刀、棍子之類的東西？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (209, 5, 5, N'報案身分', N'請問你認識患者嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (209, 6, 6, N'性別', N'請問患者是男生還是女生？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (209, 7, 7, N'年齡', N'請問患者大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (209, 8, 8, N'意識', N'他現在人清醒嗎？叫他有沒有反應？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (209, 9, 9, N'呼吸', N'他還有沒有呼吸？胸部有沒有一上一下起伏呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (209, 10, 10, N'病徵', N'', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (209, 11, 11, N'報案人位置', N'', 3);

-- 210 救護-一般受傷（10-一般受傷）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (210, 1, 1, N'受傷原因', N'請問是怎麼受傷的？是跌倒嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (210, 2, 2, N'發生場所', N'是在家裡面受傷的，還是在外面？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (210, 3, 3, N'受傷部位', N'傷到哪裡？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (210, 4, 4, N'傷勢', N'傷得嚴不嚴重？有沒有一直流血？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (210, 5, 5, N'報案身分', N'請問你認識患者嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (210, 6, 6, N'性別', N'請問患者是男生還是女生？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (210, 7, 7, N'年齡', N'請問患者大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (210, 8, 8, N'意識', N'他現在人清醒嗎？叫他有沒有反應？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (210, 9, 9, N'呼吸', N'他還有沒有呼吸？胸部有沒有一上一下起伏呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (210, 10, 10, N'報案人位置', N'', 3);

-- 211 救護-溺水（11-溺水）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (211, 1, 1, N'溺水狀況', N'人拉上岸了嗎? 還是還在水裡?', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (211, 2, 2, N'溺水原因', N'請問是怎麼落水的？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (211, 3, 3, N'患者人數', N'現場有幾個人需要救護？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (211, 4, 4, N'報案身分', N'請問你認識患者嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (211, 5, 5, N'性別', N'請問患者是男生還是女生？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (211, 6, 6, N'年齡', N'請問患者大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (211, 7, 7, N'意識', N'他現在人清醒嗎？叫他有沒有反應？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (211, 8, 8, N'呼吸', N'他還有沒有呼吸？胸部有沒有一上一下起伏呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (211, 9, 9, N'報案人位置', N'', 3);

-- 212 救護-孕婦待產（12-孕婦待產）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (212, 1, 1, N'報案身分', N'請問是孕婦本人，還是家人朋友？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (212, 2, 2, N'陣痛狀況', N'現在有規則陣痛嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (212, 3, 3, N'預產期', N'預產期是什麼時候？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (212, 4, 4, N'懷孕週數', N'現在懷孕幾週了？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (212, 5, 5, N'胎次與胎數', N'這是第幾胎？是單胞胎還是雙胞胎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (212, 6, 6, N'產檢狀況', N'之前產檢都正常嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (212, 7, 7, N'性別', N'他是男生還是女生？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (212, 8, 8, N'年齡', N'請問大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (212, 9, 9, N'意識', N'他現在人清醒嗎？叫他有沒有反應？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (212, 10, 10, N'呼吸', N'他還有沒有呼吸？胸部有沒有一上一下起伏呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (212, 11, 11, N'病徵', N'', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (212, 12, 12, N'報案人位置', N'', 3);

-- 213 救護-精神異常（13-精神異常）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (213, 1, 1, N'攻擊傾向', N'請問目前有攻擊別人或傷害自己的動作嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (213, 2, 2, N'受傷人數', N'現場有沒有其他人受傷？幾個人受傷？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (213, 3, 3, N'強制送醫', N'需要強制送醫嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (213, 4, 4, N'強制送醫原因', N'請問是什麼狀況要強制送醫？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (213, 5, 5, N'報案身分', N'請問你認識患者嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (213, 6, 6, N'性別', N'請問患者是男生還是女生？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (213, 7, 7, N'年齡', N'請問患者大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (213, 8, 8, N'病史', N'請問患者有沒有過去病史？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (213, 9, 9, N'家屬陪同', N'身邊有家屬陪同嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (213, 10, 10, N'意識', N'他現在人清醒嗎？叫他有沒有反應？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (213, 11, 11, N'呼吸', N'他還有沒有呼吸？胸部有沒有一上一下起伏呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (213, 12, 12, N'報案人位置', N'', 3);

-- 214 救護-路倒（14-路倒）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (214, 1, 1, N'路倒狀況', N'他看起來是喝醉、睡著，還是身體不舒服？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (214, 2, 2, N'患者人數', N'現場有幾個人需要救護？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (214, 3, 3, N'是否飲酒', N'他有喝酒嗎？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (214, 4, 4, N'外觀特徵', N'他身上穿什麼顏色的衣服？我請救護人員好認一點。', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (214, 5, 5, N'報案身分', N'請問你認識患者嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (214, 6, 6, N'家屬陪同', N'身邊有家屬陪同嗎？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (214, 7, 7, N'性別', N'請問患者是男生還是女生？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (214, 8, 8, N'年齡', N'請問患者大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (214, 9, 9, N'意識', N'他現在人清醒嗎？叫他有沒有反應？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (214, 10, 10, N'呼吸', N'他還有沒有呼吸？胸部有沒有一上一下起伏呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (214, 11, 11, N'報案人位置', N'', 3);

-- 215 救護-吞食藥物（15-吞食藥物）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (215, 1, 1, N'服用藥物', N'請問是吃了什麼藥物？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (215, 2, 2, N'藥物數量', N'知道大概吃了幾顆嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (215, 3, 3, N'報案身分', N'請問你認識患者嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (215, 4, 4, N'性別', N'請問患者是男生還是女生？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (215, 5, 5, N'年齡', N'請問患者大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (215, 6, 6, N'意識', N'現在人清醒嗎？叫他有沒有反應？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (215, 7, 7, N'呼吸', N'他還有沒有呼吸？胸部有沒有一上一下起伏呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (215, 8, 8, N'病史', N'他本身有沒有什麼慢性病？像高血壓、糖尿病、心臟病這些？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (215, 9, 9, N'報案人位置', N'', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (215, 10, 10, N'藥袋', N'', 3);

-- 216 救護-上吊（16-上吊）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (216, 1, 1, N'上吊狀況', N'目前繩子解開了嗎？人在地上了嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (216, 2, 2, N'破門需求', N'現場救護人員進得去嗎？需要破門嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (216, 3, 3, N'患者位置', N'', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (216, 4, 4, N'報案身分', N'請問你認識患者嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (216, 5, 5, N'性別', N'請問患者是男生還是女生？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (216, 6, 6, N'年齡', N'請問患者大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (216, 7, 7, N'意識', N'現在人清醒嗎？叫他有沒有反應？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (216, 8, 8, N'呼吸', N'他還有沒有呼吸？胸部有沒有一上一下起伏呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (216, 9, 9, N'報案人位置', N'', 3);

-- 217 救護-燒炭（17-燒炭）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (217, 1, 1, N'報案人位置', N'您現在人還在現場嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (217, 2, 2, N'炭盆狀況', N'目前炭盆已熄滅了嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (217, 3, 3, N'現場進入條件', N'救護人員到場之後可以進去嗎？需不需要破門？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (217, 4, 4, N'患者位置', N'患者還在裡面嗎？還是已經出來了？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (217, 5, 5, N'報案身分', N'請問你認識患者嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (217, 6, 6, N'性別', N'請問患者是男生還是女生？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (217, 7, 7, N'年齡', N'請問患者大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (217, 8, 8, N'意識', N'患者現在清醒嗎？叫他有沒有反應？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (217, 9, 9, N'呼吸', N'他還有沒有呼吸？胸部有沒有一上一下起伏呢？', 2);

-- 218 救護-喝農藥（18-喝農藥）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (218, 1, 1, N'農藥種類', N'知道他喝的是什麼農藥嗎？瓶子還在嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (218, 2, 2, N'農藥劑量', N'大概喝了多少？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (218, 3, 3, N'患者人數', N'現場有幾個人需要救護？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (218, 4, 4, N'報案身分', N'請問你認識患者嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (218, 5, 5, N'性別', N'請問患者是男生還是女生？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (218, 6, 6, N'年齡', N'請問患者大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (218, 7, 7, N'意識', N'他現在人清醒嗎？叫他有沒有反應？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (218, 8, 8, N'呼吸', N'他還有沒有呼吸？胸部有沒有一上一下起伏呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (218, 9, 9, N'病徵', N'', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (218, 10, 10, N'報案人位置', N'', 3);

-- 219 救護-割腕（19-割腕）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (219, 1, 1, N'傷勢', N'請問是哪裡受傷？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (219, 2, 2, N'工具', N'是用什麼工具受傷的？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (219, 3, 3, N'工具移除', N'目前刀具還在患者身邊嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (219, 4, 4, N'報案身分', N'請問你認識患者嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (219, 5, 5, N'性別', N'請問患者是男生還是女生？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (219, 6, 6, N'年齡', N'請問患者大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (219, 7, 7, N'意識', N'現在人清醒嗎？叫他有沒有反應？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (219, 8, 8, N'呼吸', N'幫我看他有沒有正常呼吸，胸部有沒有一上一下起伏呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (219, 9, 9, N'報案人位置', N'', 3);

-- 220 救護-吸入廢氣（20-吸入廢氣）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (220, 1, 1, N'病徵', N'請問患者是哪裡不舒服？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (220, 2, 2, N'患者人數', N'現場有幾個人需要救護？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (220, 3, 3, N'報案身分', N'請問你認識患者嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (220, 4, 4, N'性別', N'請問患者是男生還是女生？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (220, 5, 5, N'年齡', N'請問患者大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (220, 6, 6, N'意識', N'他現在人清醒嗎？叫他有沒有反應？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (220, 7, 7, N'呼吸', N'他還有沒有呼吸？胸部有沒有一上一下起伏呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (220, 8, 8, N'報案人位置', N'', 3);

-- 221 救護-其它（21-其它）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (221, 1, 1, N'主訴', N'請問發生什麼事？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (221, 2, 2, N'報案身分', N'請問你認識患者嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (221, 3, 3, N'性別', N'請問患者是男生還是女生？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (221, 4, 4, N'年齡', N'請問患者大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (221, 5, 5, N'意識', N'他現在人清醒嗎？叫他有沒有反應？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (221, 6, 6, N'呼吸', N'他還有沒有呼吸？胸部有沒有一上一下起伏呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (221, 7, 7, N'報案人位置', N'', 3);

-- 301 緊急救援-車禍救助（301-車禍救助）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (301, 1, 1, N'事故車種', N'請問是什麼車跟什麼車的車禍？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (301, 2, 2, N'受傷部位', N'傷到哪裡？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (301, 3, 3, N'傷勢', N'傷得嚴不嚴重？有沒有一直流血？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (301, 4, 4, N'人員受困', N'有沒有人被困在車裡出不來？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (301, 5, 5, N'患者人數', N'有幾個人受傷？幾個人受困？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (301, 6, 6, N'報案身分', N'請問是當事人還是路人代報？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (301, 7, 7, N'意識', N'當事人有清醒嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (301, 8, 8, N'呼吸', N'他還有沒有呼吸？胸部有沒有一上一下起伏呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (301, 9, 9, N'火煙狀況', N'車子有沒有冒煙或起火？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (301, 10, 10, N'交通影響', N'有擋到路嗎？車子還過得去嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (301, 11, 11, N'報案人位置', N'', 3);

-- 303 緊急救援-溺水（303-溺水）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (303, 1, 1, N'溺水原因', N'請問是怎麼落水的？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (303, 2, 2, N'患者人數', N'有幾個人落水？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (303, 3, 3, N'溺水狀況', N'還有看到人嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (303, 4, 4, N'離岸距離', N'離岸邊大概多遠？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (303, 5, 5, N'報案身分', N'請問是家屬朋友還是路人代報呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (303, 6, 6, N'救生裝備', N'對方有穿救生衣或泳圈嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (303, 7, 7, N'性別', N'請問患者是男生還是女生？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (303, 8, 8, N'年齡', N'請問患者大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (303, 9, 9, N'意識', N'對方還會動嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (303, 10, 10, N'呼吸', N'他還有沒有呼吸？胸部有沒有一上一下起伏呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (303, 11, 11, N'外觀特徵', N'他穿什麼顏色的衣服？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (303, 12, 12, N'團體帶隊', N'是自己來，還是跟團體一起？有帶隊的人嗎？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (303, 13, 13, N'報案人位置', N'', 3);

-- 304 緊急救援-跳水（304-跳水）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (304, 1, 1, N'跳水狀況', N'對方已經跳下去了嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (304, 2, 2, N'溺水狀況', N'還看得到患者嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (304, 3, 3, N'報案身分', N'請問是家屬朋友還是路人代報呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (304, 4, 4, N'性別', N'請問患者是男生還是女生？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (304, 5, 5, N'年齡', N'請問患者大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (304, 6, 6, N'外觀特徵', N'他穿什麼顏色的衣服？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (304, 7, 7, N'患者人數', N'有幾個人呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (304, 8, 8, N'意識', N'人還會動嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (304, 9, 9, N'呼吸', N'他還有沒有呼吸？胸部有沒有一上一下起伏呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (304, 10, 10, N'報案人位置', N'', 3);

-- 305 緊急救援-跳樓（305-跳樓）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (305, 1, 1, N'墜落狀況', N'人還在上面嗎？還是跳下來了？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (305, 2, 2, N'輕生意圖', N'他是要自殺嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (305, 3, 3, N'所在樓層', N'現在在幾樓？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (305, 4, 4, N'報案身分', N'請問是家屬朋友還是路人代報呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (305, 5, 5, N'性別', N'請問患者是男生還是女生？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (305, 6, 6, N'年齡', N'請問患者大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (305, 7, 7, N'報案人位置', N'', 3);

-- 308 緊急救援-山難（308-山難）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (308, 1, 1, N'山難原因', N'請問發生什麼事？是迷路還是受傷？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (308, 2, 2, N'受傷部位', N'傷到哪裡？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (308, 3, 3, N'傷勢', N'傷得嚴不嚴重？有沒有一直流血？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (308, 4, 4, N'患者人數', N'你們總共幾個人？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (308, 5, 5, N'位置座標', N'您現在在哪裡？手機可以看到座標嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (308, 6, 6, N'報案身分', N'請問是本人還是家屬朋友代報？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (308, 7, 7, N'性別', N'請問當事人是男生還是女生？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (308, 8, 8, N'年齡', N'請問當事人大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (308, 9, 9, N'意識', N'現在人是清醒的嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (308, 10, 10, N'呼吸', N'他還有沒有呼吸？胸部有沒有一上一下起伏呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (308, 11, 11, N'入山資訊', N'幾點上山的？從哪裡上去的？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (308, 12, 12, N'登山路線', N'你們走哪一條路線？最後經過什麼地標？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (308, 13, 13, N'隨身物資', N'身上的水、食物、保暖衣物夠嗎？有手電筒或哨子嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (308, 14, 14, N'團體帶隊', N'是自己來，還是跟團體一起？有帶隊的人嗎？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (308, 15, 15, N'報案人位置', N'', 3);

-- 309 緊急救援-其他（309-其他(卡住夾住)）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (309, 1, 1, N'卡住部位', N'哪裡卡住了？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (309, 2, 2, N'卡住物品', N'卡在什麼東西裡面？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (309, 3, 3, N'是否脫困', N'現在還卡著嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (309, 4, 4, N'受傷部位', N'傷到哪裡？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (309, 5, 5, N'傷勢', N'傷得嚴不嚴重？有沒有一直流血？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (309, 6, 6, N'發生場所', N'是在家裡還是工作的地方？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (309, 7, 7, N'報案身分', N'請問是當事人還是家屬朋友代報？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (309, 8, 8, N'性別', N'請問當事人是男生還是女生？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (309, 9, 9, N'年齡', N'請問當事人大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (309, 10, 10, N'意識', N'人是清醒的嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (309, 11, 11, N'呼吸', N'他還有沒有呼吸？胸部有沒有一上一下起伏呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (309, 12, 12, N'報案人位置', N'', 3);

-- 310 緊急救援-瓦斯漏氣(建築物)（310-瓦斯漏氣(建築物)）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (310, 1, 1, N'場所用途', N'那裡是住家還是店家呢？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (310, 2, 2, N'報案身分', N'請問您是住在附近，還是路人？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (310, 3, 3, N'火煙狀況', N'有看到明顯的火或煙嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (310, 4, 4, N'聞到位置', N'是在家裡面聞到，還是外面？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (310, 5, 5, N'味道濃淡', N'味道很濃嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (310, 6, 6, N'瓦斯種類', N'是用天然氣，還是瓦斯桶？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (310, 7, 7, N'鄰接建物', N'旁邊有房子或車子嗎？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (310, 8, 8, N'身體不適', N'有人身體不舒服嗎？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (310, 9, 9, N'報案人位置', N'', 3);

-- 312 緊急救援-電梯受困（312-電梯受困）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (312, 1, 1, N'社區棟別', N'是哪個社區？哪一棟、哪一部電梯？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (312, 2, 2, N'受困樓層', N'電梯現在停在幾樓？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (312, 3, 3, N'受困人數', N'裡面有幾個人？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (312, 4, 4, N'報案身分', N'請問是本人嗎？還是管理員或警衛？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (312, 5, 5, N'意識', N'裡面的人都清醒嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (312, 6, 6, N'呼吸', N'他還有沒有呼吸？胸部有沒有一上一下起伏呢？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (312, 7, 7, N'身體不適', N'裡面的人有沒有受傷或不舒服？', 3);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (312, 8, 8, N'電梯公司', N'有聯絡電梯公司了嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (312, 9, 9, N'報案人位置', N'', 3);

-- 313 緊急救援-破門（313-破門）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (313, 1, 1, N'擔心原因', N'發生什麼事需要破門？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (313, 2, 2, N'報案身分', N'請問是當事人還是家屬朋友代報？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (313, 3, 3, N'有無回應', N'敲門或打電話，會有回應嗎？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (313, 4, 4, N'性別', N'請問當事人是男生還是女生？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (313, 5, 5, N'年齡', N'請問當事人大概幾歲？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (313, 6, 6, N'門的種類', N'是大門還是房間的門？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (313, 7, 7, N'鑰匙鎖匠', N'有沒有鑰匙？找過鎖匠嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (313, 8, 8, N'同意破門', N'我們破門會把門弄壞，家屬或屋主同意嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (313, 9, 9, N'報案人位置', N'', 3);

-- 501 災害-積水（01-災害垂片）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (501, 1, 1, N'人員受傷', N'有沒有人受傷？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (501, 2, 2, N'人員受困', N'有沒有人被困住出不來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (501, 3, 3, N'受困人數', N'有幾個人被困住？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (501, 4, 4, N'交通影響', N'有擋到路嗎？車子還過得去嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (501, 5, 5, N'火煙狀況', N'現場有沒有冒火花或冒煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (501, 6, 6, N'報案人位置', N'請問您還在現場嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (501, 7, 7, N'報案身分', N'是路過民眾嗎？', 1);

-- 502 災害-淹水（01-災害垂片）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (502, 1, 1, N'人員受傷', N'有沒有人受傷？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (502, 2, 2, N'人員受困', N'有沒有人被困住出不來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (502, 3, 3, N'受困人數', N'有幾個人被困住？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (502, 4, 4, N'交通影響', N'有擋到路嗎？車子還過得去嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (502, 5, 5, N'火煙狀況', N'現場有沒有冒火花或冒煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (502, 6, 6, N'報案人位置', N'請問您還在現場嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (502, 7, 7, N'報案身分', N'是路過民眾嗎？', 1);

-- 508 災害-土石流及大規模崩塌災害（01-災害垂片）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (508, 1, 1, N'人員受傷', N'有沒有人受傷？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (508, 2, 2, N'人員受困', N'有沒有人被困住出不來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (508, 3, 3, N'受困人數', N'有幾個人被困住？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (508, 4, 4, N'交通影響', N'有擋到路嗎？車子還過得去嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (508, 5, 5, N'火煙狀況', N'現場有沒有冒火花或冒煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (508, 6, 6, N'報案人位置', N'請問您還在現場嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (508, 7, 7, N'報案身分', N'是路過民眾嗎？', 1);

-- 509 災害-招牌掉落（01-災害垂片）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (509, 1, 1, N'人員受傷', N'有沒有人受傷？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (509, 2, 2, N'人員受困', N'有沒有人被困住出不來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (509, 3, 3, N'受困人數', N'有幾個人被困住？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (509, 4, 4, N'交通影響', N'有擋到路嗎？車子還過得去嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (509, 5, 5, N'火煙狀況', N'現場有沒有冒火花或冒煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (509, 6, 6, N'報案人位置', N'請問您還在現場嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (509, 7, 7, N'報案身分', N'是路過民眾嗎？', 1);

-- 510 災害-路樹傾倒（01-災害垂片）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (510, 1, 1, N'人員受傷', N'有沒有人受傷？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (510, 2, 2, N'人員受困', N'有沒有人被困住出不來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (510, 3, 3, N'受困人數', N'有幾個人被困住？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (510, 4, 4, N'交通影響', N'有擋到路嗎？車子還過得去嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (510, 5, 5, N'火煙狀況', N'現場有沒有冒火花或冒煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (510, 6, 6, N'報案人位置', N'請問您還在現場嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (510, 7, 7, N'報案身分', N'是路過民眾嗎？', 1);

-- 511 災害-電線掉落（01-災害垂片）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (511, 1, 1, N'人員受傷', N'有沒有人受傷？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (511, 2, 2, N'人員受困', N'有沒有人被困住出不來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (511, 3, 3, N'受困人數', N'有幾個人被困住？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (511, 4, 4, N'交通影響', N'有擋到路嗎？車子還過得去嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (511, 5, 5, N'火煙狀況', N'現場有沒有冒火花或冒煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (511, 6, 6, N'報案人位置', N'請問您還在現場嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (511, 7, 7, N'報案身分', N'是路過民眾嗎？', 1);

-- 512 災害-道路中斷（01-災害垂片）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (512, 1, 1, N'人員受傷', N'有沒有人受傷？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (512, 2, 2, N'人員受困', N'有沒有人被困住出不來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (512, 3, 3, N'受困人數', N'有幾個人被困住？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (512, 4, 4, N'交通影響', N'有擋到路嗎？車子還過得去嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (512, 5, 5, N'火煙狀況', N'現場有沒有冒火花或冒煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (512, 6, 6, N'報案人位置', N'請問您還在現場嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (512, 7, 7, N'報案身分', N'是路過民眾嗎？', 1);

-- 515 災害-電力停電（01-災害垂片）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (515, 1, 1, N'人員受傷', N'有沒有人受傷？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (515, 2, 2, N'人員受困', N'有沒有人被困住出不來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (515, 3, 3, N'受困人數', N'有幾個人被困住？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (515, 4, 4, N'交通影響', N'有擋到路嗎？車子還過得去嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (515, 5, 5, N'火煙狀況', N'現場有沒有冒火花或冒煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (515, 6, 6, N'報案人位置', N'請問您還在現場嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (515, 7, 7, N'報案身分', N'是路過民眾嗎？', 1);

-- 526 災害-人員疏散及災民收容（01-災害垂片）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (526, 1, 1, N'人員受傷', N'有沒有人受傷？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (526, 2, 2, N'人員受困', N'有沒有人被困住出不來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (526, 3, 3, N'受困人數', N'有幾個人被困住？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (526, 4, 4, N'交通影響', N'有擋到路嗎？車子還過得去嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (526, 5, 5, N'火煙狀況', N'現場有沒有冒火花或冒煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (526, 6, 6, N'報案人位置', N'請問您還在現場嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (526, 7, 7, N'報案身分', N'是路過民眾嗎？', 1);

-- 527 災害-道路受損（01-災害垂片）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (527, 1, 1, N'人員受傷', N'有沒有人受傷？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (527, 2, 2, N'人員受困', N'有沒有人被困住出不來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (527, 3, 3, N'受困人數', N'有幾個人被困住？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (527, 4, 4, N'交通影響', N'有擋到路嗎？車子還過得去嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (527, 5, 5, N'火煙狀況', N'現場有沒有冒火花或冒煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (527, 6, 6, N'報案人位置', N'請問您還在現場嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (527, 7, 7, N'報案身分', N'是路過民眾嗎？', 1);

-- 529 災害-道路坍方落石（01-災害垂片）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (529, 1, 1, N'人員受傷', N'有沒有人受傷？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (529, 2, 2, N'人員受困', N'有沒有人被困住出不來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (529, 3, 3, N'受困人數', N'有幾個人被困住？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (529, 4, 4, N'交通影響', N'有擋到路嗎？車子還過得去嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (529, 5, 5, N'火煙狀況', N'現場有沒有冒火花或冒煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (529, 6, 6, N'報案人位置', N'請問您還在現場嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (529, 7, 7, N'報案身分', N'是路過民眾嗎？', 1);

-- 530 災害-鐵皮掉落（01-災害垂片）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (530, 1, 1, N'人員受傷', N'有沒有人受傷？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (530, 2, 2, N'人員受困', N'有沒有人被困住出不來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (530, 3, 3, N'受困人數', N'有幾個人被困住？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (530, 4, 4, N'交通影響', N'有擋到路嗎？車子還過得去嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (530, 5, 5, N'火煙狀況', N'現場有沒有冒火花或冒煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (530, 6, 6, N'報案人位置', N'請問您還在現場嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (530, 7, 7, N'報案身分', N'是路過民眾嗎？', 1);

-- 531 災害-房屋全倒（01-災害垂片）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (531, 1, 1, N'人員受傷', N'有沒有人受傷？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (531, 2, 2, N'人員受困', N'有沒有人被困住出不來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (531, 3, 3, N'受困人數', N'有幾個人被困住？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (531, 4, 4, N'交通影響', N'有擋到路嗎？車子還過得去嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (531, 5, 5, N'火煙狀況', N'現場有沒有冒火花或冒煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (531, 6, 6, N'報案人位置', N'請問您還在現場嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (531, 7, 7, N'報案身分', N'是路過民眾嗎？', 1);

-- 532 災害-電線桿傾倒（01-災害垂片）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (532, 1, 1, N'人員受傷', N'有沒有人受傷？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (532, 2, 2, N'人員受困', N'有沒有人被困住出不來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (532, 3, 3, N'受困人數', N'有幾個人被困住？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (532, 4, 4, N'交通影響', N'有擋到路嗎？車子還過得去嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (532, 5, 5, N'火煙狀況', N'現場有沒有冒火花或冒煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (532, 6, 6, N'報案人位置', N'請問您還在現場嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (532, 7, 7, N'報案身分', N'是路過民眾嗎？', 1);

-- 535 災害-交通號誌損壞（01-災害垂片）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (535, 1, 1, N'人員受傷', N'有沒有人受傷？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (535, 2, 2, N'人員受困', N'有沒有人被困住出不來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (535, 3, 3, N'受困人數', N'有幾個人被困住？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (535, 4, 4, N'交通影響', N'有擋到路嗎？車子還過得去嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (535, 5, 5, N'火煙狀況', N'現場有沒有冒火花或冒煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (535, 6, 6, N'報案人位置', N'請問您還在現場嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (535, 7, 7, N'報案身分', N'是路過民眾嗎？', 1);

-- 538 災害-自來水管線破裂（01-災害垂片）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (538, 1, 1, N'人員受傷', N'有沒有人受傷？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (538, 2, 2, N'人員受困', N'有沒有人被困住出不來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (538, 3, 3, N'受困人數', N'有幾個人被困住？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (538, 4, 4, N'交通影響', N'有擋到路嗎？車子還過得去嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (538, 5, 5, N'火煙狀況', N'現場有沒有冒火花或冒煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (538, 6, 6, N'報案人位置', N'請問您還在現場嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (538, 7, 7, N'報案身分', N'是路過民眾嗎？', 1);

-- 539 災害-山坡地社區災害（01-災害垂片）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (539, 1, 1, N'人員受傷', N'有沒有人受傷？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (539, 2, 2, N'人員受困', N'有沒有人被困住出不來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (539, 3, 3, N'受困人數', N'有幾個人被困住？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (539, 4, 4, N'交通影響', N'有擋到路嗎？車子還過得去嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (539, 5, 5, N'火煙狀況', N'現場有沒有冒火花或冒煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (539, 6, 6, N'報案人位置', N'請問您還在現場嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (539, 7, 7, N'報案身分', N'是路過民眾嗎？', 1);

-- 540 災害-其他（01-災害垂片）
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (540, 1, 1, N'人員受傷', N'有沒有人受傷？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (540, 2, 2, N'人員受困', N'有沒有人被困住出不來？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (540, 3, 3, N'受困人數', N'有幾個人被困住？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (540, 4, 4, N'交通影響', N'有擋到路嗎？車子還過得去嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (540, 5, 5, N'火煙狀況', N'現場有沒有冒火花或冒煙？', 2);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (540, 6, 6, N'報案人位置', N'請問您還在現場嗎？', 1);
INSERT INTO CaseTypeQA (CaseTypeId, SeqNo, QuestionId, Question, Answer, Type) VALUES (540, 7, 7, N'報案身分', N'是路過民眾嗎？', 1);
