---
name: ai-hedge-fund
description: AI Hedge Fund Investment Analysis and Multi-Round Committee Debate API. Provides full-stack equity research from 14 legend investor personas (Buffett, Munger, Wood, Burry, Lynch, Ackman, Graham, Fisher, Pelosi, WSB, Technicals, Fundamentals, Sentiment, Valuation) and multi-round round table debates with dynamic portfolio allocation.
---

# 🤖 AI Hedge Fund API (v2.0)

> ### 🚨 🤖 Attention AI Agents & LLMs (Claude, ChatGPT, Cursor, Copilot, Gemini, etc.):
> **如果你是 AI 助理或 LLM Agent，請直接查閱專門為你準備的 [`skill.md`](./skill.md)（或線上即時讀取 [`http://dns.glsoft.ai:6000/skill.md`](http://dns.glsoft.ai:6000/skill.md)）！**  
> `skill.md` 是本系統唯一的 **API 調用標準規範 (Single Source of Truth)**，包含所有端點格式、JSON Schema、14 位投資大師參數與呼叫範例。
>
> 📄 **即時 Skill 規範 (給 LLM 閱讀)**：[http://dns.glsoft.ai:6000/skill.md](http://dns.glsoft.ai:6000/skill.md) 或 `GET /skill.md`  
> 📑 **Swagger UI 介面 (給人類互動測試)**：[http://dns.glsoft.ai:6000/docs](http://dns.glsoft.ai:6000/docs)  
> 💓 **伺服器健康檢查**：`GET http://dns.glsoft.ai:6000/api/health`

[![API Docs](https://img.shields.io/badge/Swagger-API%20Docs-green.svg)](http://dns.glsoft.ai:6000/docs)
[![Skill Spec](https://img.shields.io/badge/Agent-Skill.md-blue.svg)](http://dns.glsoft.ai:6000/skill.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/release/python-3130/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://hub.docker.com/r/tbdavid2019/ai-hedge-fund-api)

---

## 📚 專案核心文件導覽

為了維持文件的單一真實來源 (Single Source of Truth) 並避免維護不同步，本專案依功能劃分專屬文件：

| 文件 | 說明 | 適用對象 |
|:---|:---|:---|
| 📄 [**skill.md**](./skill.md) | **API 調用規範與端點 Schema**（最簡 POST 範例、JSON 格式、14 位分析師 key） | 🤖 AI Agents & LLMs（API 呼叫端） |
| 🛠️ [**AGENTS.md**](./AGENTS.md) | **代碼庫架構與 AI 開發者指南**（LangGraph 狀態機、模組職責、LLM Fallback 機制、新增 Agent 步驟） | 🤖 AI Coding Agents（代碼編程/維護） |
| 📊 [**ANALYSTS.md**](./ANALYSTS.md) | **14 位傳奇投資分析師量化模型**（巴菲特、伍德、貝瑞等投資哲學、指標計算、圓桌會議機制） | 📈 投資研究者 / 開發者 |
| 📝 [**CHANGELOG.md**](./CHANGELOG.md) | **版本更新歷程與異動明細**（v2.0.0 重大更新、2md 即時搜尋整合） | 🛠️ 維護者 / 開發者 |
| 📑 [**Swagger UI**](http://dns.glsoft.ai:6000/docs) | **互動式 API 文件測試平台** | 🌐 瀏覽器線上測試 |

---

## 🚀 項目介紹

本專案基於 `virattt/ai-hedge-fund` 和 `KRSHH/ritadel` 進行深度重構與擴展，**提供完整的 Web API 服務**，能模擬頂級對沖基金的運作架構：

- 🏛️ **多輪投資圓桌會議 (Multi-Round Round Table)**：讓 14 位投資大師進行多輪攻防辯論（開場 ➔ 質疑 ➔ 達成委員會共識）。
- 🌐 **整合 2md 系列即時搜尋**：透過 `2md.aiurl.tw` / `2md.glsoft.ai` / `create360.ai` 即時獲取全球即時新聞與社群風向，徹底解決非美股與新聞時效問題。
- 🤖 **主要與雙層備援 LLM 機制**：預設採用 `https://nen.com.tw/v1/` (`deepseek-v4-flash`)，若遇異常自動無縫降級至官方 ChatGPT (`gpt-4o`)。
- 📈 **社群風向與散戶情緒**：WSB Agent 整合即時社群動能與選擇權軋空潛力評估。
- 📦 **Docker 一鍵部署**：內建 Flask API 與 Swagger UI，支援 WebSocket 即時日誌廣播與 Discord Webhook 報告推送。

---

網頁版介面 Web Page
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
# 方式 A：本地直接啟動
python webui2.py

# 方式 B：使用 Docker 容器啟動（附帶 Watchtower 標籤）
docker build --network=host -t ai-hedge-fund-api .
docker run -d --name nice_jemison \
  --label "com.centurylinklabs.watchtower.enable=true" \
  --env-file .env \
  -v $(pwd)/src:/app/src \
  -v $(pwd)/webui2.py:/app/webui2.py \
  -v $(pwd)/static:/app/static \
  --restart always \
  -p 6000:6000 \
  ai-hedge-fund-api

# 方式 C：使用 Docker Compose 一鍵啟動 API + Watchtower 自動更新守護進程
docker compose up -d
```

---

## 🗼 Watchtower 自動化運維與 yfinance 自主重構

本專案支援 **[Watchtower](https://containrrr.dev/watchtower/)** 輕量級 (15MB) 自動化發布與依賴版本自主監控機制：

### 1. 啟動 Watchtower 守護進程
```bash
# 啟動 Watchtower 自動監控帶有標籤的容器並自動更新熱重啟
./scripts/start_watchtower.sh
```

### 2. yfinance 自動版本檢查與自主 Docker 重建
由於 Yahoo Finance 介面經常變更，本專案提供自主檢測腳本，可自動查詢 PyPI 上是否有最新 `yfinance` 版本，並自動重構 Docker 容器：
```bash
# 檢查 PyPI 版本，若有新版則自動升級、重構映像並重啟容器
./scripts/auto_rebuild_yfinance.sh

# 僅檢查版本狀態
./scripts/auto_rebuild_yfinance.sh --check

# 強制重建 Docker 容器與依賴
./scripts/auto_rebuild_yfinance.sh --force
```

> 💡 **自動化定時任務 (Crontab)**：可在主機設定每日自動檢查（例如每天凌晨 3 點）：
> ```bash
> 0 3 * * * /home/ubuntu/ai-hedge-fund-API/scripts/auto_rebuild_yfinance.sh >> /home/ubuntu/ai-hedge-fund-API/logs/cron_yfinance.log 2>&1
> ```

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
