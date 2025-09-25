## 快速開始（本機 - PowerShell）

這個專案是一個 LINE Bot 範例，示範如何把使用者的文字描述與上傳的圖片送到 Google Generative AI (Gemini) 做穿搭分析，並回覆結果。以下為快速開始步驟（把使用說明放在最前面，方便開發與部署）：

1. 建立並啟用虛擬環境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. 安裝相依：

```powershell
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

3. 設定必需的環境變數（示例）：

```powershell
$env:GENAI_API_KEY="your_genai_api_key"
$env:LINE_CHANNEL_ACCESS_TOKEN="your_line_channel_access_token"
$env:LINE_CHANNEL_SECRET="your_line_channel_secret"
# Optional (observability / redis)
$env:SENTRY_DSN="https://example@sentry.io/123"
$env:REDIS_URL="redis://localhost:6379/0"
$env:GEMINI_TIMEOUT_SECONDS="15"
$env:MAX_IMAGE_MB="10"
```

4. 啟動應用：

```powershell
python app.py
# 或使用 gunicorn（生產）：
# gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

5. 健康檢查（healthz）：

- 請求 `GET /healthz` 應回 'ok'（狀態碼 200），此 endpoint 可用於 Load Balancer 或平台的健康檢查。

6. 測試

```powershell
pytest -q
```

---

## 專案說明

簡短說明：本專案採用 Flask 作為 webhook server，包含 Gemini wrapper（`gemini_client.py`）、事件處理（`handlers.py`）、狀態管理（`state.py`）、以及 Prompt Injection 防護模組（`prompts.py`, `security/pi_guard.py`, `security/messages.py`）。

## 重點目錄

- `app.py` - Flask 應用與 webhook endpoint。
- `handlers.py` - 處理 LINE 事件（文字/圖片），包含 idempotency 與錯誤分類。
- `gemini_client.py` - 封裝 Google Gemini 呼叫（文字與圖片），包含重試與回傳解析的容錯。
- `state.py` - 可切換的 state backend（Memory / Redis），使用 timezone-aware timestamps。
- `utils.py` - 小工具（例如訊息截斷、安全記錄）。
- `tests/` - pytest 測試套件，包含模擬回傳格式的測試。
- `scripts/` - 開發與測試輔助腳本（例如 `send_test_webhook.py`）。

## 已新增的安全與防護

- Prompt Injection 防護
   - 新增檔案：`prompts.py`, `security/pi_guard.py`, `security/messages.py`。
   - 會先 sanitize 使用者輸入、再掃描常見注入字串；偵測到注入會直接使用 `SAFE_REFUSAL` 回覆並在 Sentry 設 `pi_detected=true`（若啟用 Sentry）。
   - prompt 組成為 `SYSTEM_RULES + TASK_INSTRUCTION + USER_CONTEXT_TEMPLATE (+ 圖片)`，並明確把使用者語境包在 `<<USER_CONTEXT>>...<</USER_CONTEXT>>` 中標示為背景資料而非指令。

## 環境變數與 Secrets

- `GENAI_API_KEY`：Google Gemini API key（測試/生產）。
- `LINE_CHANNEL_ACCESS_TOKEN`：LINE channel access token（回覆訊息用）。
- `LINE_CHANNEL_SECRET`：LINE channel secret（驗證 webhook）。
- `SENTRY_DSN`：若設定，應用會嘗試初始化 Sentry，並在例外發生或 PI 偵測時上報。
- `REDIS_URL`：選填；若設定且 `redis` 套件可用，事件去重（idempotency）會使用 Redis；否則使用 process memory fallback。
- `GEMINI_TIMEOUT_SECONDS`：呼叫 Gemini 的超時（秒），預設 15。
- `MAX_IMAGE_MB`：圖片大小限制（MB），預設 10。

## 部署建議

