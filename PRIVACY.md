# Privacy & Academic Use / プライバシーと学術利用について

本アプリは大学の卒業プロジェクトです。LINE ボットとして、ユーザーのコーディネートを
AI で採点・要約し、提案アイテムを楽天市場 API（IchibaItem/Search/20220601）で検索して
リンクを表示します。非商用・学術目的で利用し、1 RPS 以内のレート制御とキャッシュを行います。
個人情報は保存しません。

---

這是一個大學專題的 LINE 機器人。AI 會依使用者提供的情境與穿搭資訊產生評分與建議，
接著呼叫日本樂天市場 Ichiba Item Search API（20220601）搜尋相關單品並提供連結。
僅作學術/非商用用途，實作有節流（≤1 RPS）與快取，不儲存個資。

## 隱私權與使用說明 / Privacy & Usage

本服務為大學專題用途之 LINE 機器人，提供穿搭評分與建議，並使用
Rakuten Ichiba Item Search API 顯示可能適合的單品連結。

- 非商業用途、僅供學術展示。
- 不蒐集或永久保存個人可識別資訊。訊息僅用於即時回覆。
- 呼叫第三方 API（Rakuten Ichiba Item Search 20220601）時遵守其使用條款與速率限制（≤ 1 req/sec）。
- 商品資訊以對方頁面為準；本服務不保證價格或存貨。
- 聯絡方式：yofatyozi@gmail.com

---

## Implementation notes (實作說明)

- Rate limiting: Implemented server-side throttle to ensure calls to Rakuten Ichiba API remain ≤1 RPS per application.
- Caching: Search results are cached (TTL configurable) to avoid repeated identical calls and to reduce rate consumption.
- Data retention: No user-identifiable data is permanently stored. Ephemeral conversation state may be kept in memory or Redis for short-lived sessions and is discarded per design.

---