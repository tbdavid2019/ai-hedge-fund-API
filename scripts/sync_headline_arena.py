#!/usr/bin/env python3
"""
Headline Arena Sync Adapter for AI Hedge Fund API (scripts/sync_headline_arena.py)

Autonomous bridge connecting the AI Hedge Fund's 15 investment personas
and Multi-Round Committee Debate to Headline Arena (https://headlinearena.com).

Supported Macro Futures Assets:
- ES (E-mini S&P 500) -> SPY
- GC (Gold) -> GLD
- SI (Silver) -> SLV
- CL (Crude Oil) -> USO
- ZN (10-Yr US Treasury) -> TLT
- BTC (Bitcoin) -> BTC-USD
- HG (Copper) -> CPER
- NG (Natural Gas) -> UNG

Usage:
  # Check status and open challenges (dry run)
  python3 scripts/sync_headline_arena.py --dry-run

  # Register hedge fund agent with Headline Arena
  python3 scripts/sync_headline_arena.py --register --agent-name ai-hedge-fund-macro

  # Run analysis on active challenges and submit predictions
  python3 scripts/sync_headline_arena.py --submit

  # Submit from a specific guru persona (e.g. Stanley Druckenmiller)
  python3 scripts/sync_headline_arena.py --submit --persona stanley_druckenmiller

  # Inspect agent status and scorecard
  python3 scripts/sync_headline_arena.py --status
"""

import os
import sys
import json
import time
import uuid
import re
import argparse
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

# Version & Headers
CLI_VERSION = "2.3.0"
DEFAULT_HA_ORIGIN = "https://headlinearena.com"
DEFAULT_HEDGE_FUND_URL = "https://hedgeapi.afpicapital.com"
CRED_DIR = Path(os.environ.get("HA_HOME", str(Path.home() / ".headlinearena")))
CRED_FILE = CRED_DIR / "credentials.json"

# Macro Asset Mapping: Headline Arena Asset Code -> AI Hedge Fund Ticker
ASSET_MAP = {
    "ES": "SPY",
    "GC": "GLD",
    "SI": "SLV",
    "CL": "USO",
    "ZN": "TLT",
    "BTC": "BTC-USD",
    "HG": "CPER",
    "NG": "UNG",
}

ALL_SCOPES = [
    "comment:create", "comment:reply", "comment:like", "comment:read:context",
    "comment:delete:self", "reply:like", "follow:create", "follow:delete:self",
    "follow:read", "space:read", "profile:read:self", "profile:read:public",
    "profile:write:self", "prediction:submit", "challenge:read", "credits:read",
    "signal:publish", "signal:subscribe", "delegation:request", "delegation:provide",
]


def load_env_file():
    """Load key-values from local or parent .env without overriding existing os.environ."""
    env_paths = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent / ".env",
    ]
    for p in env_paths:
        if p.exists():
            try:
                for line in p.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k not in os.environ:
                            os.environ[k] = v
            except Exception:
                pass


load_env_file()


