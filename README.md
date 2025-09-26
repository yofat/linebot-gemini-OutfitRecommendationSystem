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

此專案為一個以 Flask + LINE webhook 為基礎的示範後端，展示如何把使用者文字描述與上傳圖片送到 Google Generative AI（Gemini）做穿搭評分，並以 Flex 或文字回覆。

本次 README 已補充圖片（多模態）在 Free-tier 下的使用說明、停用開關（DISABLE_IMAGE_ANALYZE）、以及 debug endpoints 與本地/Render 測試步驟。

重點摘要
- Python 3.11+
- 建議新增套件：`Pillow`（圖片壓縮），`google-generativeai`（Gemini SDK）

## 快速開始（本機 - PowerShell）

1. 建立虛擬環境並安裝依賴：

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt
```

2. 啟動開發伺服器：

```powershell
set FLASK_APP=app.py; flask run --host=0.0.0.0 --port=8080
```

主要環境變數（範例）

- `LINE_CHANNEL_SECRET`
- `LINE_CHANNEL_ACCESS_TOKEN`
- `GENAI_API_KEY` 或 `GEMINI_API_KEY`（本專案使用 `GENAI_API_KEY`）
- `SENTRY_DSN`（可選）
- `REDIS_URL`（若使用 RedisState）
- `MAX_IMAGE_MB`（default 10）
- `IMAGE_MAX_DIM_PX`（default 1024）
- `IMAGE_JPEG_QUALITY`（default 85）
- `PER_USER_IMAGE_COOLDOWN_SEC`（default 15）
- `DISABLE_IMAGE_ANALYZE`（1/true/yes → 關閉圖片分析，改走文字流程）

建議將 `Pillow` 加入 `requirements.txt`，以啟用圖片壓縮功能，節省上傳大小與 API 額度。

## 圖片（多模態）策略（Free-first）

此專案採用「免費優先」設計：在能使用 Gemini 的多模態（GenerativeModel）API 時會直接發送壓縮後的 JPEG 圖片與上下文 prompt；若環境不支援或模型回應錯誤/超時，會自動降級至文字分析流程，並以友善訊息引導使用者改以文字描述。

要點：
- 圖片驗證：僅接受 JPG/PNG，且大小 ≤ `MAX_IMAGE_MB`。由 `utils.validate_image` 檢查。
- 壓縮：上傳後會先用 `utils.compress_image_to_jpeg`（Pillow）將圖片長邊縮到 `IMAGE_MAX_DIM_PX` 並轉為 JPEG（quality 由 `IMAGE_JPEG_QUALITY` 控制）。
- 節流：每位使用者預設 `PER_USER_IMAGE_COOLDOWN_SEC` 秒內只允許一次圖片分析以減少額度消耗。
- 臨時關閉：若你需要臨時停止圖片分析以避免額度或 SDK 問題，可在部署環境設 `DISABLE_IMAGE_ANALYZE=1`，Bot 會直接回覆文字導引。

## Debug endpoints

開發/部署時可用以下 endpoint 快速檢查狀態：
- `GET /healthz` → 回傳 `ok`（200）
- `GET /_debug/handler_status` → 告訴你 handler 與 line_bot_api 是否已初始化
- `GET /_debug/env_presence` → 檢查重要 env 變數是否存在（不回傳值）
- `GET /_debug/genai_caps` → 檢查部署環境中 `google.generativeai` 模組與 API 能力（會回傳 `has_GenerativeModel`, `has_ImageGeneration`, `version` 等）。

若 `/_debug/genai_caps` 顯示 `has_GenerativeModel: true`，代表你可使用 `GenerativeModel.generate_content(...)` 做多模態呼叫（本專案使用該路徑）。

## 本機測試圖片分析（快速）

在本機上直接測試 `analyze_outfit_image`（不經 LINE webhook）：

1. 安裝 Pillow：

```powershell
pip install Pillow
```

2. 建立一個測試腳本 `scripts/test_analyze_image.py`（或直接用 python -c）：

```python
# scripts/test_analyze_image.py
import os, json, argparse
from gemini_client import analyze_outfit_image

