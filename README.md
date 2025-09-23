LINE + Gemini 穿搭分析（專案說明）

檢查結果（目前 repo 包含）
- `app.py`：主程式、Flask webhook。
- `handlers.py`：LINE 事件處理（文字、圖片）。
- `gemini_client.py`：呼叫 Google Gemini（文字與圖片分析）。
- `state.py`：簡易使用者狀態管理（暫存文字描述）。
- `utils.py`：小工具（文字截斷）。
- `requirements.txt`：運行相依。
- `Dockerfile`, `.dockerignore`：容器化與忽略清單。
- `.env.example`：環境變數範例。

建議（缺少或可改進項目）
- 用於生產環境的 logging（目前未加入）。
- 單元測試/整合測試套件（建議至少加入一個簡單的 test）。
- 更完善的錯誤回報（例如 Sentry）與重試機制。
- 安全：不要把實際 API key 提交到 repo；使用 `.env` 或 CI secret。

元件說明與原理
- `app.py`：啟動 Flask 應用，註冊 LINE webhook。收到 webhook 後透過 `handler.handle` 交由 `handlers` 處理。
- `handlers.py`：包含兩個處理器：
   - `TextMessage`：儲存使用者描述到 `state.py`，並提示使用者上傳圖片。
   - `ImageMessage`：下載 LINE 的圖片內容，檢查大小，呼叫 `gemini_client.image_analyze` 取得分析結果，回覆使用者，並清除暫存狀態。
- `gemini_client.py`：封裝 Google Generative AI（Gemini）呼叫，提供 `text_generate` 與 `image_analyze`。在未設定 `GENAI_API_KEY` 時會回傳提示文字。
- `state.py`：內存暫存使用者描述（thread-safe），以 user_id 為 keyed state，並提供清除與過期檢查函式（目前需外部排程呼叫 `cleanup`）。
- `utils.py`：包含 `truncate` 用來限制 LINE 訊息長度至 2000 字元以內。

功能與使用案例
- 使用案例流程：
   1. 使用者傳送文字描述給 BOT（場合、目的、風格等）。
   2. BOT 儲存描述並回覆「請上傳圖片」。
   3. 使用者上傳圖片，BOT 下載圖片並把圖片與描述送到 Gemini 進行分析。分析結果回覆給使用者。

本地開發與執行
1. 建立並啟用虛擬環境：
# LINE + Gemini 穿搭分析（簡潔使用說明）

本專案是一個簡易的 LINE Bot 範例，會把使用者上傳的圖片與先前輸入的文字描述送到 Google Gemini（Generative AI）做分析，並回覆分析結果。

快速重點
- 要能運行：需要設定 `GENAI_API_KEY`、`LINE_CHANNEL_ACCESS_TOKEN`、`LINE_CHANNEL_SECRET` 三個環境變數。
- 主程式：`app.py`（Flask webhook）；主要功能拆在 `handlers.py`、`gemini_client.py`、`state.py`、`utils.py`。

如何在本機快速跑起來（PowerShell 範例）
1. 建立並啟用虛擬環境：
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
2. 安裝相依：
```powershell
pip install -r requirements.txt
```
3. 設定必要環境變數（直接設定或放在 `.env` 並使用 tools 載入）：
```powershell
$env:GENAI_API_KEY="your_genai_api_key"
$env:LINE_CHANNEL_ACCESS_TOKEN="your_line_channel_access_token"
$env:LINE_CHANNEL_SECRET="your_line_channel_secret"
```
4. 啟動應用：
```powershell
python .\app.py
```
5. （選用）若要讓 LINE 服務能呼叫本機 webhook，可用 `ngrok http 5000` 取得公開 URL，然後把該 URL 設在 LINE Developers 的 Webhook URL。

Docker（快速示例）
```powershell
docker build -t line-gemini-app:latest .
docker run -e LINE_CHANNEL_ACCESS_TOKEN="..." -e LINE_CHANNEL_SECRET="..." -e GENAI_API_KEY="..." -p 5000:5000 line-gemini-app:latest
```

Docker Compose（推薦：一次啟動）
1. 建立 `.env`（或修改現有 `.env.example`）：
```
LINE_CHANNEL_ACCESS_TOKEN=your_token
LINE_CHANNEL_SECRET=your_secret
GENAI_API_KEY=your_genai_key
```
2. 使用 docker-compose 啟動（會自動讀取 `.env`）：
```powershell
docker-compose up --build
```
3. 停止並移除容器：
```powershell
docker-compose down
```

也可以使用 `.
un.ps1 docker-run`，若 `docker-compose.yml` 在目錄中，腳本會改用 `docker-compose up --build`。

目前缺少或建議補上的項目（最少需求）
- 測試：專案目前有 minimal 測試，但建議加入更多單元測試（pytest）來覆蓋 `handlers` 與 `gemini_client` 的核心行為。
- CI：若要在 push 時自動跑測試，請新增 GitHub Actions workflow 並把 `GENAI_API_KEY` 設為 secret（測試應 mock Gemini 呼叫）。
- 監控/錯誤回報：建議在生產加入 logging 與外部錯誤追蹤（例如 Sentry）。

簡短故障排查
- 若 webhook 未觸發：確認 LINE 上 webhook 是否啟用且 URL 正確、以及 Webhook 的憑證（X-Line-Signature）是否能正確驗證。
- 若 Gemini 呼叫失敗：確認 `GENAI_API_KEY` 是否有效，或在本地先用 mock 客戶端測試。

我已做的改動（專案內）
- 在 `app.py` 新增 background cleanup thread 與 logging。
- 新增一個 minimal 的向後相容 shim（`model` 與 `call_gemini_with_retries`），以便舊有測試可正常運行。

要我現在幫你做的事（建議選項）
- 我可以幫你把現有測試數量擴充到覆蓋 `handlers`，並加入 GitHub Actions CI（自動執行 pytest）。
- 或是只針對本地開發優化 README（例如加入範例訊息、Webhook 驗證教學）。

---------------------------------
如果你想要我直接去做其中一件（例如新增 CI、增加測試），寫句簡單指示就好（例如："新增 CI" 或 "寫 tests/test_handlers.py"）。

