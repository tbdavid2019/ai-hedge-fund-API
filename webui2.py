import os
import sys
# 確保 Python 可以找到 `src/` 內的模組
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))
import json
import threading
import traceback
import requests
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from flask_sock import Sock
from datetime import datetime
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv

from src.main import run_hedge_fund
from src.agents.round_table import round_table
from src.llm.models import ModelProvider, get_model_info

# 加載 .env 環境變數
load_dotenv()

# Discord Webhook 設定
DISCORD_WEBHOOK_ENABLED = os.environ.get("DISCORD_WEBHOOK_ENABLED", "false").lower() == "true"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# 設置 Flask 伺服器
app = Flask(__name__, static_folder='static', static_url_path='/static')
CORS(app, resources={r"/*": {"origins": "*"}})  # 允許跨域請求
sock = Sock(app)

# WebSocket 客戶端列表
websocket_clients = []


def infer_model_provider(model_name: str, specified_provider: str = None) -> str:
    """自動推斷 LLM 模型供應商"""
    if specified_provider and specified_provider.lower() not in ["auto", ""]:
        return specified_provider
    
    if not model_name:
        return "OpenAI"
    
    name = model_name.lower()
    if "claude" in name:
        return "Anthropic"
    elif "gemini" in name:
        return "Gemini"
    elif "deepseek-r1-distill" in name or "llama" in name:
        return "Groq"
    elif "deepseek" in name:
        return "DeepSeek"
    return "OpenAI"