parser = argparse.ArgumentParser()
parser.add_argument('--image', '-i', required=True)
args = parser.parse_args()

os.environ.setdefault('GENAI_API_KEY', os.environ.get('GENAI_API_KEY',''))

with open(args.image, 'rb') as f:
   b = f.read()

try:
   parsed = analyze_outfit_image('上班','正式','白天/晴', b, mime='image/jpeg', timeout=20)
   print(json.dumps(parsed, ensure_ascii=False, indent=2))
except Exception as e:
   print('ERROR', type(e).__name__, str(e))
```

3. 執行（PowerShell）：

```powershell

python .\scripts\test_analyze_image.py --image .\tests\fixtures\sample.jpg
```

如果回傳有效 JSON（包含 `overall_score` 與 `subscores` 等欄位），代表 multi-modal pipeline 在你本機可用；若發生 429 / Timeout / Schema error，程式會在 handler 端自動降級為文字流程。

## 在 Render 上部署與檢查（要點）

1. Push 你的程式到 GitHub（或你使用的來源），Render 會自動建置。
2. 在 Render Dashboard 的 Service 設定中，設定必要的環境變數（`LINE_CHANNEL_*`, `GENAI_API_KEY`, `SENTRY_DSN`）。
3. 若想臨時停用圖片分析：在 Render 的 Environment Variables 新增 `DISABLE_IMAGE_ANALYZE=1` 並重新部署；若想啟用或回到圖片分析，設成 `0` 或移除該變數並重新部署。
4. 呼叫 `https://<your-service>/_debug/genai_caps`，確認 `has_GenerativeModel` 為 `true`（若為 false，請參照下方套件升級步驟）。

升級 `google-generativeai`（如果 _debug 顯示需要）：

- 建議在 `requirements.txt` 指定較新的版本或在 Dockerfile 中更新安裝。例如把 `google-generativeai==0.3.0` 改為 `google-generativeai>=0.4.0`（請依 upstream 版本實際情況調整），然後 push 使 Render 重新 build。

若你必須臨時在部署環境執行升級（不建議常態採取）：

```powershell
# 在 Render 的 shell (若有) 執行
pip install --upgrade google-generativeai
```

## .env.example（建議）

```env
LINE_CHANNEL_SECRET=
LINE_CHANNEL_ACCESS_TOKEN=
GENAI_API_KEY=
SENTRY_DSN=
REDIS_URL=
MAX_IMAGE_MB=10
IMAGE_MAX_DIM_PX=1024
IMAGE_JPEG_QUALITY=85
PER_USER_IMAGE_COOLDOWN_SEC=15
DISABLE_IMAGE_ANALYZE=0
```

## 測試清單（UAT）

- 上傳 **JPG/PNG < MAX_IMAGE_MB** → 預期得到 JSON 與 Flex 回覆（或文字 fallback）
- 在冷卻時間內重複上傳 → 第二次被節流提示
- 上傳 HEIC/WEBP/超大檔 → 立即回錯誤提示
- 模擬 429/Timeout（或改變 SDK 版本導致錯誤）→ 自動降級到文字引導
- 設 `DISABLE_IMAGE_ANALYZE=1` → 圖片路徑關閉，改走文字導引

## 開發、測試與貢獻

- 測試：

```powershell
pytest -q
```

- 若要新增圖片相關測試，建議新增以下檔案：
  - `tests/test_image_validate.py`
  - `tests/test_image_compress.py`
  - `tests/test_rate_limit.py`
  - `tests/test_image_to_text_fallback.py`

---

## Academic statement / 学術利用について / 使用說明與隱私權

本アプリは大学の卒業プロジェクトです。LINE ボットとして、ユーザーのコーディネートを
AI で採点・要約し、提案アイテムを楽天市場 API（IchibaItem/Search/20220601）で検索して
リンクを表示します。非商用・学術目的で利用し、1 RPS 以内のレート制御とキャッシュを行います。
個人情報は保存しません。

