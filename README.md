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
| 📄 [**skill.md**](./skill.md) | **API 調用規範與端點 Schema**（最簡 POST 範例、JSON 格式、14 位分析師 key） | 🤖 AI Agents & LLMs |
| 🤖 [**AGENTS.md**](./AGENTS.md) | **14 位傳奇投資大師分析模型**（巴菲特、伍德、貝瑞等投資哲學、量化指標、圓桌會議攻防機制） | 📊 投資研究者 / 開發者 |
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
