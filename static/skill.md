---
name: ai-hedge-fund
description: AI Hedge Fund Investment Analysis and Multi-Round Committee Debate API. Provides full-stack equity research from 14 legend investor personas (Buffett, Munger, Wood, Burry, Lynch, Ackman, Graham, Fisher, Pelosi, WSB, Technicals, Fundamentals, Sentiment, Valuation) and multi-round round table debates with dynamic portfolio allocation.
---

# 🤖 AI Hedge Fund API - Agent Skill Guide

This document is designed for AI Agents and LLMs to understand and interact with the **AI Hedge Fund API**.

- **Server Base URL**: `http://localhost:6000` (or `http://dns.glsoft.ai:6000`)
- **API Documentation**: `http://localhost:6000/docs`
- **Health Check**: `http://localhost:6000/api/health`
- **Swagger JSON**: `http://localhost:6000/static/swagger.json`
- **Default LLM Engine**: `deepseek-v4-flash` (`https://nen.com.tw/v1/`) with seamless `gpt-4o` (ChatGPT) automatic fallback.

---

## 📌 Available Endpoints

### 1. 📊 Run Stock Analysis (`POST /api/analysis`)
Execute deep investment analysis across selected AI investor personas with optional multi-round round table committee debate.

- **Endpoint**: `POST /api/analysis`
- **Headers**: `Content-Type: application/json`
- **Minimal Request Body (JSON)**:

```json
{
  "tickers": "TSLA,NVDA",
  "enableRoundTable": true,
  "roundTableRounds": 2
}
```

- **Full Request Body Example (JSON)**:

```json
{
  "tickers": "TSLA,NVDA",
  "selectedAnalysts": [
    "warren_buffett",
    "cathie_wood",
    "michael_burry",
    "wsb",
    "technical_analyst"
  ],
  "enableRoundTable": true,
  "roundTableRounds": 2,
  "initialCash": 100000,
  "startDate": "2024-09-01",
  "endDate": "2024-12-01"
}
```

#### Request Parameters:

| Parameter | Type | Required | Default | Description |
|:---|:---|:---:|:---|:---|
| `tickers` | string / array | ✅ | - | Ticker symbols, e.g. `"TSLA,NVDA"`, `"2330.TW"`, `"0001.HK"` |
| `selectedAnalysts` | array | ❌ | `[]` (all 14) | List of analyst keys to participate (see table below) |
| `enableRoundTable` | boolean | ❌ | `false` | Enable multi-round debate committee after analyst signals |
| `roundTableRounds` | integer | ❌ | `2` | Number of debate rounds (1 to 3) |
| `initialCash` | number | ❌ | `100000` | Starting portfolio cash |
| `startDate` | string | ❌ | 3 months ago | Historical start date (`YYYY-MM-DD`) |
| `endDate` | string | ❌ | Today | Analysis end date (`YYYY-MM-DD`) |
| `modelName` | string | ❌ | Server Default | *(Optional)* Override LLM model (Server automatically defaults to `deepseek-v4-flash` with `gpt-4o` fallback) |

#### Response Format (JSON):
```json
{
  "decisions": {
    "TSLA": {
      "action": "buy | sell | short | hold",
      "quantity": 50,
      "confidence": 85.0,
      "reasoning": "Detailed committee execution rationale..."
    }
  },
  "analyst_signals": {
    "warren_buffett_agent": {
      "TSLA": {
        "signal": "bearish",
        "confidence": 90.0,
        "reasoning": "DCF valuation indicates -80% margin of safety..."
      }
    }
  },
  "round_table": {
    "TSLA": {
      "signal": "bearish",
      "confidence": 65.0,
      "discussion_summary": "Warren Buffett and Michael Burry clashed with Cathie Wood on valuation vs innovation...",
      "consensus_view": "Valuation and debt risks outweigh short-term growth prospects.",
      "dissenting_opinions": "Cathie Wood argued for exponential AI/robotics S-curve adoption.",
      "conversation_transcript": "[Warren Buffett]: Intrinsic value doesn't hold up...\n[Cathie Wood]: Look at the innovation engine..."
    }
  }
}
```

---

