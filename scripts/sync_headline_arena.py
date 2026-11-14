#!/usr/bin/env python3
"""Standard-library CLI for the ES/GC committee probability pilot.

The backend performs challenge-conditioned synthesis via call_llm(). This CLI
fetches challenge-bound evidence, checks claim status before submission, records
receipts, and compares settled forecasts with simple benchmarks.

  python3 scripts/sync_headline_arena.py --status
  python3 scripts/sync_headline_arena.py --dry-run --asset ES,GC
  python3 scripts/sync_headline_arena.py --submit --asset ES
  python3 scripts/sync_headline_arena.py --evaluate

Set HEDGE_FUND_URL to a backend supporting forecastChallenge. --dry-run invokes
that backend and can incur inference cost, but never submits Arena predictions.
"""

import os
import sys
import json
import time
import uuid
import re
import argparse
import sqlite3
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from headline_contract import (
    ASSET_POLICIES, analyst_evidence, utc_now, validate_challenge,
    validate_context, validate_probabilities,
)

# Version & Headers
CLI_VERSION = "3.0.0"
DEFAULT_HA_ORIGIN = "https://headlinearena.com"
DEFAULT_HEDGE_FUND_URL = "https://hedgeapi.afpicapital.com"

# Macro Asset Mapping: Headline Arena Asset Code -> AI Hedge Fund Ticker
ASSET_MAP = {asset: policy["ticker"] for asset, policy in ASSET_POLICIES.items()}

ALL_SCOPES = ["prediction:submit", "challenge:read", "profile:read:self"]


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
CRED_DIR = Path(os.getenv("HA_HOME", str(Path.home() / ".headlinearena")))
CRED_FILE = CRED_DIR / "credentials.json"


class PredictionNotSent(ValueError):
    """A prediction POST was never sent, or only received an explicit 401."""