class HeadlineArenaClient:
    """Zero-dependency client for Headline Arena agent API."""

    def __init__(self, origin: Optional[str] = None):
        self.origin = (origin or os.environ.get("HA_BASE_URL", DEFAULT_HA_ORIGIN)).rstrip("/")
        if self.origin.endswith("/api/v1"):
            self.origin = self.origin[:-len("/api/v1")]
        self.api_base = f"{self.origin}/api/v1"
        self._token_cache: Optional[Dict[str, Any]] = None

    def _headers(self, token: Optional[str] = None, agent_id: Optional[str] = None) -> Dict[str, str]:
        h = {
            "User-Agent": f"headlinearena-cli/{CLI_VERSION}",
            "X-HA-Plugin-Version": CLI_VERSION,
            "X-HA-Plugin-Host": "ai-hedge-fund",
            "Content-Type": "application/json",
            "X-Request-Id": str(uuid.uuid4()),
        }
        if token:
            h["Authorization"] = f"Bearer {token}"
        if agent_id:
            h["X-Agent-Id"] = agent_id
        return h

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        token: Optional[str] = None,
        agent_id: Optional[str] = None,
        timeout: int = 30
    ) -> Tuple[int, Dict[str, Any]]:
        url = path if path.startswith("http") else f"{self.api_base}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = self._headers(token=token, agent_id=agent_id)
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8")
                try:
                    return resp.status, json.loads(text) if text else {}
                except json.JSONDecodeError:
                    return resp.status, {"raw": text}
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8")
            try:
                return e.code, json.loads(text) if text else {"detail": str(e)}
            except json.JSONDecodeError:
                return e.code, {"detail": text or str(e)}
        except Exception as exc:
            return 500, {"detail": f"Transport error: {exc}"}

    def load_credentials(self) -> Dict[str, Any]:
        """Load stored credentials from CRED_FILE or environment variables."""
        # 1. Check environment variables
        env_agent_id = os.environ.get("HA_AGENT_ID")
        env_secret = os.environ.get("HA_CLIENT_SECRET")
        if env_agent_id and env_secret:
            return {
                "agent_id": env_agent_id,
                "client_secret": env_secret,
                "agent_name": os.environ.get("HA_AGENT_NAME", "ai-hedge-fund-env"),
                "status": "active",
            }

        # 2. Check credentials.json
        if CRED_FILE.exists():
            try:
                data = json.loads(CRED_FILE.read_text(encoding="utf-8"))
                origin_data = data.get(self.origin, {})
                default_agent = origin_data.get("_default_agent")
                agents = origin_data.get("_agents", {})
                if default_agent and default_agent in agents:
                    return agents[default_agent]
                if agents:
                    # Return first available agent
                    return next(iter(agents.values()))
            except Exception:
                pass
        return {}

    def save_credentials(self, entry: Dict[str, Any], set_default: bool = True):
        """Save credentials to CRED_FILE matching ha.py format."""
        CRED_DIR.mkdir(parents=True, exist_ok=True)
        store = {}
        if CRED_FILE.exists():
            try:
                store = json.loads(CRED_FILE.read_text(encoding="utf-8"))
            except Exception:
                store = {}

        org = store.setdefault(self.origin, {})
        agents = org.setdefault("_agents", {})
        agent_id = entry.get("agent_id")
        if not agent_id:
            return

        agents[agent_id] = entry
        if set_default or org.get("_default_agent") is None:
            org["_default_agent"] = agent_id

        CRED_FILE.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")

    def get_token(self, force: bool = False) -> Optional[str]:
        """Retrieve cached JWT token or fetch a fresh one via client credentials."""
        creds = self.load_credentials()
        agent_id = creds.get("agent_id")
        client_secret = creds.get("client_secret")
        if not agent_id or not client_secret:
            return None

        # Check existing cached token in creds
        token_info = creds.get("token") or {}
        now = time.time()
        if not force and token_info.get("access_token") and token_info.get("expires_at", 0) - 60 > now:
            return token_info["access_token"]

        # Request new token
        payload = {
            "grant_type": "client_credentials",
            "agent_id": agent_id,
            "client_secret": client_secret,
        }
        status, resp = self._request("POST", "/agent/auth/token", payload)
        if status == 200 and "access_token" in resp:
            access_token = resp["access_token"]
            expires_in = resp.get("expires_in", 900)
            token_entry = {
                "access_token": access_token,
                "expires_at": int(now + expires_in),
            }
            creds["token"] = token_entry
            self.save_credentials(creds)
            return access_token
        return None

    def authed_request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Tuple[int, Dict[str, Any]]:
        """Authenticated request with automatic single retry on 401."""
        creds = self.load_credentials()
        agent_id = creds.get("agent_id")
        token = self.get_token()
        if not token:
            return 401, {"detail": "No credentials or access token available. Run --register first."}

        status, resp = self._request(method, path, body, token=token, agent_id=agent_id)
        if status == 401:
            token = self.get_token(force=True)
            status, resp = self._request(method, path, body, token=token, agent_id=agent_id)
        return status, resp

    def solve_onboarding_challenge(self, prompt: str, submit_url: str) -> bool:
        """Automatically solve onboarding challenge via Groq or Gemini REST API."""
        print("🧠 [Headline Arena] Solving agent onboarding challenge with LLM reasoning...")
        system_instruction = (
            "You are an expert quantitative macro analyst. Return ONLY the requested JSON object "
            "strictly adhering to the Required JSON Response Format. Do not enclose in markdown blocks, "
            "do not add preamble or trailing commentary."
        )

        llm_json_text = ""
        # 1. Try Groq
        groq_key = os.environ.get("GROQ_API_KEY")
        if groq_key:
            try:
                groq_payload = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.2,
                }
                req = urllib.request.Request(
                    "https://api.groq.com/openai/v1/chat/completions",
                    data=json.dumps(groq_payload).encode("utf-8"),
                    headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=30) as r:
                    res = json.loads(r.read().decode("utf-8"))
                    llm_json_text = res["choices"][0]["message"]["content"]
            except Exception as e:
                print(f"⚠️ Groq solver attempt failed: {e}")

        # 2. Try Gemini fallback if needed
        if not llm_json_text:
            gemini_key = os.environ.get("FALLBACK_API_KEY") or os.environ.get("GEMINI_API_KEY")
            if gemini_key:
                try:
                    gemini_url = f"https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
                    gemini_payload = {
                        "model": "models/gemini-flash-latest",
                        "messages": [
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.2,
                    }
                    req = urllib.request.Request(
                        gemini_url,
                        data=json.dumps(gemini_payload).encode("utf-8"),
                        headers={"Authorization": f"Bearer {gemini_key}", "Content-Type": "application/json"},
                        method="POST"
                    )
                    with urllib.request.urlopen(req, timeout=30) as r:
                        res = json.loads(r.read().decode("utf-8"))
                        llm_json_text = res["choices"][0]["message"]["content"]
                except Exception as e:
                    print(f"⚠️ Gemini solver attempt failed: {e}")

        if not llm_json_text:
            print("❌ No LLM API key available to solve onboarding challenge. Please set GROQ_API_KEY or GEMINI_API_KEY.")
            return False

        # Clean JSON text
        match = re.search(r"\{.*\}", llm_json_text, re.DOTALL)
        if match:
            clean_json = match.group(0)
        else:
            clean_json = llm_json_text.strip()

        try:
            parsed_answer = json.loads(clean_json)
        except Exception as exc:
            print(f"❌ Failed to parse LLM answer as JSON: {exc}")
            return False

        # Submit answer to challenge submit_url
        submit_status, submit_resp = self._request("POST", submit_url, {"answer": parsed_answer})
        if submit_status in (200, 201) and submit_resp.get("passed"):
            print(f"🎉 [Headline Arena] Challenge PASSED! Score: {submit_resp.get('score', 100)}/100")
            return True
        else:
            print(f"❌ Challenge submission failed (Status {submit_status}): {submit_resp}")
            return False

    def register(self, name: str, bio: Optional[str] = None) -> bool:
        """Register a new hedge fund agent on Headline Arena and persist credentials."""
        bio = bio or (
            "Multi-Agent AI Hedge Fund Committee: 15 legendary personas (Buffett, Druckenmiller, "
            "Burry, Wood, Ackman, Graham, Lynch, Fisher, Pelosi, etc.) analyzing macro futures "
            "and equities via multi-round debates."
        )
        payload = {
            "name": name,
            "type": "trading",
            "bio": bio,
            "languages": ["en", "zh-TW"],
            "model_provider": "Groq",
            "model_name": "openai/gpt-oss-20b",
            "model_capability_tag": "reasoning",
            "hosting_mode": "cloud",
            "policy_profile": "standard",
            "disclosure_level": "public",
            "default_spaces": ["finance", "policy"],
            "auth_method": "client_credentials",
            "requested_scopes": ALL_SCOPES,
        }

        print(f"📡 Registering agent '{name}' on Headline Arena ({self.origin})...")
        candidate_name = name
        status, resp = 0, {}
        for attempt in range(5):
            payload["name"] = candidate_name
            status, resp = self._request("POST", "/agent/registry/register", payload)
            if status != 409:
                break
            candidate_name = f"{name}-{attempt + 2}"
            print(f"⚠️ Name taken, retrying as '{candidate_name}'...")

        if status not in (200, 201):
            print(f"❌ Registration failed ({status}): {resp.get('detail', resp)}")
            return False

        agent_id = resp["agent_id"]
        client_secret = resp.get("client_secret")
        claim_url = resp.get("claim_url")
        pairing_code = resp.get("pairing_code")
        challenge_id = resp.get("challenge_id")
        challenge_prompt = resp.get("challenge_prompt")
        submit_url = resp.get("submit_url")

        creds = {
            "agent_id": agent_id,
            "agent_name": candidate_name,
            "client_secret": client_secret,
            "claim_url": claim_url,
            "pairing_code": pairing_code,
            "status": "pending_challenge" if challenge_id else "active",
            "token": None,
        }

        self.save_credentials(creds, set_default=True)
        print(f"✅ Credentials securely stored for agent '{candidate_name}' ({agent_id}) in {CRED_FILE}")

        # Solve challenge if required
        if challenge_id and submit_url and challenge_prompt:
            success = self.solve_onboarding_challenge(challenge_prompt, submit_url)
            if success:
                creds["status"] = "active"
                creds["challenge"] = None
                self.save_credentials(creds)
                # Fetch first access token
                self.get_token(force=True)
                return True
            return False

        if claim_url:
            print(f"🔗 Claim Link for Operator: {claim_url} (Pairing Code: {pairing_code})")
        return True

    def get_open_challenges(self, status: str = "open", asset_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Fetch active/open financial challenges from Headline Arena."""
        # Try authenticated endpoint first if creds present
        creds = self.load_credentials()
        items = []
        if creds.get("agent_id") and creds.get("client_secret"):
            s, r = self.authed_request("GET", "/eval/challenges/active")
            if s == 200:
                raw_items = r.get("items", r.get("challenges", []))
                items = [
                    dict(i["challenge"], context=i.get("context")) if "challenge" in i else i
                    for i in raw_items
                ]

        if not items:
            # Fall back to public challenge list
            s, r = self._request("GET", f"/eval/challenges?status={status}")
            if s == 200:
                items = r.get("items", r.get("challenges", []))

        # Filter by asset if specified
        if asset_filter:
            target_assets = {a.upper() for a in asset_filter}
            items = [c for c in items if c.get("asset", "").upper() in target_assets]

        return items

    def predict(
        self,
        challenge_id: str,
        direction: str,
        confidence: float,
        reasoning: str,
        is_revision: bool = False
    ) -> Tuple[bool, Dict[str, Any]]:
        """Submit forecast to Headline Arena."""
        body = {
            "direction": direction,
            "confidence": round(confidence, 4),
            "reasoning": reasoning,
            "is_revision": is_revision,
        }
        status, resp = self.authed_request("POST", f"/eval/challenges/{challenge_id}/predict", body)
        if status in (200, 201):
            return True, resp
        return False, resp

    def get_scorecard(self) -> Dict[str, Any]:
        """Fetch current agent's public scorecard."""
        creds = self.load_credentials()
        agent_id = creds.get("agent_id")
        if not agent_id:
            return {"error": "No agent credentials found."}
        status, resp = self._request("GET", f"/eval/agents/{agent_id}/scorecard")
        if status == 200:
            return resp
        return {"error": f"Failed to retrieve scorecard ({status}): {resp}"}


class HedgeFundAPIClient:
    """Client communicating with the AI Hedge Fund API (https://hedgeapi.afpicapital.com)."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or os.environ.get("HEDGE_FUND_URL", DEFAULT_HEDGE_FUND_URL)).rstrip("/")

    def analyze(
        self,
        ticker: str,
        analysts: Optional[List[str]] = None,
        enable_round_table: bool = True,
        round_table_rounds: int = 1
    ) -> Dict[str, Any]:
        """Trigger multi-agent analysis for a specific equity or ETF ticker."""
        if not analysts:
            # Default macro-oriented committee
            analysts = [
                "stanley_druckenmiller",
                "warren_buffett",
                "michael_burry",
                "cathie_wood",
                "technical_analyst",
                "valuation_analyst",
                "sentiment_analyst"
            ]

        payload = {
            "tickers": ticker,
            "analysts": analysts,
            "enableRoundTable": enable_round_table,
            "roundTableRounds": round_table_rounds,
        }

        url = f"{self.base_url}/api/analysis"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "HeadlineArena-Sync/2.3.0"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                text = resp.read().decode("utf-8")
                return json.loads(text)
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8")
            try:
                err_json = json.loads(text)
            except Exception:
                err_json = {"detail": text or str(e)}
            return {"error": f"HTTP {e.code}", "detail": err_json}
        except Exception as exc:
            return {"error": "ConnectionError", "detail": str(exc)}


def convert_hedge_decision_to_forecast(
    hedge_result: Dict[str, Any],
    ticker: str,
    asset: str,
    persona: str = "committee"
) -> Tuple[str, float, str]:
    """
    Extract direction ('bullish' | 'bearish' | 'neutral'), confidence (0.1 ~ 0.95),
    and synthesis reasoning from the hedge fund response.
    """
    decisions = hedge_result.get("decisions", {})
    ticker_decision = decisions.get(ticker, {})
    analyst_signals = hedge_result.get("analyst_signals", {})

    # Check if a specific persona was requested
    if persona != "committee" and persona in analyst_signals:
        persona_data = analyst_signals[persona].get(ticker, {})
        raw_sig = str(persona_data.get("signal", "neutral")).lower()
        conf = float(persona_data.get("confidence", 0.65))
        reason = str(persona_data.get("reasoning", "")).strip()
        direction = "bullish" if raw_sig in ("bullish", "buy") else ("bearish" if raw_sig in ("bearish", "sell", "short") else "neutral")
        full_reason = f"[{persona.replace('_', ' ').title()} Macro Thesis] {reason}"
        return direction, min(max(conf, 0.1), 0.95), full_reason[:480]

    # Otherwise: Consolidated Committee Decision
    action = str(ticker_decision.get("action", "hold")).lower()
    conf = float(ticker_decision.get("confidence", 0.70))
    if conf > 1.0:
        conf = conf / 100.0  # normalize percentage if returned as 0-100

    if action in ("buy", "long"):
        direction = "bullish"
    elif action in ("sell", "short"):
        direction = "bearish"
    else:
        direction = "neutral"

    # Assemble reasoning from Druckenmiller, Buffett, Burry, and Committee Debate
    reason_parts = []
    if "stanley_druckenmiller" in analyst_signals and ticker in analyst_signals["stanley_druckenmiller"]:
        druck_reason = analyst_signals["stanley_druckenmiller"][ticker].get("reasoning", "")
        if druck_reason:
            reason_parts.append(f"Druckenmiller Inflection: {druck_reason[:120]}")

    if ticker_decision.get("reasoning"):
        reason_parts.append(f"Committee Risk-Adjusted Allocation: {ticker_decision['reasoning'][:160]}")

    round_table_summary = hedge_result.get("round_table_summary", "")
    if round_table_summary:
        reason_parts.append(f"Debate: {round_table_summary[:120]}")

    combined_reasoning = " | ".join(reason_parts) if reason_parts else f"AI Hedge Fund Committee evaluated {asset} ({ticker}) as {direction}."
    return direction, min(max(conf, 0.1), 0.95), combined_reasoning[:480]


def main():
    parser = argparse.ArgumentParser(
        description="Headline Arena Sync Adapter for AI Hedge Fund API (15 Personas & Round Table)"
    )
    parser.add_argument("--register", action="store_true", help="Register hedge fund agent with Headline Arena")
    parser.add_argument("--agent-name", default="ai-hedge-fund-macro", help="Agent name to register or use")
    parser.add_argument("--bio", default=None, help="Agent biography for Headline Arena")
    parser.add_argument("--dry-run", action="store_true", help="Analyze active challenges without submitting predictions")
    parser.add_argument("--submit", action="store_true", help="Submit actual predictions to Headline Arena")
    parser.add_argument("--persona", default="committee", help="Forecast persona ('committee', 'stanley_druckenmiller', 'michael_burry', 'warren_buffett', etc.)")
    parser.add_argument("--asset", default=None, help="Comma-separated assets to filter (e.g. 'ES,GC,CL,BTC')")
    parser.add_argument("--limit", type=int, default=5, help="Maximum number of challenges to process (default: 5)")
    parser.add_argument("--status", action="store_true", help="Check current agent status, credentials, and scorecard")
    parser.add_argument("--ha-url", default=None, help=f"Headline Arena base URL (default: {DEFAULT_HA_ORIGIN})")
    parser.add_argument("--hedge-fund-url", default=None, help=f"AI Hedge Fund API URL (default: {DEFAULT_HEDGE_FUND_URL})")

    args = parser.parse_args()

    ha_client = HeadlineArenaClient(origin=args.ha_url)
    hedge_client = HedgeFundAPIClient(base_url=args.hedge_fund_url)

    print("=" * 72)
    print("🏛️  AI Hedge Fund <-> Headline Arena Autonomous Bridge")
    print(f"🌐 Headline Arena: {ha_client.origin}")
    print(f"🏦 Hedge Fund API: {hedge_client.base_url}")
    print("=" * 72)

    # 1. Status mode
    if args.status:
        creds = ha_client.load_credentials()
        if not creds:
            print("⚠️ No credentials found in ~/.headlinearena/credentials.json or environment.")
            print("Run with --register to create an agent.")
            return

        print(f"🤖 Registered Agent: {creds.get('agent_name')} ({creds.get('agent_id')})")
        print(f"📌 Status: {creds.get('status')}")
        if creds.get("claim_url"):
            print(f"🔗 Claim Link: {creds.get('claim_url')}")
            print(f"🔑 Pairing Code: {creds.get('pairing_code')}")

        scorecard = ha_client.get_scorecard()
        print("\n📊 Headline Arena Scorecard:")
        print(json.dumps(scorecard, indent=2, ensure_ascii=False))
        return

    # 2. Registration mode
    if args.register:
        success = ha_client.register(name=args.agent_name, bio=args.bio)
        if success:
            print(f"\n🎉 Successfully onboarded '{args.agent_name}' to Headline Arena!")
        return

    # Check for credentials before running forecast
    creds = ha_client.load_credentials()
    if not creds and args.submit:
        print("❌ No agent credentials found. Please run with --register first, or use --dry-run.")
        sys.exit(1)

    # 3. Fetch challenges
    asset_filter = [a.strip().upper() for a in args.asset.split(",")] if args.asset else None
    print(f"\n🔍 Fetching active challenges from Headline Arena (Filter: {asset_filter or 'All'})...")
    challenges = ha_client.get_open_challenges(asset_filter=asset_filter)

    if not challenges:
        print("ℹ️ No open challenges matching the criteria right now.")
        return

    print(f"🎯 Found {len(challenges)} open challenges. Processing up to {args.limit}...")

    processed = 0
    for challenge in challenges[:args.limit]:
        c_id = challenge.get("id")
        asset = challenge.get("asset", "").upper()
        question = challenge.get("question", "")
        deadline = challenge.get("deadline", "")
        open_price = challenge.get("open_price")

        mapped_ticker = ASSET_MAP.get(asset, asset)
        print("\n" + "-" * 72)
        print(f"📌 Challenge ID: {c_id}")
        print(f"📊 Asset: {asset} (Mapped Ticker: {mapped_ticker})")
        print(f"❓ Question: {question}")
        print(f"⏳ Deadline: {deadline} | Open Price: {open_price}")

        # Call AI Hedge Fund API
        print(f"🚀 Running AI Hedge Fund Committee Analysis on {mapped_ticker}...")
        t0 = time.time()
        hedge_result = hedge_client.analyze(
            ticker=mapped_ticker,
            analysts=[
                "stanley_druckenmiller",
                "warren_buffett",
                "michael_burry",
                "technical_analyst",
                "valuation_analyst",
            ],
            enable_round_table=True,
            round_table_rounds=1
        )
        elapsed = time.time() - t0

        if "error" in hedge_result:
            print(f"❌ Analysis failed for {mapped_ticker}: {hedge_result.get('error')} - {hedge_result.get('detail')}")
            continue

        direction, confidence, reasoning = convert_hedge_decision_to_forecast(
            hedge_result,
            ticker=mapped_ticker,
            asset=asset,
            persona=args.persona
        )

        print(f"⏱️ Analysis completed in {elapsed:.2f}s")
        print(f"🔮 Persona: {args.persona}")
        print(f"📈 Forecast Direction: {direction.upper()}")
        print(f"🎯 Confidence: {confidence:.2%}")
        print(f"📝 Reasoning: {reasoning}")

        if args.dry_run or not args.submit:
            print("🧪 [DRY-RUN] Prediction prepared successfully (use --submit to broadcast).")
        elif args.submit:
            print(f"📤 Submitting forecast to Headline Arena challenge {c_id}...")
            ok, resp = ha_client.predict(
                challenge_id=c_id,
                direction=direction,
                confidence=confidence,
                reasoning=reasoning
            )
            if ok:
                print(f"✅ Prediction SUBMITTED! Status: {resp.get('status', 'accepted')}")
                if "brier_score" in resp:
                    print(f"⭐ Current Brier Score: {resp.get('brier_score')}")
            else:
                print(f"❌ Failed to submit prediction: {resp}")

        processed += 1

    print("\n" + "=" * 72)
    print(f"✨ Finished processing {processed} challenges.")
    print("=" * 72)


if __name__ == "__main__":
    main()
