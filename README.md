---
name: ai-hedge-fund
description: AI Hedge Fund Investment Analysis and Multi-Round Committee Debate API. Provides full-stack equity research from 16 legend investor personas (Buffett, Munger, Wood, Burry, Lynch, Ackman, Graham, Fisher, Pelosi, WSB, Technicals, Fundamentals, Sentiment, Valuation, Druckenmiller, Jev Decision Model) and multi-round round table debates with dynamic portfolio allocation.
---

# 🤖 AI Hedge Fund API (v2.0)

[![API Docs](https://img.shields.io/badge/Swagger-API%20Docs-green.svg)](https://hedgeapi.afpicapital.com/docs)
[![Skill Spec](https://img.shields.io/badge/Agent-Skill.md-blue.svg)](https://hedgeapi.afpicapital.com/skill.md)
[![Health](https://img.shields.io/badge/Health-200%20OK-brightgreen.svg)](https://hedgeapi.afpicapital.com/api/health)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/release/python-3130/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://hub.docker.com/r/tbdavid2019/ai-hedge-fund-api)

> 🌐 **Official Public HTTPS API**: [https://hedgeapi.afpicapital.com](https://hedgeapi.afpicapital.com)  
> 📑 **Interactive Swagger UI**: [https://hedgeapi.afpicapital.com/docs](https://hedgeapi.afpicapital.com/docs)  
> 📄 **LLM Agent Skill Spec**: [https://hedgeapi.afpicapital.com/skill.md](https://hedgeapi.afpicapital.com/skill.md)  
> 📊 **OpenAPI 3.0.3 Specification**: [https://hedgeapi.afpicapital.com/static/swagger.json](https://hedgeapi.afpicapital.com/static/swagger.json)  
> 💓 **Live Health Check**: `GET https://hedgeapi.afpicapital.com/api/health`

---

## 🇺🇸 English Documentation

An institutional-grade, multi-agent financial quantitative research and investment committee system. Built on **LangGraph** and **Python 3.13**, it orchestrates 16 specialized investment personas, simulates a multi-round round table committee debate, leverages point-in-time quantitative risk controls, and delivers risk-adjusted portfolio allocation decisions.

### 🧭 Documentation Map

| Document | Purpose | Target Audience |
|:---|:---|:---|
| 📄 [**skill.md**](./skill.md) | **API Calling Specification & Endpoint Schema** (minimal JSON payloads, 16 analyst keys, TypeSafe/Groq models) | 🤖 AI Agents & LLMs |
| 🛠️ [**AGENTS.md**](./AGENTS.md) | **Codebase Architecture & AI Developer Guide** (LangGraph state machine, module responsibilities, failover, agent creation) | 🤖 AI Coding Agents |
| 📊 [**ANALYSTS.md**](./ANALYSTS.md) | **16 Investment Analyst & Quantitative Models** (Investment philosophies, financial formulas, debate mechanics) | 📈 Quants & Researchers |
| 📝 [**CHANGELOG.md**](./CHANGELOG.md) | **Version History & Release Notes** (v2.0 architecture, 2md search, TypeSafe integration) | 🛠️ Developers |
| 📑 [**Swagger UI**](https://hedgeapi.afpicapital.com/docs) | **Interactive Web Testing Platform** | 🌐 Web Browsers |

---

### 🚀 Key System Features

1. 🏛️ **Multi-Round Round Table Committee Debate (`POST /api/round_table`)**:
   - Simulates a boardroom debate where 16 legendary personas challenge each other's assumptions across multiple rounds.
   - Outputs comprehensive consensus view, dissenting opinions, debate transcripts, and synthesized conviction scores.
2. 🦅 **Stanley Druckenmiller Inflection Strategy**:
   - Identifies structural fundamental inflections (rate-of-change / 2nd derivative in revenue and gross/operating margins).
   - Evaluates PEG vs forward trajectory to capture highly asymmetric risk/reward setups with strict downside protection.
3. ⚡ **TypeSafe Jev / Clef-Flash SystemOne Fast Evaluation Engine**:
   - Ultra-fast structured evaluation (<200ms) with 3-tier resilient failover:
     - **Primary Tier-1**: Self-hosted Clef-Flash (`https://clef.create360.ai/v1/systemone`)
     - **Fallback Tier-2**: Self-hosted Clef-Flash-Q4 (`https://clef.aiurl.tw/v1/systemone`)
     - **Fallback Tier-3**: TypeSafe Official Service (`https://api.typesafe.ai/v1/systemone`)
4. 🌐 **Live Multi-Node 2md News Search**:
   - Automated real-time sentiment analysis via `2md.aiurl.tw`, `2md.glsoft.ai`, and `create360.ai`.
   - Eliminates knowledge cutoffs and provides instant global coverage for US, Taiwan (`.TW`), Hong Kong (`.HK`), and European equities.
5. 🛡️ **Point-in-Time (PIT) Data & Resumable Backtest Grid (`POST /api/backtest/grid`)**:
   - Strict availability timestamps prevent lookahead bias; SEC acceptance times plus safety buffers are tracked.
   - SQLite-backed state machine supports resuming synchronous multi-ticker date grids (`/api/backtest/runs/{run_id}`).
6. 📈 **Quantitative Risk & Portfolio Management**:
   - Computes 95%/99% VaR, CVaR Expected Shortfall, volatility regime compression, and ATR trailing stops.
   - Automatically sizes portfolio allocations across cash and equity holdings.
7. 🏟️ **Headline Arena Agent Forecasting Arena Integration (`scripts/sync_headline_arena.py`)**:
   - Seamlessly synchronizes macro commodity & index forecasts with [Headline Arena](https://headlinearena.com) ([Issue #4](https://github.com/tbdavid2019/ai-hedge-fund-API/issues/4)).
   - Automatically maps macro futures contracts (Gold `GC`, S&P 500 `ES`, Treasuries `ZN`, Crude `CL`, Bitcoin `BTC`) to liquid underlying ETFs (`GLD`, `SPY`, `TLT`, `USO`, `BTC-USD`), benchmarks committee vs persona convictions, and tracks public verifiable Brier accuracy scores.
8. ⚡ **Independent Algorithmic Decision Model Agent (`decision_model`)**:
   - Packaged as an independent quantitative analyst agent powered by TypeSafe JEV / Clef-Flash SystemOne.
   - Generates calibrated $T+1 \sim T+3$ directional probability distributions (`bullish`, `neutral`, `bearish`) and incorporates PEAD earnings drift.
   - Built with high-availability fail-safe resilience: if remote inference services are unreachable, it automatically gracefully falls back to quantitative statistical momentum without blocking the hedge fund pipeline.

---

### 💻 API Quick Start (cURL)

#### 1. Full Multi-Agent Equity Analysis
```bash
curl -X POST "https://hedgeapi.afpicapital.com/api/analysis" \
     -H "Content-Type: application/json" \
     -d '{
       "tickers": ["2330.TW"],
       "selectedAnalysts": ["stanley_druckenmiller", "warren_buffett", "technical_analyst"],
       "enableRoundTable": true,
       "roundTableRounds": 1,
       "modelName": "clef-flash"
     }'
```

#### 2. Standalone Round Table Committee Debate
```bash
curl -X POST "https://hedgeapi.afpicapital.com/api/round_table" \
     -H "Content-Type: application/json" \
     -d '{
       "tickers": "NVDA",
       "analystSignals": {
         "cathie_wood": {"NVDA": {"signal": "bullish", "confidence": 90, "reasoning": "AI hardware demand"}},
         "michael_burry": {"NVDA": {"signal": "bearish", "confidence": 75, "reasoning": "Hyperscaler capex peak"}}
       },
       "numRounds": 2
     }'
```

#### 3. Point-in-Time Resumable Backtest Grid
```bash
curl -X POST "https://hedgeapi.afpicapital.com/api/backtest/grid" \
     -H "Content-Type: application/json" \
     -d '{
       "runId": "run-2026-q1",
       "tickers": ["AAPL", "2330.TW"],
       "startDate": "2026-01-05",
       "endDate": "2026-01-30",
       "cutoffTimeUtc": "23:59:59Z",
       "selectedAnalysts": ["technical_analyst"],
       "initialCash": 100000
     }'
```

---

### ⚙️ Installation & Deployment

#### 1. Local Environment
```bash
git clone https://github.com/tbdavid2019/ai-hedge-fund-API.git
cd ai-hedge-fund-API

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Copy example configuration and supply your keys
cp .env.example .env

# Run API server (defaults to port 6000)
python webui2.py
```

#### 2. Docker & Watchtower Deployment
```bash
# Build image locally
docker build --network=host -t ai-hedge-fund-api .

# Run container with persistent SQLite storage and hot-reloading
docker run -d --name nice_jemison \
  --label "com.centurylinklabs.watchtower.enable=true" \
  --env-file .env \
  -v $(pwd)/src:/app/src \
  -v $(pwd)/webui2.py:/app/webui2.py \
  -v $(pwd)/static:/app/static \
  -v $(pwd)/instance:/app/instance \
  -e BACKTEST_RUN_DB=/app/instance/backtest_runs.sqlite3 \
  --restart always \
  -p 6000:6000 \
  ai-hedge-fund-api

# Or launch API + Watchtower auto-updater using Docker Compose
docker compose up -d
```

#### 3. Prebuilt Container Images via GHCR
```bash
# Pull and start the prebuilt latest image from GitHub Container Registry
AI_HEDGE_FUND_IMAGE=ghcr.io/tbdavid2019/ai-hedge-fund-api:latest docker compose pull ai-hedge-fund-api
AI_HEDGE_FUND_IMAGE=ghcr.io/tbdavid2019/ai-hedge-fund-api:latest docker compose up -d --no-build
```

---

## 🇹🇼 繁體中文說明

`ai-hedge-fund-API` 是一套企業級、多智慧體（Multi-Agent）金融量化研調與投資決策委員會系統。全系統基於 **LangGraph** 與 **Python 3.13** 開發，模擬現代對沖基金頂級投研流程：由 16 位各具鮮明投資哲學的傳奇大師代理人並行研調，透過**多輪圓桌會議（Round Table Debate）**展開多空辯論攻防，最終整合嚴格的量化風控模型（CVaR、波動率制度）輸出標準化資產配置訂單。

### 🧭 核心文件導覽

| 文件 | 核心內容說明 | 適用對象 |
|:---|:---|:---|
| 📄 [**skill.md**](./skill.md) | **API 調用標準規範與端點 Schema**（最簡 POST 範例、JSON 格式、16 位分析師 key、TypeSafe/Groq 模型規格） | 🤖 AI Agents & LLMs（API 呼叫端） |
| 🛠️ [**AGENTS.md**](./AGENTS.md) | **代碼庫架構與 AI 開發者指南**（LangGraph 狀態機、模組職責、LLM Fallback 容災降級、新增 Agent 規範） | 🤖 AI Coding Agents（代碼維護） |
| 📊 [**ANALYSTS.md**](./ANALYSTS.md) | **16 位傳奇投資分析師量化模型**（巴菲特、卓肯米勒、伍德、貝瑞等投資哲學、量化公式、圓桌會議機制） | 📈 投資研究者 / 開發者 |
| 📝 [**CHANGELOG.md**](./CHANGELOG.md) | **版本更新歷程與異動紀錄**（v2.0 架構、2md 搜尋、TypeSafe Jev 整合） | 🛠️ 維護者 / 開發者 |
| 📑 [**Swagger UI**](https://hedgeapi.afpicapital.com/docs) | **互動式 API 瀏覽器測試平台** | 🌐 瀏覽器線上測試 |

---

### 🚀 系統核心亮點與架構

1. 🏛️ **多輪投資圓桌辯論會議 (`POST /api/round_table`)**：
   - 模擬對沖基金投資委員會，讓 16 位投資大師針對標的多空交鋒（開場破題 ➔ 交叉質疑 ➔ 達成共識決策）。
   - 產出結構化共識結論（Consensus）、異議觀點（Dissent）、辯論對話逐字稿與投資信念度評分。
2. 🦅 **新增第 15 位傳奇大師：Stanley Druckenmiller（史丹利·卓肯米勒）**：
   - 專注尋找營收與營業利益率的「二階正向拐點（Rate-of-Change Inflection）」。
   - 鎖定市場預期落差與低 PEG 比率，捕捉具備向上非對稱盈虧比（Asymmetry）的投資機會，嚴密防範下行風險。
3. ⚡ **TypeSafe Jev / Clef-Flash SystemOne 極速決策引擎**：
   - <200ms 極速結構化推理輸出，提供三層無縫容災降級：
     - **第 1 層 (Primary)**：自建 Clef-Flash (`https://clef.create360.ai/v1/systemone`)
     - **第 2 層 (Fallback)**：自建備援 Clef-Flash-Q4 (`https://clef.aiurl.tw/v1/systemone`)
     - **第 3 層 (Fallback)**：TypeSafe 官方 Jev 服務 (`https://api.typesafe.ai/v1/systemone`)
4. 🌐 **整合 2md 系列多節點即時聯網搜尋**：
   - 自動透過 `2md.aiurl.tw`、`2md.glsoft.ai` 與 `create360.ai` 抓取全球即時新聞與社群聲量。
   - 徹底消除靜態大模型知識盲區，完整支援台股（`2330.TW`）、港股（`0700.HK`）與全球非美資產。
5. 🛡️ **嚴格 Point-in-Time (PIT) 歷史資料點檢驗與可續跑回測**：
   - 精確依據 SEC EDGAR 接收時間與公開可用時間截止，根除未來資訊偏差（Lookahead Bias）。
   - 具備 SQLite 支援之批次同步日期網格回測（`/api/backtest/grid`），支援同配置中斷續跑。
6. 📊 **機構級量化風險管理（CVaR & 波動率制度）**：
   - 動態計算 95%/99% VaR、CVaR 預期虧損率、Amihud 流動性指標、歷史波動率壓縮制度與 ATR 動態追蹤停損。
7. 🏟️ **Headline Arena 公開宏觀預測競技場無縫對接 (`scripts/sync_headline_arena.py`)**：
   - 完美相容 [Headline Arena](https://headlinearena.com) AI Agent 預測協議（[Issue #4](https://github.com/tbdavid2019/ai-hedge-fund-API/issues/4)）。
   - 自動將宏觀期貨題目（黃金 GC、標普 ES、美債 ZN、原油 CL、比特幣 BTC）映射至對應資產，支持委員會共識或卓肯米勒單一大師出戰，公開累積 Brier 評分與預測命中記分卡。
8. ⚡ **獨立量化演算法決策模型 (`decision_model`)**：
   - 將 TypeSafe JEV / Clef-Flash SystemOne 快速推理與短線方向機率預測封裝為獨立分析師 Agent。
   - 直接輸出 $T+1 \sim T+3$ 方向多分類機率向量（看漲、平盤、看跌）與 PEAD 盈餘驚喜漂移信號。
   - 具備強韌高可用降級保證（Fail-Safe）：若外部決策服務全部離線，自動無縫降級為純統計動能基線，絕不中斷避險基金整體流程。

---

### 💻 終端機調用範例 (cURL)

#### 1. 執行股票完整多維度分析
```bash
curl -X POST "https://hedgeapi.afpicapital.com/api/analysis" \
     -H "Content-Type: application/json" \
     -d '{
       "tickers": ["2330.TW"],
       "selectedAnalysts": ["stanley_druckenmiller", "warren_buffett", "technical_analyst"],
       "enableRoundTable": true,
       "roundTableRounds": 1,
       "modelName": "clef-flash"
     }'
```

#### 2. 獨立調用圓桌會議辯論
```bash
curl -X POST "https://hedgeapi.afpicapital.com/api/round_table" \
     -H "Content-Type: application/json" \
     -d '{
       "tickers": "TSLA",
       "analystSignals": {
         "cathie_wood": {"TSLA": {"signal": "bullish", "confidence": 90, "reasoning": "FSD 自動駕駛商業化進程加速"}},
         "michael_burry": {"TSLA": {"signal": "bearish", "confidence": 80, "reasoning": "全球電動車毛利受降價擠壓"}}
       },
       "numRounds": 2
     }'
```

---

### 📦 環境安裝與本機啟動

```bash
# 1. 複製專案庫
git clone https://github.com/tbdavid2019/ai-hedge-fund-API.git
cd ai-hedge-fund-API

# 2. 建立虛擬環境與安裝依賴
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 3. 配置環境變數
cp .env.example .env

# 4. 本地啟動 API 伺服器
python webui2.py
```

---

### 🗼 Watchtower 自動化維運與 yfinance 自主升級

```bash
# 啟動 Watchtower 守護進程（自動監控並升級帶有標籤的容器）
./scripts/start_watchtower.sh

# 檢查 PyPI yfinance 版本並在有更新時自主重建映像
./scripts/auto_rebuild_yfinance.sh

# 強制重建 Docker 容器與依賴
./scripts/auto_rebuild_yfinance.sh --force
```

---

### 💰 風險管理 - 動態倉位分配規則

系統根據分析標的數量自動調整每個標的的投資上限：

| 標的數量 | 個股持倉上限 | 配置說明 |
|:---:|:---:|:---|
| 1 個 | **100%** | 單一標的，在風控額度內可全倉配置 |
| 2 個 | **50%** | 雙標的等權分配 |
| 3 個 | **33%** | 三標的等權分配 |
| 4 個 | **25%** | 四標的等權分配 |
| 5+ 個 | **20%** | 多標的分散投資，防止單一資產集中風險 |

---

## 📄 License

本專案採用 [MIT License](LICENSE) 開源授權協議。