這是一個大學專題的 LINE 機器人。AI 會依使用者提供的情境與穿搭資訊產生評分與建議，
接著呼叫日本樂天市場 Ichiba Item Search API（20220601）搜尋相關單品並提供連結。
僅作學術/非商用用途，實作有節流（≤1 RPS）與快取，不儲存個資。

### 隱私權與使用說明

本服務為大學專題用途之 LINE 機器人，提供穿搭評分與建議，並使用
Rakuten Ichiba Item Search API 顯示可能適合的單品連結。

- 非商業用途、僅供學術展示。
- 不蒐集或永久保存個人可識別資訊。訊息僅用於即時回覆。
- 呼叫第三方 API（Rakuten Ichiba Item Search 20220601）時遵守其使用條款與速率限制（≤ 1 req/sec）。
- 商品資訊以對方頁面為準；本服務不保證價格或存貨。
- 聯絡方式：yofatyozi@gmail.com
## 限額 (Quota) 與常見問題處理

如果你在生產環境遇到 `429 quota_exceeded`，或在 probe 時看到 `available: false` 並包含 `retry_delay`：表示目前專案在該 model 的免費配額或每分鐘配額已被耗盡。以下為快速處理步驟：

- 短期（幾十秒內）重試：Probe 回傳會包含 `retry_delay`（秒數），可等候該秒數後再呼叫 `/_debug/genai_caps?probe=1` 檢查是否回復。程式已實作 in-memory cooldown，會在收到 429 時暫時把該 model 標記為冷卻以避免短時間內重試造成更多 429。
- 臨時降低消耗：在部署上設 `DISABLE_IMAGE_ANALYZE=1`，或暫時把 `GEMINI_MODEL_CANDIDATES` 設為只包含你確定有額度且能使用的 model，減少多模態呼叫。
- 永久解法（建議）：到 Google Cloud Console → IAM & Admin / Quotas，找到與 `generativelanguage.googleapis.com` 或 `GenerateContent` 相關的 quota 條目，按需申請提高配額或啟用付費方案（Billing）。

### 在 GCP Console 申請提高配額（步驟摘要）

1. 登入 Google Cloud Console，選擇你專案（右上角專案選單）。
2. 左側選單搜尋 "Quotas" 並進入 Quotas 頁面。
3. 在搜尋欄輸入 `generativelanguage` 或 `model : gemini-2.5`（或你要使用的 model 關鍵字），過濾出相關的 quota 條目（例如 `GenerateContent input token count limit` / `GenerateContent free tier requests`）。
4. 勾選你要調整的 quota 條目，然後按上方的 "EDIT QUOTAS"（或 "REQUEST QUOTA INCREASE"）按鈕，填寫表單。通常需填寫預期流量、使用原因及聯絡資訊。
5. 等待 Google 審核，審核通過後配額會自動更新，然後你再回到部署環境做一次 probe 確認。

### 權限與 404（model not found）問題處理

- 若 probe 顯示 `404 model not found or not accessible`：代表該 model 或特定版本在你的專案尚未可用，或服務帳戶沒有存取該 model 的權限。請檢查：
   - 你使用的 model 名稱是否與 Console 中的 exact model id 匹配（例如 `gemini-2.5-flash-preview-image`）。
   - 確認專案是否已啟用 Generative AI / Generative Language API，且服務帳戶具備所需 IAM 權限（例如 `roles/aiplatform.user` 或文件上推薦的 role）。

### 建議的現場緊急流程

1. 觀察 probe 回傳的 `retry_delay`（秒）：若為短時間（例如 30~120s），等候後重試。
2. 若常態性 429：在 Render 設 `DISABLE_IMAGE_ANALYZE=1` 來暫停圖片流程，維持服務的文字回覆功能。
3. 同時在 GCP Console 申請提高 quota 或切換到付費 tier，或考慮使用不同專案分散流量（每個專案有獨立 quota）。

如果需要，我可以把上述步驟寫成一份更完整的操作手冊或一鍵 probe 腳本（例如 `scripts/check_models.py --probe`），供你在本機或 CI/CD 使用。
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