### 2. 🏛️ Standalone Round Table Debate (`POST /api/round_table`)
Run an investment committee debate with pre-computed analyst signals.

- **Endpoint**: `POST /api/round_table`
- **Headers**: `Content-Type: application/json`
- **Request Body (JSON)**:

```json
{
  "tickers": "NVDA",
  "analystSignals": {
    "cathie_wood": {
      "NVDA": {"signal": "bullish", "confidence": 90, "reasoning": "Exponential AI infrastructure demand"}
    },
    "michael_burry": {
      "NVDA": {"signal": "bearish", "confidence": 75, "reasoning": "Hyperscaler capex peak and concentration risk"}
    }
  },
  "numRounds": 2
}
```

#### Response Format (JSON):
```json
{
  "round_table": {
    "NVDA": {
      "signal": "neutral",
      "confidence": 65.0,
      "discussion_summary": "Cathie Wood debated Michael Burry on AI capex sustainability...",
      "consensus_view": "Strong long-term positioning balanced against near-term concentration risk.",
      "dissenting_opinions": "Michael Burry warned of margin compression if hyperscaler spending cools.",
      "conversation_transcript": "[Cathie Wood]: AI transformation is just beginning...\n[Michael Burry]: Don't ignore the customer concentration risk..."
    }
  }
}
```

---

### 3. 💓 Health Check (`GET /api/health`)
- **Endpoint**: `GET /api/health`
- **Response**: `{"status": "healthy", "version": "2.0.0", "timestamp": "2026-08-26T07:35:04Z"}`

---

## 👥 14 Analyst Personas Reference Table

| Analyst Key | Display Name | Core Investment Philosophy |
|:---|:---|:---|
| `warren_buffett` | **Warren Buffett** | Moats, predictable cash flow, ROE > 15%, 30% margin of safety |
| `charlie_munger` | **Charlie Munger** | Inversion mental model, pricing power, management integrity |
| `ben_graham` | **Ben Graham** | Margin of safety, Net-Net (NCAV), conservative P/E & P/B |
| `cathie_wood` | **Cathie Wood** | Disruptive innovation, 5-year S-curves, AI / robotics CAGR > 25% |
| `bill_ackman` | **Bill Ackman** | Activist value investing, high barrier to entry, operational catalysts |
| `nancy_pelosi` | **Nancy Pelosi** | Congressional trading disclosures, legislative and subsidy tailwinds |
| `michael_burry` | **Michael Burry** | Deep value contrarian, FCF yield > 8%, hidden debt & accounting risks |
| `peter_lynch` | **Peter Lynch** | Consumer insight, PEG ratio < 1.0, 10-bagger growth potential |
| `phil_fisher` | **Phil Fisher** | 15 qualitative points, R&D productivity, outstanding sales execution |
| `wsb` | **WallStreetBets** | Retail momentum, short squeeze, YOLO options, 2md Reddit hype |
| `technical_analyst` | **Technical Analyst** | Trend following, SMA 20/50/200, RSI, MACD, Bollinger Bands |
| `fundamentals_analyst` | **Fundamentals Analyst** | Financial statements audit, revenue growth, gross & net margins |
| `sentiment_analyst` | **Sentiment Analyst** | 2md global news sentiment scoring, SEC Form 4 insider trades |
| `valuation_analyst` | **Valuation Analyst** | Discounted Cash Flow (DCF), EV/EBITDA, relative peer multiples |

---

## 💡 Agent Usage Tips

1. **For General Stock Analysis**:
   - Send `POST /api/analysis` with `enableRoundTable: true` to get both individual analyst metrics and a synthesized committee decision.
2. **For High-Growth / Tech Stocks**:
   - Select `["cathie_wood", "michael_burry", "wsb", "valuation_analyst"]` to get balanced bull/bear debate on growth vs valuation.
3. **For Value / Defensive Stocks**:
   - Select `["warren_buffett", "ben_graham", "charlie_munger", "fundamentals_analyst"]`.
4. **For Non-US Stocks** (e.g. Taiwan `2330.TW`, Hong Kong `0001.HK`):
   - The system automatically normalizes ticker suffixes and leverages 2md search for global news and sentiment.
