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
- 最小權限原則：Prompt 以系統/任務/user 三層分離，避免把信任邏輯放在使用者輸入中。
- 安全先行：在送出給 LLM 前對 user-provided content 做 PI 檢查並在必要時拒絕或淨化。


4. prompt 說明

Prompt 三層

- System (SYSTEM_RULES)：定義 agent 的身份、不可逾越的限制（安全、隱私、拒絕違規要求的標準措辭）以及回覆格式指引（例如要回 JSON 或特定欄位）。
- Task (TASK_INSTRUCTION)：具體任務說明，例如「你是一個協助使用者上傳圖片並標記標籤的助理，必須回覆簡短句子與狀態代碼」。
- User Context (USER_CONTEXT_TEMPLATE)：把使用者當前狀態、先前對話摘要、上傳圖像的 metadata 放在此層，並限制長度與格式。

範例結構（概念）

- 最終送到 Gemini 的 prompt 會以 JSON 或 dict 模式封裝：
   - system: <SYSTEM_RULES>
   - task: <TASK_INSTRUCTION>
   - user: <USER_CONTEXT>

- 實作細節：
   - `prompts.py` 中儲存 TEXT 模板與格式化 helper。
   - 在 `handlers.py` 中，先把使用者文字送到 `security/pi_guard.scan_prompt_injection`。若回傳有高風險，會記錄 Sentry 並以 `SAFE_REFUSAL` 回覆使用者而不呼叫 Gemini。

回覆與解析

- 若預期 Gemini 回傳結構化資料，會在 system/task 中強制要求 JSON 格式。
- `gemini_client.py` 會嘗試解析回傳，若無法解析則觸發錯誤處理流程（重試或退回簡化 prompt）。


5. prompt injection（PI）說明

偵測與防護策略

- 位置：在將文字加入 prompt 的 user 層前執行（handlers -> pi_guard -> gemini_client），以避免可惡內容進入 system 或 task 層。
- 方法：
   - 快速規則檢查（黑白名單/關鍵字/可疑結構）。
   - 簡單語意檢查（例如內含 "ignore previous instructions", "do X instead" 的句式）以判斷是否為 prompt injection。
   - 必要時執行淨化（sanitize）與長度限制（truncate），或直接返回 `SAFE_REFUSAL`。
- 風險分級：
   - 低風險：只能做輕微淨化／截斷。
   - 中風險：淨化 + Sentry 標記 + 仍可嘗試呼叫 Gemini（視情況）。
   - 高風險：拒絕呼叫 LLM，立即回覆 `SAFE_REFUSAL` 並登記事件。

實務細節

- 程式碼位置：`security/pi_guard.py` 提供 `scan_prompt_injection(text) -> {score, verdict, reasons}` 與 `sanitize_user_text(text) -> str`。
- 監控：遇到中/高風險事件會用 Sentry 加上標籤（event_id, user_id, verdict）以便追蹤與回溯。
- 測試：tests 中已包含對幾種注入字串的單元測試，確保偵測器行為穩定。


6. 其他專案內需要知道的事情

快速檢查點

- healthz：有一個 /healthz endpoint（在 `app.py`），用來確認服務存活與基本依賴（例如 Redis）是否可用。
- Idempotency：事件去重（使用 event_id 快取）以防止 LINE 或網路重試導致重複處理。
- 錯誤追蹤：Sentry 已整合，會在例外與高風險事件發生時上報更多 context。
- 測試：使用 pytest，tests/ 內包含主要流程與邊界案例。請以 `pytest -q` 執行所有測試。
- 開發提示：在本機使用 MemoryState 測試，部署生產請切換 RedisState 並提供 REDIS_URL。

聯絡與延伸

- 若要新增 prompt 規則或調整 PI 偵測閾值，編輯 `prompts.py` 與 `security/pi_guard.py`，並更新 tests 以覆蓋新範例。

- 若要將 Gemini 換成其他 LLM，實作另一個 client（類似 `gemini_client.py` 的 interface）並在 handler 中替換呼叫點。


完成狀態：本 README 旨在直觀呈現使用方式、結構、目的、prompt 與安全設計要點，方便開發者快速上手與審查。
