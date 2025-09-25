## 快速開始（本機 - PowerShell）

這個專案是一個 LINE Bot 範例，示範如何把使用者的文字描述與上傳的圖片送到 Google Generative AI (Gemini) 做穿搭分析，並回覆結果。以下為快速開始步驟（把使用說明放在最前面，方便開發與部署）：

1. 建立並啟用虛擬環境：
1. 專案的使用方式

快速開始

- 建議環境：Python 3.11+，Windows / Linux / macOS。
- 建議建立虛擬環境並安裝套件：
   - 在 PowerShell 中：
      - python -m venv .venv; .\\.venv\\Scripts\\Activate.ps1; pip install -r requirements.txt
- 環境變數（範例）：
   - LINE_CHANNEL_SECRET - LINE channel secret
   - LINE_CHANNEL_ACCESS_TOKEN - LINE channel access token
   - GEMINI_API_KEY - Google Gemini/Generative API key
   - SENTRY_DSN (可選) - Sentry DSN
   - REDIS_URL (當使用 RedisState 時)
- 開發環境啟動（本機）
   - 使用 Flask 直接啟動：
      - set FLASK_APP=app.py; flask run --host=0.0.0.0 --port=8080
   - 使用 gunicorn（Linux / WSL）：
      - gunicorn -c gunicorn.conf.py app:app
- 部署
   - 已包含 Dockerfile / docker-compose.yml，可用於容器化部署

運作流程簡述

- 此專案為一個 LINE webhook 的 Flask 應用。
- 收到來自 LINE 的事件（message / image / postback），進入 `handlers.py` 的處理流程，維持簡單的狀態機並呼叫 Gemini 生成回覆。


2. 專案的結構 (包括資料流的走向)

主要檔案與目的

- app.py：Flask 應用入口，設定 Sentry、路由（/healthz 與 /webhook），選擇 state backend（Memory / Redis）。
- handlers.py：LINE 事件處理器，包含狀態機（Q1/Q2/Q3/WAIT_IMAGE）、事件去重（idempotency）、Prompt Injection 檢測與回應邏輯。
- gemini_client.py：封裝對 Google Generative API（Gemini）的呼叫，含 timeout、重試與錯誤處理。
- prompts.py：定義系統層與任務層的 prompt 模板（SYSTEM_RULES, TASK_INSTRUCTION, USER_CONTEXT_TEMPLATE）。
- security/pi_guard.py：Prompt Injection（PI）檢測與文字淨化工具。
- security/messages.py：定義預設的安全拒絕回覆（SAFE_REFUSAL）等訊息。
- state.py：抽象化的狀態儲存（MemoryState 與 RedisState），用以存放對話狀態與事件去重快取。
- utils.py / compat.py / sentry_init.py / handlers.py：輔助功能、兼容層與 Sentry 初始化。
- tests/：pytest 測試，包含對 handlers、gemini_client、pi_guard 等關鍵路徑的單元測試與整合測試。

資料流

1. LINE webhook 傳入 POST /webhook。
2. `app.py` 驗證簽章並將事件傳給 `handlers.py`。
3. `handlers.py` 檢查事件是否已處理（去重）；載入或初始化使用者狀態（Memory 或 Redis）。
4. 根據狀態機決定下一步：要求文字輸入、要求上傳圖片、或等待 Gemini 回應。若需呼叫 Gemini，先透過 `security/pi_guard.py` 做 prompt injection 偵測與淨化，並把系統/任務/user 三層 prompt 組合後傳給 `gemini_client.py`。
5. `gemini_client.py` 呼叫 Google Generative API，取得回覆；若 API 回傳錯誤或超時，會有重試策略並記錄 Sentry。
6. `handlers.py` 根據回覆更新狀態並回覆使用者（LINE 回覆或推播）。


3. 專案目的

- 提供一個可測試、可部署的 LINE webhook 範例，展示如何：
   - 與 Google 的 Gemini（Generative API）整合。
   - 在 webhook 處理流程中實作狀態機與 idempotency（事件去重）。
   - 加入 Prompt Injection 偵測與防護，示範在呼叫 LLM 前做防禦的正確位置與方式。
   - 用 Sentry 做監控與錯誤追蹤。
   - 支援 Memory 與 Redis 兩種狀態後端，便於開發與生產環境。

設計原則

- 減少副作用：只有在確定 API 呼叫與狀態更新需要時才變更外部狀態。
# 穿搭評分 LINE Bot（Gemini 驅動）

一個以 Flask + LINE webhook 為基礎的示範專案，展示如何把使用者文字描述與上傳圖片送到 Google Generative AI（Gemini）進行穿搭評分。專案強調安全（Prompt Injection 偵測）、可測試性、Sentry 錯誤追蹤與可切換的狀態儲存（Memory / Redis）。

## 1. 專案概述

此專案示範完整的 LINE Bot 後端：接收事件（文字、圖片、Postback）、維護簡單狀態機（Q1/Q2/Q3 -> WAIT_IMAGE）、在呼叫 LLM 前執行 Prompt Injection 偵測與淨化，並使用 Gemini 的文字/影像能力產生結構化結果後回覆使用者。適合作為學習與參考範例，也能延伸為商用系統的基礎。

## 2. 主要功能

