# 📝 更新日誌 (CHANGELOG.md)

本專案遵循語意化版本管理 (Semantic Versioning)。所有重大更新、新增功能與修復項目皆記錄於此。

---

## 🚀 [v2.3.2] - 2026-09-02

### 🛡️ 1. 全面資安審計與生產環境安全加固 (Security Hardening & Safe Error Sanitization)
- **API 錯誤資訊防洩漏處理**：
  - 於 [`webui2.py`](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/webui2.py) 實作 `format_api_error_response()`，在 HTTP 500 與異步任務異常時自動遮蔽內部詳細檔案路徑與 Traceback，僅在明確開啟 `SHOW_INTERNAL_ERROR_TRACEBACK=true` 或 Debug 模式時暴露，杜絕路徑外洩風險。
- **CI/CD 工作流 Secret 存在性防禦**：
  - 優化 [`.github/workflows/yfinance-auto-update.yml`](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/.github/workflows/yfinance-auto-update.yml)，加入 Docker Hub 金鑰檢測守衛。當倉庫未設置推送 Secrets 時自動發出溫馨提示並優雅跳過，消除誤報性 CI 失敗。
- **安全審計 100% 合規認證**：
  - 經完整 `security-audit` 審查，全庫金鑰零洩漏、Quant 數學極值/除零邊界防護完備、MCP 協議入參嚴格收斂。

---

## 🚀 [v2.3.1] - 2026-09-01

### 🗼 1. 全自動 yfinance 巡檢、GitHub Actions CI/CD 與遠端 Watchtower 熱部署閉環
- **GitHub Actions 自動化排程工作流**：
  - 新增 [`.github/workflows/yfinance-auto-update.yml`](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/.github/workflows/yfinance-auto-update.yml)：每 6 小時自動對 PyPI 官方 API 巡檢 `yfinance` 最新版本。
  - 當檢測到 PyPI 有新版本發布（或手動觸發 / Push 主分支）時，自動執行 `docker build --no-cache` 確保拉取最新無快取之依賴，並自動推送至 Docker Hub (`tbdavid2019/ai-hedge-fund-api:latest`)。
  - 自動回寫並提交版本追蹤檔 [`yfinance.version`](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/yfinance.version)。
- **升級巡檢模組 ([`scripts/check_and_update_yfinance.py`](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/scripts/check_and_update_yfinance.py))**：
  - 增加 `--version-file` 與 `$GITHUB_OUTPUT` 支援，實現 CI/CD 執行環境的無狀態確定性比對。
- **遠端 Watchtower 自動感知與零停機熱重啟**：
  - 伺服器容器帶有 `com.centurylinklabs.watchtower.enable=true` 標籤，Watchtower 守護容器會在 Docker Hub 映像更新後自動拉取最新映像並熱重啟 `nice_jemison`，達成 100% 零人工介入之長效維護。

---

## 🚀 [v2.3.0] - 2026-08-31

### 🧮 1. 注入機構級 Quant 金融數學層 (QuantLib) 增強分析師客觀決策
- **建立量化核心庫 (`src/quant/`)**：
  - `src/quant/risk.py`: 實作歷史模擬法與參數法 95%/99% VaR (Value at Risk)、CVaR (Expected Shortfall)、實現波動度體制判定、最大回撤 (MDD) 與動態風險預算部位控管 (2% 淨值停損上限)。
  - `src/quant/valuation.py`: 實作 5×5 DCF 敏感度分析矩陣 (WACC vs. 永續成長率)、Altman Z-Score 破產風險預警模型、Piotroski F-Score (0~9 分) 財務體質健全度評級。
  - `src/quant/technicals.py`: 實作 Amihud (2002) 非流動性衝擊指標 (Illiquidity Ratio) 與 ATR Chandelier 動態吊燈停損位計算。