def send_discord_notification(tickers, result, analysis_date):
    """發送分析結果及圓桌會議到 Discord"""
    if not DISCORD_WEBHOOK_ENABLED or not DISCORD_WEBHOOK_URL:
        return
    
    try:
        embeds = []
        
        # 主要標題 Embed
        main_embed = {
            "title": "🤖 AI Hedge Fund 分析與決策報告",
            "description": f"**分析日期:** {analysis_date}\n**標的代號:** {', '.join(tickers)}",
            "color": 0x00ff00,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": "AI Hedge Fund API v2.0"
            }
        }
        embeds.append(main_embed)
        
        # 投資組合決策結果 Embed
        if "decisions" in result:
            for ticker, decision in result["decisions"].items():
                action = str(decision.get("action", "N/A")).upper()
                confidence = decision.get("confidence", 0)
                quantity = decision.get("quantity", 0)
                reasoning = str(decision.get("reasoning", "N/A"))
                
                if action == "BUY":
                    color = 0x00ff00
                    emoji = "🟢"
                elif action in ["SELL", "SHORT"]:
                    color = 0xff0000
                    emoji = "🔴"
                else:
                    color = 0xffff00
                    emoji = "🟡"
                
                decision_embed = {
                    "title": f"{emoji} {ticker} - 建議操作: {action}",
                    "fields": [
                        {"name": "信心度", "value": f"{confidence}%", "inline": True},
                        {"name": "數量", "value": str(quantity), "inline": True},
                        {"name": "投資理由", "value": reasoning[:1000] if len(reasoning) > 1000 else reasoning, "inline": False}
                    ],
                    "color": color
                }
                embeds.append(decision_embed)

        # 圓桌會議結論 Embed（若有啟用）
        if "round_table" in result:
            for ticker, rt in result["round_table"].items():
                rt_signal = str(rt.get("signal", "neutral")).upper()
                rt_conf = rt.get("confidence", 0)
                rt_summary = str(rt.get("discussion_summary", ""))
                rt_consensus = str(rt.get("consensus_view", ""))
                rt_dissent = str(rt.get("dissenting_opinions", ""))

                rt_color = 0x00ff00 if rt_signal == "BULLISH" else (0xff0000 if rt_signal == "BEARISH" else 0xffff00)
                rt_embed = {
                    "title": f"🏛️ {ticker} 多輪投資圓桌會議共識 - {rt_signal} ({rt_conf}%)",
                    "fields": [
                        {"name": "辯論摘要", "value": rt_summary[:600] if len(rt_summary) > 600 else rt_summary, "inline": False},
                        {"name": "主要共識", "value": rt_consensus[:400] if len(rt_consensus) > 400 else rt_consensus, "inline": True},
                        {"name": "異議觀點", "value": rt_dissent[:400] if len(rt_dissent) > 400 else rt_dissent, "inline": True},
                    ],
                    "color": rt_color
                }
                embeds.append(rt_embed)
        
        # 分析師信號摘要 Embed
        if "analyst_signals" in result:
            signals_summary = []
            for agent_name, signals in result["analyst_signals"].items():
                if agent_name in ["risk_management_agent", "portfolio_management_agent", "round_table"]:
                    continue
                for ticker, signal_data in signals.items():
                    signal = signal_data.get("signal", "N/A")
                    conf = signal_data.get("confidence", 0)
                    
                    if signal == "bullish":
                        emoji = "🟢"
                    elif signal == "bearish":
                        emoji = "🔴"
                    else:
                        emoji = "🟡"
                    
                    agent_display = agent_name.replace("_agent", "").replace("_", " ").title()
                    signals_summary.append(f"{emoji} **{agent_display}**: {signal} ({conf}%)")
            
            if signals_summary:
                signals_embed = {
                    "title": "📊 各分析師信號摘要",
                    "description": "\n".join(signals_summary[:15]),
                    "color": 0x0099ff
                }
                embeds.append(signals_embed)
        
        # 發送到 Discord
        payload = {
            "username": "AI Hedge Fund Committee",
            "avatar_url": "https://cdn-icons-png.flaticon.com/512/2103/2103633.png",
            "embeds": embeds[:10]
        }
        
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code == 204:
            print(f"[Discord] 通知發送成功")
        else:
            print(f"[Discord] 通知發送失敗: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"[Discord] 發送通知時發生錯誤: {str(e)}")


def broadcast_log(message, level="info"):
    log_data = {"level": level, "message": message, "timestamp": datetime.utcnow().isoformat() + "Z"}
    for client in websocket_clients[:]:
        try:
            client.send(json.dumps(log_data))
        except Exception:
            websocket_clients.remove(client)


@app.route('/')
@app.route('/skill.md')
def serve_skill_md():
    """提供 Skill MD 文件供 AI Agent / LLM 參考與調用指南"""
    skill_path = os.path.join(os.path.dirname(__file__), "static", "skill.md")
    if not os.path.exists(skill_path):
        skill_path = os.path.join(os.path.dirname(__file__), "skill.md")
    
    if os.path.exists(skill_path):
        with open(skill_path, "r", encoding="utf-8") as f:
            content = f.read()
        return Response(content, mimetype="text/markdown; charset=utf-8")
    return Response("# AI Hedge Fund API\n\nPlease visit /docs for Swagger UI documentation.", mimetype="text/plain; charset=utf-8")


@app.route('/api/health', methods=['GET'])
def health_check():
    """健康檢查端點"""
    return jsonify({
        "status": "healthy",
        "version": "2.0.0",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    })


@app.route('/docs')
@app.route('/swagger')
def swagger_ui():
    """Swagger UI 文檔頁面"""
    return '''
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Hedge Fund API - Swagger UI</title>
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui.css">
    <style>
        body { margin: 0; padding: 0; }
        .swagger-ui .topbar { display: none; }
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui-bundle.js"></script>
    <script>
        window.onload = function() {
            SwaggerUIBundle({
                url: "/static/swagger.json",
                dom_id: '#swagger-ui',
                presets: [
                    SwaggerUIBundle.presets.apis,
                    SwaggerUIBundle.SwaggerUIStandalonePreset
                ],
                layout: "BaseLayout"
            });
        };
    </script>
</body>
</html>
'''


@app.route('/api/analysis', methods=['POST'])
def run_analysis():
    """執行對股票的多維度分析與可選的圓桌會議"""
    try:
        data = request.get_json() or {}
        raw_tickers = data.get('tickers', '')
        if isinstance(raw_tickers, list):
            ticker_list = [t.strip() for t in raw_tickers if t.strip()]
        else:
            ticker_list = [t.strip() for t in str(raw_tickers).split(',') if t.strip()]
            
        selected_analysts = data.get('selectedAnalysts', [])
        default_model = os.getenv("DEFAULT_MODEL", "gpt-4o")
        default_provider = os.getenv("DEFAULT_MODEL_PROVIDER", "")
        model_name = data.get('modelName') or default_model
        model_provider = infer_model_provider(model_name, data.get('modelProvider') or default_provider)
        
        enable_round_table = bool(data.get('enableRoundTable', False) or data.get('enable_round_table', False))
        round_table_rounds = int(data.get('roundTableRounds', 2) or data.get('round_table_rounds', 2))
        is_crypto = bool(data.get('isCrypto', False) or data.get('is_crypto', False))

        # 設定開始與結束時間
        end_date = data.get('endDate') or datetime.now().strftime('%Y-%m-%d')
        start_date = data.get('startDate') or (datetime.strptime(end_date, '%Y-%m-%d') - relativedelta(months=3)).strftime('%Y-%m-%d')

        # 初始投資組合
        portfolio = {
            "cash": data.get('initialCash', 100000),
            "positions": {},
            "cost_basis": {},
            "realized_gains": {ticker: {"long": 0.0, "short": 0.0} for ticker in ticker_list}
        }

        broadcast_log(f"Starting analysis for {ticker_list} (RoundTable={enable_round_table}, Model={model_name})", "info")

        # 執行完整分析
        result = run_hedge_fund(
            tickers=ticker_list,
            start_date=start_date,
            end_date=end_date,
            portfolio=portfolio,
            show_reasoning=True,
            selected_analysts=selected_analysts,
            model_name=model_name,
            model_provider=model_provider,
            is_crypto=is_crypto,
            enable_round_table=enable_round_table,
            round_table_rounds=round_table_rounds
        )

        broadcast_log("Analysis completed successfully", "success")
        
        # 發送 Discord 通知
        send_discord_notification(ticker_list, result, end_date)
        
        return jsonify(result)

    except Exception as e:
        error_message = f"API Error: {str(e)}"
        broadcast_log(error_message, "error")
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@app.route('/api/round_table', methods=['POST'])
def run_round_table_endpoint():
    """獨立執行多輪圓桌會議端點"""
    try:
        data = request.get_json() or {}
        raw_tickers = data.get('tickers', '')
        if isinstance(raw_tickers, list):
            ticker_list = [t.strip() for t in raw_tickers if t.strip()]
        else:
            ticker_list = [t.strip() for t in str(raw_tickers).split(',') if t.strip()]
            
        analyst_signals = data.get('analystSignals') or data.get('analyst_signals') or {}
        default_model = os.getenv("DEFAULT_MODEL", "gpt-4o")
        default_provider = os.getenv("DEFAULT_MODEL_PROVIDER", "")
        model_name = data.get('modelName') or default_model
        model_provider = infer_model_provider(model_name, data.get('modelProvider') or default_provider)
        num_rounds = int(data.get('numRounds', 2) or data.get('roundTableRounds', 2))

        broadcast_log(f"Starting standalone round table debate for {ticker_list}", "info")

        rt_results = round_table(
            data={
                "tickers": ticker_list,
                "analyst_signals": analyst_signals
            },
            model_name=model_name,
            model_provider=model_provider,
            show_reasoning=True,
            num_rounds=num_rounds
        )

        broadcast_log("Round table debate completed successfully", "success")
        return jsonify({"round_table": rt_results})

    except Exception as e:
        error_message = f"Round Table API Error: {str(e)}"
        broadcast_log(error_message, "error")
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@sock.route('/ws/logs')
def logs(ws):
    """WebSocket 端點來監控即時日誌"""
    websocket_clients.append(ws)
    try:
        while True:
            ws.receive()
    except Exception:
        if ws in websocket_clients:
            websocket_clients.remove(ws)


if __name__ == "__main__":
    api_thread = threading.Thread(target=app.run, kwargs={"host": "0.0.0.0", "port": 6000, "debug": True, "use_reloader": False})
    api_thread.daemon = True
    api_thread.start()
    print("API Server started on http://localhost:6000")
    api_thread.join()
