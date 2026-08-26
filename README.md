---
name: ai-hedge-fund
description: AI Hedge Fund Investment Analysis and Multi-Round Committee Debate API. Provides full-stack equity research from 14 legend investor personas (Buffett, Munger, Wood, Burry, Lynch, Ackman, Graham, Fisher, Pelosi, WSB, Technicals, Fundamentals, Sentiment, Valuation) and multi-round round table debates with dynamic portfolio allocation.
---

# 🤖 AI Hedge Fund API (v2.0) - Agent Skill & Quick Reference

> **📢 AI Agent / LLM 呼叫指南**：本專案為標準 AI Hedge Fund API 服務。外部 LLM、AI Agent 或前端應用可直接透過 HTTP POST 呼叫本系統，調用 14 位投資大師與多輪圓桌會議（Round Table Committee）達成投資共識決策。

[![API Docs](https://img.shields.io/badge/Swagger-API%20Docs-green.svg)](http://dns.glsoft.ai:6000/docs)
[![Skill Spec](https://img.shields.io/badge/Agent-Skill.md-blue.svg)](http://dns.glsoft.ai:6000/skill.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/release/python-3130/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://hub.docker.com/r/tbdavid2019/ai-hedge-fund-api)

- **🌐 公開 API 主機位址**: `http://dns.glsoft.ai:6000`
- **🏠 本地伺服器位址**: `http://localhost:6000`
- **📑 Swagger UI 文檔**: `http://dns.glsoft.ai:6000/docs`
- **📄 Agent Skill 規範**: `http://dns.glsoft.ai:6000/skill.md`
- **💓 伺服器健康檢查**: `GET http://dns.glsoft.ai:6000/api/health`

---

## ⚡ AI Agent 快速調用指南 (Quick Start for LLMs)

### 1️⃣ 執行多分析師分析與多輪圓桌辯論 (`POST /api/analysis`)

**最簡請求（LLM 呼叫推薦）：**
```bash
curl -X POST "http://dns.glsoft.ai:6000/api/analysis" \
     -H "Content-Type: application/json" \
     -d '{
       "tickers": "TSLA,NVDA",
       "enableRoundTable": true,
       "roundTableRounds": 2
     }'
```

**指定特定分析師組合（例如：價值派 vs 成長派）：**
```bash
curl -X POST "http://dns.glsoft.ai:6000/api/analysis" \
     -H "Content-Type: application/json" \
     -d '{
       "tickers": "AAPL",
       "selectedAnalysts": ["warren_buffett", "cathie_wood", "michael_burry", "wsb"],
       "enableRoundTable": true,
       "roundTableRounds": 2,
       "initialCash": 100000
     }'
```

#### 📋 請求參數說明

| 參數 | 類型 | 必填 | 預設值 | 說明 |
|:---|:---|:---:|:---|:---|
| `tickers` | string / array | ✅ | - | 股票代碼（逗號分隔，支援美股 `TSLA,NVDA`、台股 `2330.TW`、港股 `0001.HK`） |
| `selectedAnalysts` | array | ❌ | `[]` (全部 14 位) | 參與分析的分析師 Key 清單（見下方 14 位分析師速查表） |
| `enableRoundTable` | boolean | ❌ | `false` | 是否在各分析師獨立分析後啟動多輪投資委員會圓桌會議辯論 |
| `roundTableRounds` | integer | ❌ | `2` | 圓桌會議辯論輪數（建議 `1` 到 `3` 輪） |
| `initialCash` | number | ❌ | `100000` | 初始投資組合現金 |
| `startDate` | string | ❌ | 3 個月前 | 歷史數據起始日期（`YYYY-MM-DD`） |
| `endDate` | string | ❌ | 今日 | 歷史數據結束日期（`YYYY-MM-DD`） |
| `modelName` | string | ❌ | 伺服器預設 | *(可選)* 伺服器端預設採用 `deepseek-v4-flash` 並具備 ChatGPT 自動容錯備援，呼叫端**無需強迫傳入** |

#### 📥 回應格式範例 (JSON Response)
```json
{
  "decisions": {
    "TSLA": {
      "action": "buy | sell | short | hold",
      "quantity": 285,
      "confidence": 85.0,
      "reasoning": "投資組合經理與委員會綜合評估之最終下單理由..."
    }
  },
  "analyst_signals": {
    "warren_buffett_agent": {
      "TSLA": {
        "signal": "bearish",
        "confidence": 95.0,
        "reasoning": "內在價值評估顯示負安全邊際 -91%，ROE 與營業利潤率不符標準..."
      }
    }
  },
  "round_table": {
    "TSLA": {
      "signal": "bearish",
      "confidence": 65.0,
      "discussion_summary": "巴菲特與貝瑞質疑估值與負債，伍德為顛覆性創新辯護...",
      "consensus_view": "委員會共識認為當前估值與負債風險壓過了短期創新溢價。",
      "dissenting_opinions": "凱西·伍德主張以 5 年期 S 曲線技術指數增長看待長期潛力。",
      "conversation_transcript": "[Warren Buffett]: Intrinsic value doesn't hold up...\n[Cathie Wood]: Look at the innovation engine..."
    }
  }
}
```

---

### 2️⃣ 獨立發起多輪圓桌會議辯論 (`POST /api/round_table`)
若已預先計算或擁有各方觀點，可直接傳入訊號進行多方激辯與共識產出：

```bash
curl -X POST "http://dns.glsoft.ai:6000/api/round_table" \
     -H "Content-Type: application/json" \
     -d '{
       "tickers": "TSLA",
       "analystSignals": {
         "warren_buffett": {"TSLA": {"signal": "bearish", "confidence": 95, "reasoning": "No margin of safety"}},
         "wsb": {"TSLA": {"signal": "bullish", "confidence": 85, "reasoning": "Diamond hands rocket to the moon"}}
       },
       "numRounds": 2
     }'
```

---

## 👥 14 位 AI 投資分析師速查表

詳細投資哲學、量化模型與決策演算法請見 👉 [**AGENTS.md**](./AGENTS.md)。

| Analyst Key | 顯示名稱 | 核心投資哲學與分析維度 |
|:---|:---|:---|
| `warren_buffett` | **Warren Buffett** | 護城河、持續高 ROE (>15%)、可預測現金流、30% 安全邊際 |
| `charlie_munger` | **Charlie Munger** | 逆向思維 (Invert)、多元思維模型、企業定價權、管理層誠信 |
| `ben_graham` | **Ben Graham** | 安全邊際、雪茄煙蒂法、流動資產淨值 (NCAV)、防禦型財務 |
| `cathie_wood` | **Cathie Wood** | 顛覆性創新、5 年 S 曲線技術革新週期、AI / 機器人 TAM |
| `bill_ackman` | **Bill Ackman** | 激進主義價值投資、高進入壁壘、輕資產現金流、營運催化劑 |
| `nancy_pelosi` | **Nancy Pelosi** | 國會議員股票申報 (Stock Act)、政策補貼與政府法案順風 |
| `michael_burry` | **Michael Burry** | 深度逆向價值、自由現金流收益率 (FCF Yield >8%)、隱藏債務 |
| `peter_lynch` | **Peter Lynch** | 生活選股法、本益成長比 (PEG < 1.0)、尋找 10 倍股潛力 |
| `phil_fisher` | **Phil Fisher** | 15 點質化調研法、頂級研發投入回報率、長期卓越複合成長 |
| `wsb` | **WallStreetBets** | 散戶熱度 (2md SERP/Reddit)、軋空潛力 (Short Squeeze)、YOLO 選擇權動能 |
| `technical_analyst` | **Technical Analyst** | 均線架構 (SMA 20/50/200)、RSI、MACD、布林通道量化指標 |
| `fundamentals_analyst` | **Fundamentals Analyst** | 財務三表深度審查、營收與利潤率 YoY 成長率、ROIC |
| `sentiment_analyst` | **Sentiment Analyst** | 2md 全球即時新聞情緒多空打分、SEC 內部人買賣超分析 |
| `valuation_analyst` | **Valuation Analyst** | 現金流量折現模型 (DCF)、EV/EBITDA、同業相對估值倍數 |

---

## 🚀 項目核心架構與特性

本專案基於 `virattt/ai-hedge-fund` 和 `KRSHH/ritadel` 進行深度重構與擴展：
- 🏛️ **多輪投資圓桌會議 (Multi-Round Round Table)**：讓不同投資流派進行攻防辯論，化解單一視角盲區。
- 🌐 **整合 2md 系列即時搜尋**：透過 `2md.aiurl.tw` / `2md.glsoft.ai` / `create360.ai` 即時獲取全球即時新聞與社群風向，徹底解決非美股與新聞時效問題。
- 🤖 **主要與雙層備援 LLM 機制**：預設採用 `https://nen.com.tw/v1/` (`deepseek-v4-flash`)，若遇異常自動無縫降級至官方 ChatGPT (`gpt-4o`)。
- 📈 **社群風向與散戶情緒**：WSB Agent 整合即時社群動能與選擇權軋空潛力評估。
- 📦 **Docker 一鍵部署**：內建 Flask API 與 Swagger UI，支援 WebSocket 即時日誌廣播與 Discord Webhook 報告推送。

---

📖 **相關文檔導覽：**
- 🤖 [**AGENTS.md**](./AGENTS.md)：14 位分析師投資哲學、量化模型與圓桌會議機制完整介紹
- 📝 [**CHANGELOG.md**](./CHANGELOG.md)：版本更新歷程與詳細改動記錄
- 📄 [**skill.md**](./skill.md)：標準 Agent Skill 規範文件

---

網頁版介面 Web Page
<img width="1516" alt="image" src="https://github.com/user-attachments/assets/e2d443f9-0a48-44ee-a9f4-a61bdfe60e96" />

Telegram Bot 整合
https://github.com/tbdavid2019/telegram-bot-stock2
![image](https://github.com/user-attachments/assets/26d173d0-cc64-4d11-b70b-7735a07c30e0)

---

## 📌 本地安裝與 Docker 部署

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
```ini
# LLM 預設設定
DEFAULT_MODEL=deepseek-v4-flash
DEFAULT_MODEL_PROVIDER=OpenAI-Compatible

# 主要 LLM (nen.com.tw)
PRIMARY_BASE_URL=https://nen.com.tw/v1
PRIMARY_API_KEY=your-primary-api-key
OPENAI_BASE_URL=https://nen.com.tw/v1
OPENAI_API_KEY=your-primary-api-key

# 備援 LLM (ChatGPT 官方)
FALLBACK_BASE_URL=https://api.openai.com/v1
FALLBACK_API_KEY=your-openai-api-key

# 其他支援 LLM（可選）
ANTHROPIC_API_KEY=
GROQ_API_KEY=
GEMINI_API_KEY=

# 金融數據 API Keys（可選）
ALPHA_VANTAGE_API_KEY=
STOCKDATA_API_KEY=
FINNHUB_API_KEY=
EODHD_API_KEY=

# Discord Webhook（可選）
DISCORD_WEBHOOK_ENABLED=false
DISCORD_WEBHOOK_URL=
```

---

### **4️⃣ 啟動服務**

```bash
# 本地直接啟動
python webui2.py

# 或使用 Docker 容器啟動
docker build -t ai-hedge-fund-api .
docker run -d --name ai-hedge-fund-api --env-file .env --restart always -p 6000:6000 ai-hedge-fund-api
```

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