class HeadlineArenaClient:
    """Zero-dependency client for Headline Arena agent API."""

    def __init__(self, origin: Optional[str] = None):
        self.origin = (origin or os.environ.get("HA_BASE_URL", DEFAULT_HA_ORIGIN)).rstrip("/")
        if self.origin.endswith("/api/v1"):
            self.origin = self.origin[:-len("/api/v1")]
        self.api_base = f"{self.origin}/api/v1"
        self._token_cache: Optional[Dict[str, Any]] = None
        self.auth_status: Dict[str, Any] = {}

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
            except Exception as exc:
                raise ValueError("Existing credential store cannot be read; recover it before registering or submitting") from exc
        return {}

    def save_credentials(self, entry: Dict[str, Any], set_default: bool = True):
        """Serialize read-modify-write and atomically replace private credentials."""
        import tempfile
        CRED_DIR.mkdir(parents=True, exist_ok=True)
        CRED_DIR.chmod(0o700)
        agent_id = entry.get("agent_id")
        if not agent_id:
            return
        lock = sqlite3.connect(CRED_DIR / "credential_lock.sqlite3", timeout=30)
        temporary_path = None
        try:
            lock.execute("BEGIN IMMEDIATE")
            # A malformed existing store must never be silently overwritten.
            store = json.loads(CRED_FILE.read_text(encoding="utf-8")) if CRED_FILE.exists() else {}
            org = store.setdefault(self.origin, {})
            agents = org.setdefault("_agents", {})
            agents[agent_id] = dict(agents.get(agent_id, {}), **entry)
            if set_default or org.get("_default_agent") is None:
                org["_default_agent"] = agent_id
            fd, temporary_path = tempfile.mkstemp(prefix="credentials-", dir=CRED_DIR)
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(store, output, indent=2, ensure_ascii=False)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_path, CRED_FILE)
            lock.commit()
        finally:
            lock.close()
            if temporary_path and Path(temporary_path).exists():
                Path(temporary_path).unlink()

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
            self.auth_status = creds.get("auth_status", {})
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
            self.auth_status = {key: resp.get(key) for key in (
                "agent_status", "claim_pending", "provisional_until", "claim_note",
            )}
            # Patch only refreshed fields; creds may predate another process's
            # updated claim details or credentials.
            self.save_credentials({"agent_id": agent_id, "token": token_entry,
                                   "auth_status": self.auth_status}, set_default=False)
            return access_token
        return None

    def authed_request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None, preflight=None) -> Tuple[int, Dict[str, Any]]:
        """Authenticated request with automatic single retry on 401."""
        creds = self.load_credentials()
        agent_id = creds.get("agent_id")
        token = self.get_token()
        if not token:
            if method == "POST" and path.endswith("/predict"):
                raise PredictionNotSent("No token available before prediction send")
            return 401, {"detail": "No access token; check existing credentials and claim status before registering again."}

        def check_before_send():
            try:
                if method == "POST" and path.endswith("/predict"):
                    self.assert_claimed_status()
                if preflight is not None:
                    preflight()
            except (ValueError, RuntimeError) as exc:
                raise PredictionNotSent(str(exc)) from None

        check_before_send()
        status, resp = self._request(method, path, body, token=token, agent_id=agent_id)
        if status == 401:
            token = self.get_token(force=True)
            if not token:
                if method == "POST" and path.endswith("/predict"):
                    raise PredictionNotSent("Token refresh failed after explicit 401 rejection")
                return 401, {"detail": "Token refresh failed"}
            check_before_send()
            status, resp = self._request(method, path, body, token=token, agent_id=agent_id)
        if status == 401 and method == "POST" and path.endswith("/predict"):
            raise PredictionNotSent("Prediction was explicitly rejected with HTTP 401")
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
            creds = {"agent_id": self.load_credentials().get("agent_id")}
            for key in ("claim_url", "pairing_code", "provisional_until", "provisional_prediction_limit"):
                if key in submit_resp:
                    creds[key] = submit_resp[key]
            self.save_credentials(creds, set_default=False)
            print("Onboarding passed. Private claim details saved in the credential file; human claim is still required.")
            return True
        else:
            print(f"Challenge submission failed (HTTP {submit_status}); private response omitted.")
            return False

    def register(self, name: str, bio: Optional[str] = None) -> bool:
        """Register a new hedge fund agent on Headline Arena and persist credentials."""
        if self.load_credentials():
            raise ValueError("Existing agent found; claim it instead of registering again")
        bio = bio or "AI Hedge Fund committee: challenge-conditioned ES/GC probability pilot."
        payload = {
            "name": name,
            "type": "trading",
            "bio": bio,
            "languages": ["en", "zh-TW"],
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
        status, resp = self._request("POST", "/agent/registry/register", payload)
        if status not in (200, 201):
            print(f"Registration failed (HTTP {status}); check the existing agent before retrying.")
            return False

        if not resp.get("agent_id") or not resp.get("client_secret"):
            raise ValueError("Registration response missing credentials; do not automatically register again")
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
                self.save_credentials({"agent_id": agent_id, "status": "active_provisional",
                                       "challenge": None}, set_default=False)
                # Fetch first access token
                self.get_token(force=True)
                return True
            return False

        if claim_url:
            print("Private claim details saved in the credential file; complete the human claim before --submit.")
        return True

    def get_open_challenges(self, status="open", asset_filter=None):
        """An authenticated empty list is authoritative; never broaden subscriptions."""
        creds = self.load_credentials()
        authenticated = bool(creds.get("agent_id") and creds.get("client_secret"))
        if authenticated:
            status_code, response = self.authed_request("GET", "/eval/challenges/active")
        else:
            status_code, response = self._request("GET", f"/eval/challenges?status={status}")
        if status_code != 200:
            raise ValueError(f"Challenge discovery failed (HTTP {status_code})")
        raw = response.get("items", response.get("challenges", []))
        items = [dict(item["challenge"], context=item.get("context")) if "challenge" in item else item for item in raw]
        targets = {str(asset).strip().upper() for asset in asset_filter} if asset_filter else None
        for item in items:
            item["asset"] = str(item.get("asset", "")).strip().upper()
        return [c for c in items if targets is None or c.get("asset") in targets]

    def challenge_context(self, challenge_id):
        # Fixed same-origin route avoids forwarding credentials to advertised URLs.
        path = f"/eval/challenges/{urllib.parse.quote(str(challenge_id), safe='')}/context"
        if self.load_credentials():
            status, result = self.authed_request("GET", path)
        else:
            status, result = self._request("GET", path)
        if status != 200:
            raise ValueError(f"Challenge context unavailable (HTTP {status})")
        return result

    def require_claimed(self):
        # Refresh the token so cached local registration status is never trusted.
        if not self.get_token(force=True):
            raise ValueError("Cannot authenticate existing agent; check claim status, do not register again")
        self.assert_claimed_status()

    def assert_claimed_status(self):
        if self.auth_status.get("agent_status") is None or self.auth_status.get("claim_pending") is None:
            raise ValueError("Token response is missing claim status fields; cannot verify the existing agent")
        if self.auth_status.get("agent_status") != "active" or self.auth_status.get("claim_pending") is not False:
            raise ValueError("Agent claim is pending or unknown; human claim is required before --submit")

    def predict(self, challenge_id, forecast, preflight=None):
        probabilities = validate_probabilities(forecast.get("probabilities"))
        body = {"probabilities": probabilities, "reasoning": forecast["reasoning"],
                "prompt_hash": forecast["prompt_hash"]}
        # Stable across ambiguous transport retries; local reservations still
        # require operator reconciliation rather than automatic replay.
        import hashlib
        body["idempotency_key"] = hashlib.sha256(
            (str(challenge_id) + ":" + forecast["prompt_hash"]).encode()
        ).hexdigest()
        attribution = forecast.get("model_attribution") or {}
        if attribution.get("model_provider") and attribution.get("model_name"):
            body.update({key: attribution[key] for key in ("model_provider", "model_name")})
        status, response = self.authed_request("POST", f"/eval/challenges/{urllib.parse.quote(str(challenge_id), safe='')}/predict", body, preflight=preflight)
        return status, response

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

    def analyze(self, ticker, analysts, challenge, context):
        """Forecast synthesis stays on the backend; the CLI needs no LLM libraries."""
        payload = {
            "tickers": ticker, "selectedAnalysts": analysts,
            "enableRoundTable": True, "roundTableRounds": 1,
            "forecastChallenge": challenge, "marketContext": context,
        }
        req = urllib.request.Request(
            f"{self.base_url}/api/analysis", data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as response:
                result = json.load(response)
        except Exception as exc:
            raise ValueError("Backend analysis unavailable; no prediction prepared") from exc
        if not isinstance(result, dict) or not isinstance(result.get("forecast"), dict):
            raise ValueError("Backend did not return a challenge-conditioned forecast")
        forecast = result["forecast"]
        if forecast.get("challenge_id") != challenge["id"]:
            raise ValueError("Backend returned a different challenge")
        validate_probabilities(forecast.get("probabilities"))
        reasoning = forecast.get("reasoning")
        if not isinstance(reasoning, str) or not 20 <= len(reasoning) <= 4000:
            raise ValueError("Invalid forecast rationale")
        if not re.fullmatch(r"[0-9a-f]{64}", str(forecast.get("prompt_hash", ""))):
            raise ValueError("Missing prompt hash")
        return forecast


def convert_hedge_decision_to_forecast(hedge_result, ticker, asset, persona="committee"):
    """Legacy diagnostic only: never used to construct Arena submissions."""
    if persona == "committee":
        rt = (hedge_result.get("round_table") or {}).get(ticker)
        signals = analyst_evidence({"analyst_signals": {"round_table_agent": {ticker: rt}}}, ticker, ["round_table"])
        signal = signals["round_table"]
    else:
        normalized = persona[:-6] if persona.endswith("_agent") and persona != "wsb_agent" else persona
        aliases = {"fundamentals": "fundamentals_analyst", "sentiment": "sentiment_analyst", "valuation": "valuation_analyst"}
        normalized = aliases.get(normalized, normalized)
        signal = analyst_evidence(hedge_result, ticker, [normalized])[normalized]
    return signal["signal"], signal["confidence"], signal["reasoning"]


class ForecastJournal:
    """Persist evidence and reserve outbound attempts atomically across processes."""

    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30)
        self.db.execute("CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, origin TEXT, agent TEXT, challenge TEXT, state TEXT, payload TEXT, receipt TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS attempts (origin TEXT, agent TEXT, challenge TEXT, run_id INTEGER, PRIMARY KEY(origin, agent, challenge))")
        self.db.commit()

    def record(self, origin, agent, challenge, state, payload):
        with self.db:
            cursor = self.db.execute("INSERT INTO runs(origin,agent,challenge,state,payload) VALUES(?,?,?,?,?)", (origin, agent, challenge, state, json.dumps(payload, ensure_ascii=False, allow_nan=False)))
        return cursor.lastrowid

    def attempted(self, origin, agent, challenge):
        return self.db.execute("SELECT 1 FROM attempts WHERE origin=? AND agent=? AND challenge=?", (origin, agent, challenge)).fetchone() is not None

    def reserve(self, origin, agent, challenge, run_id):
        try:
            with self.db:
                self.db.execute("INSERT INTO attempts VALUES(?,?,?,?)", (origin, agent, challenge, run_id))
                self.db.execute("UPDATE runs SET state='pending' WHERE id=?", (run_id,))
        except sqlite3.IntegrityError:
            raise ValueError("An outbound attempt already exists; inspect its receipt before retrying") from None

    def finish(self, run_id, status, receipt):
        eligible = status in (200, 201) and receipt.get("counts_for_score") is True
        rejected = 400 <= status < 500 and status not in (408, 409)
        state = ("scored_eligible" if eligible else "rejected" if rejected
                 else "remote_conflict" if status == 409
                 else "paper_only" if status in (200, 201) and receipt.get("counts_for_score") is False
                 else "unconfirmed")
        # Store only forecast receipt fields, never auth or claim material.
        safe = {key: receipt[key] for key in ("counts_for_score", "prediction_id", "id", "status", "brier_score", "model_attribution_source") if key in receipt}
        safe["http_status"] = status
        with self.db:
            self.db.execute("UPDATE runs SET state=?,receipt=? WHERE id=?", (state, json.dumps(safe), run_id))
            if rejected:
                self.db.execute("DELETE FROM attempts WHERE run_id=?", (run_id,))
        return state

    def release_unsent(self, run_id):
        with self.db:
            self.db.execute("DELETE FROM attempts WHERE run_id=?", (run_id,))
            self.db.execute("UPDATE runs SET state='not_sent' WHERE id=?", (run_id,))

    def evaluate(self, client):
        agent_id = client.load_credentials().get("agent_id")
        if not agent_id:
            raise ValueError("Select the existing agent credentials before evaluating its forecasts")
        rows = self.db.execute("SELECT id,challenge,payload FROM runs WHERE origin=? AND agent=? AND state='scored_eligible'", (client.origin, agent_id)).fetchall()
        scores, failures = [], []
        for run_id, challenge_id, payload in rows:
            path = f"/eval/challenges/{urllib.parse.quote(challenge_id, safe='')}"
            status, result = client.authed_request("GET", path)
            if status != 200:
                failures.append({"challenge_id": challenge_id, "http_status": status})
                continue
            challenge = result.get("challenge", result)
            if challenge.get("status") != "resolved" or challenge.get("result") not in {"bearish", "neutral", "bullish"}:
                continue
            data = json.loads(payload)
            if not isinstance(data.get("benchmarks"), dict) or not isinstance(data.get("forecast"), dict):
                failures.append({"challenge_id": challenge_id, "error": "Invalid stored forecast/benchmarks"})
                continue
            vectors = dict(data["benchmarks"], committee=data["forecast"]["probabilities"])
            scores.append({"run_id": run_id, "challenge_id": challenge_id, "brier": {name: brier_score(p, challenge["result"]) for name, p in vectors.items()}})
        return {"settled_comparable_forecasts": len(scores), "rows": scores, "fetch_or_data_failures": failures,
                "mean_brier": {name: sum(row["brier"][name] for row in scores) / len(scores) for name in scores[0]["brier"]} if scores else {}}


def brier_score(probabilities, outcome):
    p = validate_probabilities(probabilities)
    return sum((v - int(k == outcome)) ** 2 for k, v in p.items())


def benchmark_vectors(challenge, context):
    price = context["quote"]["price"]
    baseline = challenge["open_price"]
    change = (price / baseline - 1) * 100
    import math
    threshold = challenge["dead_zone_pct"]
    on_boundary = math.isclose(abs(change), threshold, rel_tol=0, abs_tol=1e-10)
    direction = "neutral" if on_boundary else "bullish" if change > threshold else "bearish" if change < -threshold else "neutral"
    return {"uniform": {k: 1 / 3 for k in ("bearish", "neutral", "bullish")},
            "always_neutral": {"bearish": 0.0, "neutral": 1.0, "bullish": 0.0},
            "momentum": {k: float(k == direction) for k in ("bearish", "neutral", "bullish")}}


def process_challenge(ha_client, hedge_client, journal, challenge, submit=False):
    policy = validate_challenge(challenge)
    agent = ha_client.load_credentials().get("agent_id", "anonymous-dry-run")
    if submit and journal.attempted(ha_client.origin, agent, challenge["id"]):
        raise ValueError("Already attempted; skipping duplicate analysis and submission")
    # Always fetch the bound context, even when discovery included asset context.
    context = ha_client.challenge_context(challenge["id"])
    validate_context(context, challenge)
    benchmarks = benchmark_vectors(challenge, context)
    forecast = hedge_client.analyze(policy["ticker"], policy["analysts"], challenge, context)
    validate_challenge(challenge)
    validate_context(context, challenge)
    run_id = journal.record(ha_client.origin, agent, challenge["id"], "dry_run" if not submit else "prepared", {
        "observed_at": utc_now().isoformat(), "challenge": challenge, "context": context,
        "selectedAnalysts": policy["analysts"], "forecast": forecast, "benchmarks": benchmarks,
    })
    if not submit:
        return "dry_run"
    ha_client.require_claimed()
    validate_challenge(challenge)  # Token refresh may have taken time too.
    validate_context(context, challenge)
    journal.reserve(ha_client.origin, agent, challenge["id"], run_id)
    # A crash/timeout after reservation stays pending/unconfirmed and is never
    # automatically replayed: the remote side may already have accepted it.
    def preflight():
        validate_challenge(challenge)
        validate_context(context, challenge)
    try:
        status, receipt = ha_client.predict(challenge["id"], forecast, preflight=preflight)
    except PredictionNotSent:
        journal.release_unsent(run_id)
        raise
    return journal.finish(run_id, status, receipt)


def main():
    parser = argparse.ArgumentParser(description="Headline Arena committee probability pilot (ES/GC)")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--agent-name", default="ai-hedge-fund-committee")
    parser.add_argument("--bio", default=None)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--submit", action="store_true")
    parser.add_argument("--persona", choices=["committee"], default="committee")
    parser.add_argument("--asset", default="ES,GC")
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--evaluate", action="store_true", help="Compare stored eligible forecasts with resolved outcomes")
    parser.add_argument("--journal", default=None, help="SQLite journal (default: HA_HOME/forecast_runs.sqlite3)")
    parser.add_argument("--ha-url", default=None)
    parser.add_argument("--hedge-fund-url", default=None)
    args = parser.parse_args()
    ha_client = HeadlineArenaClient(origin=args.ha_url)
    hedge_client = HedgeFundAPIClient(base_url=args.hedge_fund_url)
    if args.status:
        token = ha_client.get_token(force=True)
        # Never print claim_url, pairing_code, tokens, or arbitrary auth responses.
        print(json.dumps({"authenticated": bool(token), **{k: ha_client.auth_status.get(k) for k in ("agent_status", "claim_pending", "provisional_until")}}, indent=2))
        return
    if args.register:
        if ha_client.load_credentials():
            parser.error("Existing agent credentials found; use --status and claim that agent")
        ha_client.register(args.agent_name, args.bio)
        return
    journal = ForecastJournal(args.journal or CRED_DIR / "forecast_runs.sqlite3")
    if args.evaluate:
        print(json.dumps(journal.evaluate(ha_client), indent=2))
        return
    if args.submit:
        ha_client.require_claimed()
    assets = [a.strip().upper() for a in args.asset.split(",")]
    if any(asset not in ASSET_POLICIES for asset in assets):
        parser.error("Only ES and GC are enabled in this pilot")
    challenges = ha_client.get_open_challenges(asset_filter=assets)
    print(f"Found {len(challenges)} open pilot challenges")
    processed = 0
    for challenge in challenges:
        if processed >= max(0, args.limit):
            break
        try:
            state = process_challenge(ha_client, hedge_client, journal, challenge, submit=args.submit)
            processed += 1
            print(f"{challenge.get('id')}: {state}")
        except (ValueError, RuntimeError) as exc:
            # Local validation messages only; HTTP response bodies are not printed.
            journal.record(ha_client.origin, ha_client.load_credentials().get("agent_id", "anonymous-dry-run"),
                           str(challenge.get("id", "unknown")), "skipped",
                           {"observed_at": utc_now().isoformat(), "reason": str(exc)})
            print(f"{challenge.get('id')}: skipped ({exc})")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, sqlite3.Error, OSError) as exc:
        print(f"Stopped: {exc}", file=sys.stderr)
        sys.exit(1)