- **全面升級核心 Agent**：
  - [src/agents/risk_manager.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/src/agents/risk_manager.py): 升級為基於 CVaR 極端風險預算與波動率逆權重 (Volatility Parity) 計算動態安全下單上限，杜絕高波動標的重創投資組合。
  - [src/agents/valuation.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/src/agents/valuation.py): 結合 DCF 敏感度矩陣、Altman Z-Score 與 Piotroski F-Score，在財務困境時強制降級多頭信號。
  - [src/agents/technicals.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/src/agents/technicals.py): 整合 Amihud 流動性層級與 ATR 吊燈動態停損。
- **單元測試驗證**：
  - 於 [tests/test_quant.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/tests/test_quant.py) 建立完整測試套件，100% 通過驗證。

### 🔌 2. 支援標準 MCP (Model Context Protocol) 伺服器
- **新增 [mcp_server.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/mcp_server.py)**：
  - 基於 `FastMCP` 開發標準 MCP Server，完美整合 Cursor、Claude Desktop、Windsurf 與 Antigravity。
  - **Tool 1: `analyze_stock_with_committee`**: 讓外部 IDE/客戶端一鍵召集 14 位傳奇大師進行多輪圓桌辯論與投資決策。
  - **Tool 2: `get_stock_quant_audit`**: 免 LLM 亞秒級計算任何美股/台股/港股/加密貨幣之完整量化風控與估值審計報告。

---

## 🚀 [v2.2.3] - 2026-08-29

