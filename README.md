# AI Hedge Fund API (v2.0)

[![API Docs](https://img.shields.io/badge/Swagger-API%20Docs-green.svg)](http://localhost:6000/docs)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/release/python-3130/)
[![Docker Image](https://img.shields.io/badge/docker-ready-blue.svg)](https://hub.docker.com/r/tbdavid2019/ai-hedge-fund-api)

## 🚀 項目介紹
本專案基於 `virattt/ai-hedge-fund` 和 `KRSHH/ritadel` 進行深度重構與擴展，**提供完整的 Web API 服務**，能模擬頂級對沖基金的運作架構，調用 14 位傳奇投資大師進行深度分析，並透過**多輪圓桌會議辯論**達成最終投資決策。

**🔥 核心特色：**
- 🏛️ **多輪投資圓桌會議 (Multi-Round Round Table)**：模擬巴菲特、伍德、貝瑞、WSB 散戶等 14 位大師的多輪交鋒辯論，達成委員會共識。
- 🌐 **整合 2md 系列即時搜尋**：透過 `2md.aiurl.tw` / `2md.glsoft.ai` / `create360.ai` 即時獲取即時新聞與社群風向，解決非美股與新聞過時問題。
- 🤖 **最新 LLM 與自訂 API 支援**：支援 Claude 3.7 Sonnet、GPT-4.5 Preview、o1/o3-mini、Gemini 2.0 Flash、DeepSeek-V3/R1，以及自訂 `OPENAI_BASE_URL`（相容 OneAPI / NewAPI / Ollama）。
- 📈 **社群風向與散戶情緒**：WSB Agent 整合即時社群動能與選擇權軋空潛力評估。
- 📦 **Docker 一鍵部署**：內建 Flask API 與 Swagger UI（預設運行於 `6000` 連接埠），支援 WebSocket 即時日誌廣播與 Discord Webhook 報告推送。

---

📖 **相關重要文檔：**
- 🤖 [**AGENTS.md**](./AGENTS.md)：14 位分析師投資哲學、量化模型與圓桌會議機制完整介紹
- 📝 [**CHANGELOG.md**](./CHANGELOG.md)：版本更新歷程與詳細改動記錄

---

網頁版 Web Page
<img width="1516" alt="image" src="https://github.com/user-attachments/assets/e2d443f9-0a48-44ee-a9f4-a61bdfe60e96" />

Telegram Bot 整合
https://github.com/tbdavid2019/telegram-bot-stock2
![image](https://github.com/user-attachments/assets/26d173d0-cc64-4d11-b70b-7735a07c30e0)

---

## 📌 環境安裝與部署

### **1️⃣ Clone 本專案**
```bash
git clone https://github.com/tbdavid2019/ai-hedge-fund-API.git
cd ai-hedge-fund-API
```

### **2️⃣ 創建虛擬環境 & 安裝依賴**
```bash
python3 -m venv venv
source venv/bin/activate  # Windows 則使用 venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

### **3️⃣ 設定環境變數 (`.env`)**
請在專案根目錄創建 `.env` 檔案：

```ini
# LLM API Keys（至少設定一個）
OPENAI_API_KEY=your-openai-api-key
ANTHROPIC_API_KEY=your-anthropic-api-key
GROQ_API_KEY=your-groq-api-key
GEMINI_API_KEY=your-gemini-api-key
DEEPSEEK_API_KEY=your-deepseek-api-key

# 自訂 OpenAI 相容網關（可選，如 OneAPI、NewAPI、Ollama）
# OPENAI_BASE_URL=https://your-api-gateway.com/v1

# 金融數據 API Keys（可選）
ALPHA_VANTAGE_API_KEY=your-alpha-vantage-key
STOCKDATA_API_KEY=your-stockdata-key
FINNHUB_API_KEY=your-finnhub-key
EODHD_API_KEY=your-eodhd-key

# Discord Webhook（可選，用於推送分析結果通知）
DISCORD_WEBHOOK_ENABLED=false
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your-webhook-url
```

---

## 🚀 啟動 API 服務

### **本機直接啟動**
```bash
python webui2.py
```
預設 API 運行於 `http://localhost:6000`

### **Docker 一鍵部署**
```bash
# 自行構建映像檔
docker build -t ai-hedge-fund-api .
docker run -d --name ai-hedge-fund-api --env-file .env --restart always -p 6000:6000 ai-hedge-fund-api

# 或直接拉取 Docker Hub 預建映像
docker pull tbdavid2019/ai-hedge-fund-api:latest
docker run -d --name ai-hedge-fund-api --env-file .env --restart always -p 6000:6000 tbdavid2019/ai-hedge-fund-api:latest
```

---

## 📚 API 文檔與端點說明

啟動服務後，可訪問 Swagger UI 進行互動式測試：
- **Swagger UI 介面**: [http://localhost:6000/docs](http://localhost:6000/docs)
- **健康檢查**: [http://localhost:6000/api/health](http://localhost:6000/api/health)
- **即時日誌 WebSocket**: `ws://localhost:6000/ws/logs`

---

## 🔍 API 調用範例

### **1️⃣ 股票分析與多輪圓桌會議 (`POST /api/analysis`)**

```bash
curl -X POST "http://localhost:6000/api/analysis" \
     -H "Content-Type: application/json" \
     -d '{
           "tickers": "TSLA,NVDA",
           "selectedAnalysts": ["warren_buffett", "cathie_wood", "michael_burry", "wsb", "technical_analyst"],
           "modelName": "gpt-4o",
           "enableRoundTable": true,
           "roundTableRounds": 2,
           "initialCash": 100000
         }'
```

#### **請求參數說明**

| 參數 | 類型 | 必填 | 說明 | 範例 |
|:---|:---|:---:|:---|:---|
| `tickers` | string | ✅ | 股票代碼（逗號分隔，支援美股、台股 `2330.TW`、港股 `0001.HK`） | `"TSLA,NVDA"` |
| `selectedAnalysts` | array | ❌ | 指定分析師列表（空陣列表示全部 14 位分析師） | `["warren_buffett", "cathie_wood"]` |
| `modelName` | string | ❌ | LLM 模型名稱（預設 `"gpt-4o"`） | `"claude-3-7-sonnet-latest"`, `"gpt-4o"` |
| `modelProvider` | string | ❌ | 模型供應商（自動推斷，可選 OpenAI, Anthropic, Gemini 等） | `"Anthropic"` |
| `enableRoundTable` | boolean | ❌ | 是否啟用多輪圓桌會議辯論（預設 `false`） | `true` |
| `roundTableRounds` | integer | ❌ | 圓桌會議辯論輪數（預設 `2`，可設 1~3） | `2` |
| `initialCash` | number | ❌ | 初始資金（預設 `100000`） | `100000` |
| `startDate` | string | ❌ | 分析起始日期（YYYY-MM-DD） | `"2024-01-01"` |
| `endDate` | string | ❌ | 分析結束日期（YYYY-MM-DD） | `"2024-12-31"` |

---

### **2️⃣ 獨立執行多輪圓桌會議 (`POST /api/round_table`)**

```bash
curl -X POST "http://localhost:6000/api/round_table" \
     -H "Content-Type: application/json" \
     -d '{
           "tickers": "NVDA",
           "analystSignals": {
             "cathie_wood": {"NVDA": {"signal": "bullish", "confidence": 90, "reasoning": "AI 算力基礎設施爆發式增長"}},
             "michael_burry": {"NVDA": {"signal": "bearish", "confidence": 75, "reasoning": "客戶資本支出可持續性存疑，估值過熱"}}
           },
           "modelName": "gpt-4o",
           "numRounds": 2
         }'
```

---

## 🤖 14 位 AI 投資大師與分析師陣容

詳細模型演算法與分析指標請參閱 👉 [**AGENTS.md**](./AGENTS.md)。

| Key | 顯示名稱 | 核心流派與特點 |
|:---|:---|:---|
| `warren_buffett` | **Warren Buffett** | 護城河、持續高 ROE、可預測現金流、30% 安全邊際 |
| `charlie_munger` | **Charlie Munger** | 逆向思維、多元思維模型、企業定價權、管理層誠信 |
| `ben_graham` | **Ben Graham** | 安全邊際、雪茄煙蒂法、流動資產淨值 (NCAV) |
| `cathie_wood` | **Cathie Wood** | 顛覆性創新、5 年 S 曲線、指數型技術成長 |
| `bill_ackman` | **Bill Ackman** | 激進主義價值投資、高進入壁壘、營運改造催化劑 |
| `nancy_pelosi` | **Nancy Pelosi** | 國會議員交易記錄追蹤、產業法案與政府補貼受惠者 |
| `michael_burry` | **Michael Burry** | 深度逆向價值、自由現金流收益率 (FCF Yield)、隱藏債務 |
| `peter_lynch` | **Peter Lynch** | 生活選股法、本益成長比 (PEG < 1.0)、尋找 10 倍股 |
| `phil_fisher` | **Phil Fisher** | 15 點質化調研、高研發回報率、長期卓越複合成長 |
| `wsb` | **WallStreetBets** | 散戶熱度、迷因潛力、軋空機會、YOLO 選擇權動能 |
| `technical_analyst` | **Technical Analyst** | 均線系統、RSI、MACD、布林通道量化指標 |
| `fundamentals_analyst` | **Fundamentals Analyst** | 財務三表深度審查、利潤率與營收品質評估 |
| `sentiment_analyst` | **Sentiment Analyst** | 2md 即時全球新聞情緒評估、內部人買賣超分析 |
| `valuation_analyst` | **Valuation Analyst** | 現金流量折現模型 (DCF)、EV/EBITDA、相對估值倍數 |

---

## 💰 風險管理 - 動態倉位分配

系統會根據分析的標的物數量，**自動調整每個標的物的投資上限比例**：

| 標的物數量 | 每個標的物上限 | 說明 |
|:---:|:---:|:---|
| 1 個 | **100%** | 單一標的，可全倉投入 |
| 2 個 | **50%** | 平均分配 |
| 3 個 | **33%** | 平均分配 |
| 4 個 | **25%** | 平均分配 |
| 5+ 個 | **20%** | 分散風險 |

---

## 📄 License
本專案基於 [MIT License](LICENSE) 開源。