- 在生產環境：使用 Gunicorn + systemd（或雲端服務如 Render / Heroku / GCP Cloud Run）。
- 把所有敏感資訊放入環境變數或 CI/CD secrets，不要硬編碼在 repo。
- 若要在 CI 中測試 webhook（會用到 ngrok），務必在 workflow 裡下載並使用 ngrok v3 的二進位（避免 runner 中預裝的 ngrok v2 導致 ERR_NGROK_121）。

## 限制與注意事項

- `gemini_client` 目前以 lazy configure（在呼叫時讀取 `GENAI_API_KEY`）以提高測試可替換性與健壯性。
- 生產環境應謹慎處理 API 呼叫錯誤、重試和費用控制（quota）。

## 常見故障排查

- Webhook 驗證失敗（400）：檢查 `X-Line-Signature` 與 `LINE_CHANNEL_SECRET`。
- LINE 無法取得 public webhook（404/410）：確認 ngrok 指向應用的 5000 埠，或部署 URL 是否正確。
- Gemini 呼叫失敗：檢查 `GENAI_API_KEY` 是否存在，並檢視日誌或 Sentry（若已啟用）。

## 變更紀錄（最近）

- 2025-09-25: 合併 PR #1 — gemini_client lazy configure、state timezone-aware、補充測試（14 passed）。

## 新增：Prompt 組成與 Prompt Injection 防禦（2025-09-25）

為了降低模型被 Prompt Injection 的風險，本專案新增了一套分層的 prompt 設計與前置防護：

- Prompt 組成（送至 Gemini 的最終 prompt）
   - SYSTEM_RULES（系統層，唯一定義且不可被使用者覆寫）
   - TASK_INSTRUCTION（任務層：明確要求模型回傳固定 JSON schema 並限制輸出範圍）
   - USER_CONTEXT_TEMPLATE（使用者語境層，格式化為 <<USER_CONTEXT>>...<</USER_CONTEXT>>，明確標記為「僅作為背景資料，非指令」）
   - 圖片與圖片說明（若有）

- 防禦流程
   - sanitize_user_text：去除零寬字元、控制碼、並截斷過長輸入（上限 4096 字）。
   - scan_prompt_injection：使用關鍵字/正則表達式檢測常見注入字串（中英文），也會檢查 URL / 模板標記（例如 `{{...}}`）。
   - 若偵測到注入：
      - 直接回覆安全拒絕模板（`security/messages.py::SAFE_REFUSAL`）。
      - 不把疑慮文字當作指令或送入模型。若啟用 Sentry（環境變數 `SENTRY_DSN`），在事件中標記 `pi_detected=true` 並把偵測 reason 記為 extra。
      - 可選（尚未啟用）：允許在安全模式下僅用三題語境（不帶可疑文字）呼叫模型並附註提醒。

- 新增檔案（本次變更）：
   - `prompts.py` — 定義 `SYSTEM_RULES`, `USER_CONTEXT_TEMPLATE`, `TASK_INSTRUCTION`。
   - `security/pi_guard.py` — 提供 `scan_prompt_injection` 與 `sanitize_user_text`。
   - `security/messages.py` — 提供 `SAFE_REFUSAL`。

- 觀察與部署
   - 若已設定 `SENTRY_DSN` 並且 `sentry-sdk` 安裝可用，發生 prompt injection 時 Sentry event 會包含 tag `pi_detected=true` 與 extra `pi_reason`，可以在 Sentry UI 搜尋 `pi_detected:true`。
   - 本地測試：以含注入字眼的訊息與 webhook 測試腳本（`scripts/send_test_webhook.py`）測試 bot 回覆會看到 `SAFE_REFUSAL`。

如需更嚴格的防護（例如把 OCR/圖片文字也納入掃描），可再擴充 `security/pi_guard.py` 的檢測規則或整合 OCR。

如需我把 README 再拆成更詳細的開發指南或新增 CHANGELOG.md，我可以進一步幫您完成。
```powershell

git rm --cached -r __pycache__