### 🛡️ 1. 全域 Antigravity 規則部署與跨語言多技術棧安全鐵律 (Multi-Stack Iron Rules)
- **全域 Antigravity 規則配置**：
  - 於全域路徑 `~/.gemini/config/AGENTS.md`、`~/.gemini/config/GEMINI.md`、`/Users/david/Documents/git/tbdavid2019/AGENTS.md` 與本專案 [AGENTS.md](file:///Users/david/Documents/git/tbdavid2019/ai-hedge-fund-API/AGENTS.md) 建立最高優先級【最高安全鐵律 · 絕對零容忍 (ZERO-TOLERANCE SECURITY IRON RULE)】。
- **跨語言金鑰隔離標準**：
  - 🐍 **Python**: 一律使用 `os.getenv("KEY_NAME")`。
  - 🟨 **JavaScript / TypeScript / Node.js**: 一律使用 `process.env.KEY_NAME` 或 `import.meta.env.VITE_KEY_NAME`。
  - ☁️ **Cloudflare Workers**: 一律透過 `env.KEY_NAME` 或 `wrangler secret put` 讀取，嚴禁寫入 `wrangler.toml` 或腳本常數中。
  - 🌐 **前端網頁 / HTML / 靜態網站**: 嚴禁在 `<script>` 標籤或 JS 變數硬編碼後端 API Key；一律透過後端 API 代理轉發。
  - 🐚 **Shell / Docker / CI**: 一律透過系統環境變數或受保護的 `.env` 注入。
- **物理層全域 Git 攔截機制**：
  - 於本機與遠端伺服器配置全域 `git config --global core.hooksPath ~/.git_hooks`（`~/.git_hooks/pre-commit`），在 Git 底層強制拒絕並中斷任何包含 `AIzaSy...`、`sk-...`、`gsk_...`、`ghp_...` 等特徵之提交。
- **歷史 Commit 徹底清洗重寫**：
  - 使用 `git filter-branch` 深層清洗所有歷史 Commit 並透過 `git push origin main --force` 強制覆蓋 GitHub，確保全倉庫歷史無任何真實金鑰殘留。

---

## 🚀 [v2.2.2] - 2026-08-29

### ⚡ 1. 預設主力模型優化為 Groq 極速輕量旗艦 `openai/gpt-oss-20b`
- **極速與低延遲推論**：將全系統預設主力模型設為 `openai/gpt-oss-20b`（兼顧超高並發吞吐量、低延遲與穩定性，並支援 `openai/gpt-oss-120b`）。
- **同步更新全局配置**：
  - 更新 [src/llm/models.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/src/llm/models.py)、[src/utils/llm.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/src/utils/llm.py)、[webui2.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/webui2.py)、[src/main.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/src/main.py)。
  - 同步更新 [skill.md](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/skill.md)、[README.md](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/README.md) 與 [AGENTS.md](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/AGENTS.md)。

---

## 🚀 [v2.2.1] - 2026-08-29

### 🐛 1. 修復 yfinance 尾列 NaN 導致市場價格無效 (NaN) 與無法下單 (Hold 0股) 之重大 Bug
- **根因定位**：
  - Yahoo Finance 在美股非開盤時段、週末或盤前同步時，`yf.Ticker().history()` 的最後一行常會返回包含空值之預留列（`Open: NaN, Close: NaN`）。
  - `src/tools/api.py` 過去未過濾 `NaN` 數值，導致 `Price` 物件攜帶 `NaN`；當 `risk_manager` 執行 `prices_df["close"].iloc[-1]` 時直接取得 `NaN` 股價，並傳遞給 `portfolio_manager`。
  - `portfolio_manager` 因無法計算 `max_shares`（計算為 0 股）且當前價格為 `NaN`，迫使大師與經理人只能給出「市場價格無效/缺失 (NaN)，維持觀望 (Hold 0股)」之非預期交易決策。
- **全面修復防護**：
  - [src/tools/api.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/src/tools/api.py)：在 `get_prices()` 中全面過濾 `Close <= 0` 或 `NaN` 行；在 `prices_to_df()` 中自動執行 `df.dropna(subset=['close'])`。
  - [src/agents/risk_manager.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/src/agents/risk_manager.py)：改採 `close_series = prices_df["close"].dropna()` 並驗證 `current_price > 0`，徹底杜絕 `NaN` 進入風控與下單模組。
  - [src/agents/portfolio_manager.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/src/agents/portfolio_manager.py)：加入股價正規化與防呆防護。

---

## 🚀 [v2.2.0] - 2026-08-29

### ⚡ 1. 切換主力模型為 Groq 極速推理架構並強化金鑰防洩漏安全機制
- **主力模型全面升級為 Groq**：
  - 預設主力 LLM 切換為 Groq 極速開源旗艦模型 `openai/gpt-oss-120b`（與備選 `openai/gpt-oss-20b`）。
  - 提供超高吞吐量與亞秒級推論延遲，支援 14 位分析師與投資圓桌會議即時決策。
- **雙層備援機制 (Fallback to Gemini)**：
  - 若遇 Groq 頻率限制或網路抖動，後端自動無縫降級至 Google Gemini `models/gemini-flash-latest`。
- **嚴格金鑰安全與程式碼去硬編碼 (Zero Hardcoded Keys)**：
  - 徹底移除程式碼中所有硬編碼的金鑰字串，所有 API 金鑰均嚴格自 `.env` 動態讀取。
  - `.env.example` 統一改為佔位符（Placeholders），杜絕因 Git Commit 洩漏金鑰之風險。
- **更新核心設定與代碼**：
  - [src/llm/models.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/src/llm/models.py)：更新 `AVAILABLE_MODELS`、`get_model()` 預設為 Groq `openai/gpt-oss-120b`。
  - [src/utils/llm.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/src/utils/llm.py)：`call_llm` 預設為 Groq。
  - [webui2.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/webui2.py) & [src/main.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/src/main.py)：預設模型與供應商切換為 `openai/gpt-oss-120b` / `Groq`。
  - [AGENTS.md](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/AGENTS.md)、[skill.md](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/skill.md) & [README.md](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/README.md)：同步更新架構與接口說明。

---

## 🚀 [v2.1.2] - 2026-08-29

### ⚡ 1. 移除失效 nen.com.tw 並全面升級 Google Gemini 最新旗艦模型
- **移除失效平台模型**：徹底移除不穩定的 `nen.com.tw` / `deepseek-v4-flash` 預設依賴。
- **全面升級主要與備用模型**：
  - 預設 LLM 與 Fallback 全面切換為 Google Gemini 最新模型 `models/gemini-flash-latest`（汰換 `gemini-2.5-flash`）。
  - 支援 Google Gemini 專用權杖環境變數 (`GEMINI_API_KEY`)。
  - 端點統一走 OpenAI 相容協議 `https://generativelanguage.googleapis.com/v1beta/openai/`，大幅提升 14 位分析師與投資圓桌會議推論之產出速度與雙語結構穩定度。
- **API 介面極簡化（前端解耦 LLM 實作細節）**：
  - 徹底自 [skill.md](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/skill.md)、`static/skill.md`、`static/swagger.json` 與 [README.md](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/README.md) 移除前端需要感知或傳遞 `modelName` / `modelProvider` 的反直覺設計。
  - 後端全面封裝 LLM 調度與自動容錯轉移，前端/調用端僅需傳入股票代號（`tickers`）與選填之分析參數。
- **清理失效模型**：自模型清單中移除已失效的 `qwen/qwen3.8-27b`。
- **更新核心設定與代碼**：
  - [src/llm/models.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/src/llm/models.py)：更新 `AVAILABLE_MODELS`、`get_model()` 與 `get_fallback_model()` 預設為 `models/gemini-flash-latest`。
  - [src/utils/llm.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/src/utils/llm.py)：`call_llm` 與安全降級邏輯更新。
  - [webui2.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/webui2.py) & [src/main.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/src/main.py)：預設模型與供應商全面切換為 `models/gemini-flash-latest` / `Gemini`。
  - [AGENTS.md](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/AGENTS.md) & [.env.example](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/.env.example)：同步更新開發規範與環境變數範本。

---

## 🚀 [v2.1.1] - 2026-08-29

### 🔑 1. 修復 LLM 憑證過期與多級容錯降級機制 (解決分析師 Agent 中性 0% 無反應問題)
- **問題根因修復**：修復了因 `PRIMARY_API_KEY`（`nen.com.tw`）權杖過期與 `FALLBACK_API_KEY`（OpenAI）無效，導致巴菲特、蒙格、伍德、貝瑞、林區、費雪、WSB、葛拉漢、艾克曼、裴洛西與投資組合經理等 11 位 LLM 分析師因 401 錯誤而退回預設 `neutral 0%` 的問題。
- **更新有效平台 Token**：更新 `nen.com.tw` 有效金鑰，並支援 `deepseek-v4-flash` 與 `gpt-5-mini` 等核心模型。
- **多級備用容錯架構升級**：
  - 升級 [src/llm/models.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/src/llm/models.py) 的 `get_fallback_model()`，動態支援 `FALLBACK_BASE_URL`、`FALLBACK_MODEL`（預設 Gemini 2.5 Flash / OpenAI compatible）與 `FALLBACK_API_KEY`，擺脫過去寫死 OpenAI 官方 URL 導致額度不足時無法自動切換的問題。
  - 增強 [src/utils/llm.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/src/utils/llm.py) 的 JSON 提取容錯能力（支援無語言標籤的 markdown 區塊與末尾逗號正規化修復）。
  - 更新 [src/round_table/engine.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/src/round_table/engine.py) 的圓桌會議降級調用邏輯。

---

## 🚀 [v2.1.0] - 2026-08-27

### 🗼 1. 導入 Watchtower 自動化維運與 yfinance 自主檢測重建機制
- **整合 Watchtower 自動發布守護進程**：
  - 導入輕量級 (15MB) Golang 運維工具 [Watchtower](https://containrrr.dev/watchtower/)（`containrrr/watchtower`），透過標籤 `com.centurylinklabs.watchtower.enable=true` 實現無人值守自動熱更新。
  - 新增 [scripts/start_watchtower.sh](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/scripts/start_watchtower.sh) 提供一鍵啟動腳本。
  - 新增 [docker-compose.yml](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/docker-compose.yml) 支援 API 服務與 Watchtower 雙容器標準編排。
- **yfinance PyPI 版本自主檢測與自動 Docker 重建**：
  - 新增 [scripts/check_and_update_yfinance.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/scripts/check_and_update_yfinance.py)：自動對比容器內部與 PyPI 上最新的 `yfinance` 版本。
  - 新增 [scripts/auto_rebuild_yfinance.sh](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/scripts/auto_rebuild_yfinance.sh)：當 PyPI 推出新版 `yfinance` 時，自動觸發 Docker 映像重構、重啟容器並執行 `/api/health` 與 Ticker 功能校驗，可無縫加入 Crontab 定時排程。
- **文檔與指令更新**：在 [README.md](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/README.md) 與 [AGENTS.md](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/AGENTS.md) 完整記錄 Watchtower 與自動維護指令。

---

## 🚀 [v2.0.3] - 2026-08-27

### 🌐 1. 優先採用 2MD SERP 高速金融新聞搜尋與修復 yfinance 結構解析
- **2MD SERP 新聞優先化**：在 [src/tools/api.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/src/tools/api.py) 中，將 2MD 即時搜尋 (`2md.aiurl.tw` / `2md.glsoft.ai` / `create360.ai`) 列為第一優先新聞源，並針對台股（`2330.TW`、`*.TWO`）、港股（`*.HK`）與美股動態自適應搜尋關鍵字（例如 `{ticker} 台灣 股票 財經 新聞`），大幅提升非美股新聞涵蓋度與時效性。
- **修復現代 yfinance 新聞結構解析**：全面支援新版 yfinance 回傳之巢狀 `content` 物件（解析 `clickThroughUrl`、`canonicalUrl` 等新欄位），並向下相容舊版扁平結構，徹底修復過去 yfinance 新聞標題與連結遺失問題。
- **歷史價格解析容錯強化**：在 Yahoo Finance 歷史 K 線解析中加入單列異常跳過邏輯，防止單一損毀數據中斷整體歷史股價序列。

---

## 🚀 [v2.0.2] - 2026-08-26

### 🌐 1. 全面支援英文與繁體中文雙語輸出 (Bilingual Reasoning & Debates)
- **AI 分析師雙語推論**：升級 [src/utils/llm.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/src/utils/llm.py) 的 `call_llm`，自動為 14 位投資大師（巴菲特、蒙格、伍德、貝瑞、林區、費雪、WSB、葛拉漢、艾克曼、裴洛西、估值、基本面等）與投資組合經理注入雙語規範，回傳清晰的英文與繁體中文（【繁體中文解析】...）詳細推論。
- **圓桌會議委員會雙語辯論**：升級 [src/round_table/engine.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/src/round_table/engine.py)，使辯論逐字稿 (`conversation_transcript`)、摘要 (`discussion_summary`)、共識觀點 (`consensus_view`) 與異議觀點 (`dissenting_opinions`) 全面包含英文與繁體中文對照。
- **情緒分析師雙語升級**：在 [src/agents/sentiment.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/src/agents/sentiment.py) 增加新聞情緒統計與內部人交易數據之繁體中文解讀。

---

## 🚀 [v2.0.1] - 2026-08-26

### 🛡️ 1. 修復技術指標 NaN 導致 Node.js JSON.parse 解析失敗問題 (RFC 8259 嚴格相容)
- **問題根因修復**：修復了當歷史價格區間較短（如預設 3 個月）時，6 個月動能指標 `momentum_6m` 與長週期波動率計算產出 Python `NaN`，在 JSON 序列化中輸出非標準 `NaN` 字符，導致 Node.js / 前端 Next.js (`route.ts`) 執行 `JSON.parse()` 時拋出 `SyntaxError: Unexpected token 'N', ... NaN is not valid JSON` 的嚴重問題。
- **技術指標滾動計算強化**：在 [src/agents/technicals.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/src/agents/technicals.py) 加入 `min_periods=1` 與 `safe_float` 容錯轉換，確保在任何歷史長度下皆能產出合法數值。
- **全局 JSON 淨化攔截**：在 [webui2.py](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/webui2.py) 實作 `sanitize_json_output` 遞迴過濾器，保證所有 API 回傳數據（`/api/analysis`、`/api/round_table`）中的 `NaN`、`Infinity` 與 `-Infinity` 一律安全轉換為標準 JSON `null` 或合法浮點數。
- **更新 API Skill 規範**：在 [skill.md](file:///Users/david/git/tbdavid2019/ai-hedge-fund-API/skill.md) 與 `static/skill.md` 清楚載明 RFC 8259 JSON 嚴格相容性保證與 Node.js / TypeScript 安全指南。

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
