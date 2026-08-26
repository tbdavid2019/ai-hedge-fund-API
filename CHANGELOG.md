# 📝 更新日誌 (CHANGELOG.md)

本專案遵循語意化版本管理 (Semantic Versioning)。所有重大更新、新增功能與修復項目皆記錄於此。

---

## 🚀 [v2.0.0] - 2026-08-26

### 🌐 1. 導入 2md 即時搜尋與社群風向抓取
- **多節點高可用**：整合 `https://2md.aiurl.tw/`（主要）、`https://2md.glsoft.ai/`（備用 1）、`https://create360.ai/`（備用 2），提供自動故障轉移。
- **即時新聞與情緒**：重構 [src/tools/api.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/src/tools/api.py) 的新聞抓取，加入金融情緒詞彙即時打分，解決過往 Yahoo 新聞預設全為 neutral 的問題。
- **WSB / Reddit 智能降級**：升級 [src/agents/wsb_agent.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/src/agents/wsb_agent.py)，在 Reddit PRAW 憑證失效時，自動透過 2md 搜尋 r/wallstreetbets 與社群討論，精準捕捉迷因熱度與散戶動能。
- **非美股支援強化**：台股（如 `2330.TW`）與港股在缺乏 SEC 內部人交易申報時，自動調整為 100% 新聞與社群情緒權重。

---

### 🏛️ 2. 全新多輪投資圓桌會議 (Multi-Round Round Table)
- **14 位傳奇投資分析師**：補齊巴菲特、蒙格、葛拉漢、伍德、艾克曼、裴洛西、麥可·貝瑞、彼得·林區、菲利普·費雪、WSB、技術分析師、基本面分析師、情緒分析師、估值分析師的 Persona 與辯論風格。
- **結構化多輪辯論引擎**：重構 [src/round_table/engine.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/src/round_table/engine.py)，支援可設定輪數（開場陳述 ➔ 交叉質疑與反駁 ➔ 委員會共識決策）。
- **API 與獨立端點**：
  - `/api/analysis` 支援 `"enableRoundTable": true, "roundTableRounds": 2` 參數。
  - 新增專用端點 `POST /api/round_table`，支援直接傳入各分析師訊號進行獨立辯論。
- **Discord 整合**：分析報告自動嵌入圓桌會議辯論摘要、主要共識與異議觀點。

---

### 🤖 3. 現代 LLM 模型與自訂端點擴充
- **支援現代模型**：
  - **Anthropic**: Claude 3.7 Sonnet, Claude 3.5 Sonnet, Claude 3.5 Haiku
  - **OpenAI**: GPT-4o, GPT-4o-mini, GPT-4.5 Preview, o1, o3-mini
  - **Google Gemini**: Gemini 2.0 Flash, Gemini 2.0 Pro, Gemini 1.5 Pro
  - **DeepSeek**: DeepSeek-V3 (`deepseek-chat`), DeepSeek-R1 (`deepseek-reasoner`)
  - **Groq**: LLaMA-3.3 70B, DeepSeek-R1 Distill 70B
- **自訂 Base URL 支援**：透過 `OPENAI_BASE_URL` 或 `CUSTOM_BASE_URL` 支援 OneAPI、NewAPI 或本地 Ollama 模型串接。

---

### 📑 4. 文檔與 Swagger UI 升級
- 新增 [AGENTS.md](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/AGENTS.md) 完整記載 14 位分析師模型與圓桌會議機制。
- 更新 [static/swagger.json](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/static/swagger.json) 與 Swagger UI（`/docs`、`/swagger`）至 OpenAPI 3.0.3 / v2.0.0 規範。

---

## 📦 [v1.2.0] - 2025-12-01
- 新增健康檢查端點 `/api/health` 與 Swagger UI 文檔頁面 `/docs`。
- 根據標的物數量動態計算投資上限比例（單一標的 100%、多標的平均分散）。
- 支援非美股代號自動轉換（如台股 `2330.TW`、港股 `0001.HK`、陸股 `600519.SS`）。

---

## 📦 [v1.1.0] - 2025-06-20
- 擴充 Michael Burry、Peter Lynch、Phil Fisher、Nancy Pelosi 等投資大師 Agent。
- 加入 Discord Webhook 通知功能。
- 支援以 Docker 映像檔進行容器化部署。

---

## 📦 [v1.0.0] - 2025-03-21
- 初始版本發布：基於 LangGraph 實現 AI 對沖基金分析架構。
- 內建 Flask API 服務與 WebSocket 即時日誌廣播。