- 三題引導（地點/目的/時間）以 Postback/Quick Reply 驅動，最後請使用者上傳圖片進行評分。
- 圖片驗證：檔案格式（JPG/PNG）與大小限制（預設 10MB，可透過環境變數調整）。
- Prompt Injection（PI）防護：在把使用者內容加入 prompt 前執行偵測與淨化，必要時直接回覆安全拒絕訊息（`SAFE_REFUSAL`）。
- Sentry 整合：錯誤與高風險事件會上報 Sentry，並加上匿名化使用者標記與關鍵 tag/extra。
- State 抽象：支援 MemoryState（本機）與 RedisState（生產），方便測試與水平擴充。
- Gemini client：封裝呼叫到 Google Generative API（包含 timeout、重試與錯誤處理）。
- Flex Message：分析結果會嘗試以 Flex 格式回覆，若失敗則退回純文字分段回覆。

## 3. 快速啟動 & 環境變數

建議使用 Python 3.11+。

在 PowerShell（Windows）中快速啟動：

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt
# 開發模式
set FLASK_APP=app.py; flask run --host=0.0.0.0 --port=8080
```

主要環境變數（範例）：

- `LINE_CHANNEL_SECRET` - LINE channel secret
- `LINE_CHANNEL_ACCESS_TOKEN` - LINE channel access token
- `GEMINI_API_KEY` - Google Gemini API key
- `SENTRY_DSN` - Sentry DSN（可選）
- `REDIS_URL` - 若要使用 RedisState
- `MAX_IMAGE_MB` - 圖片最大允許 MB（預設 10）

容器化：專案包含 `Dockerfile` 與 `docker-compose.yml`，可在生產環境中使用。

## 4. 使用流程與範例

1. 使用者加入或輸入「開始評分」後，Bot 啟動三題引導：
   - Q1：請描述地點/場景（例如：上班、聚會、海邊）
   - Q2：請描述穿搭目的（例如：正式、休閒）
   - Q3：請描述時間/天氣（例如：夏天、傍晚）
2. 完成三題後，使用者上傳 JPG/PNG 圖片。
3. 後端會驗證圖片，組成 prompt（包含系統規則、任務指示與 user context），呼叫 Gemini 的影像/文字分析 API，期望回傳結構化 JSON（summary、subscores、suggestions 等）。
4. 若模型回傳結構化結果，Bot 會嘗試以 Flex Message 回覆；若無法解析，則以分段純文字回覆並 push 額外訊息給使用者。

快速測試（本地）：

```powershell
# 1. 啟動 flask
set FLASK_APP=app.py; flask run --host=0.0.0.0 --port=8080
# 2. 使用 ngrok 或其他反向代理將 /callback 暴露給 LINE
# 3. 在 LINE 官方後台設定 webhook URL 並啟用
```

## Routes（路由）

本專案在 `app.py` 中暴露下列主要 HTTP 路徑，請依說明設定與驗證：

- `GET /healthz`
  - 說明：健康檢查（health check），用於確認應用是否正在運行以及基本依賴是否可用。
  - 方法：GET
  - 回應：HTTP 200 與 body `ok`。
  - 使用情境：可用於平台的 readiness/liveness probe 或手動檢查。

- `POST /callback`（LINE webhook endpoint）
  - 說明：LINE Platform 的 webhook 請求會送到此路徑。程式會驗證 `X-Line-Signature` 標頭，然後把事件交給 `handlers.py` 處理（文字、圖片、postback、follow 等）。
  - 方法：POST
  - 必要 Header：`X-Line-Signature`（用於驗證 payload 的完整性，需與 `LINE_CHANNEL_SECRET` 對應）。
  - Body：LINE 傳送的 JSON 事件陣列（events）。若簽章驗證失敗，伺服器會回 400。
  - 在 LINE Developers Console 的 Messaging API 中，請將 Webhook URL 設為：
    - `https://<your-domain>/callback`（若你修改程式路由，請相對應調整）。

注意：文件歷史版本可能提到 `/webhook`，但目前程式預設為 `/callback`（參見 `app.py` 的 `@app.route('/callback', methods=['POST'])`）。如果你想保留 `/webhook` 作為路徑，可修改 `app.py` 中的 route 並重新部署。

排錯小貼士：
- 若 LINE Console 的 Verify 失敗，請檢查：Render domain、路徑（應為 `/callback`）、是否使用 HTTPS、以及 Render 上的 `LINE_CHANNEL_SECRET` 是否與 LINE Console 的 Channel secret 一致。
- 若收到 400/401/403，通常表示簽章或權杖（access token）錯誤；檢查 `LINE_CHANNEL_ACCESS_TOKEN` 與 `LINE_CHANNEL_SECRET` 是否在環境變數內正確設定。

## 5. Prompt Injection 與安全策略

- 在任何把 user 輸入加入到 system/task 層前，先呼叫 `security.pi_guard.scan_prompt_injection` 並使用 `sanitize_user_text` 做必要淨化。
- 根據偵測結果採取三種處置：淨化、標記監控（Sentry tag），或直接拒絕（回覆 `SAFE_REFUSAL`）。
- System prompt 強制模型輸出符合 JSON schema（若需要結構化輸出），並限制回覆長度與格式。
- 所有錯誤或高風險事件都會上報 Sentry，並帶入匿名使用者 id（hash）與相關上下文。

## 6. 開發、測試與貢獻

- 測試：使用 pytest，專案已包含多個 unit / integration tests。執行所有測試：

```powershell
pytest -q
```

- 風格與相依性：請依 `requirements.txt` 安裝相依套件。
- 貢獻：歡迎提交 PR 或 issue；若要擴充 PI 規則、調整 prompt 或更換 LLM，請同時新增對應測試與說明。

---

如果你希望，我可以為 README 建立一個簡短的變更記錄（CHANGELOG）或把路由說明另存為獨立的 `ROUTES.md`。
