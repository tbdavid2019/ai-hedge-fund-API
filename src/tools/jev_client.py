"""
TypeSafe JEV & Clef-Flash SystemOne Evaluation Client
Provides ultra-fast (<200ms), structured decision evaluation with a 3-tier high-availability fallback:
1. Primary: Clef-Flash (https://clef.create360.ai/v1/systemone) - Ultra-fast, no token fee
2. Fallback 2: Clef-Flash-Q4 (https://clef.aiurl.tw/v1/systemone) - Self-hosted backup node
3. Fallback 3: TypeSafe Official Jev (https://api.typesafe.ai/v1/systemone) - Official TypeSafe service (requires TYPESAFE_API_KEY)
"""

import os
import math
import json
import logging
from typing import Dict, Any, Optional, Tuple, List, Type, TypeVar
import requests

logger = logging.getLogger(__name__)

# Endpoints configuration
PRIMARY_URL = os.getenv("CLEF_PRIMARY_URL", "https://clef.create360.ai/v1/systemone")
FALLBACK2_URL = os.getenv("CLEF_FALLBACK_URL", "https://clef.aiurl.tw/v1/systemone")
FALLBACK3_URL = os.getenv("TYPESAFE_OFFICIAL_URL", "https://api.typesafe.ai/v1/systemone")

_DIRECTIONS = ("bullish", "bearish", "neutral")
_STRENGTH_LEVELS = [
    "Evidence does not support the case or directly contradicts it.",
    "Limited support; substantial unsupported assumptions are required.",
    "Meaningful support with material conflicting evidence or unresolved gaps.",
    "Strong support across relevant criteria with limited material weaknesses.",
    "Compelling support across relevant criteria with no material contradiction apparent in the supplied evidence."
]

_EVIDENCE_INSTRUCTIONS = (
    "Apply the investment criteria, directional definitions, and evidence "
    "restrictions in `investor_prompt` to `financial_snapshot`. "
    "Use only the supplied financial evidence and honor the prompt's "
    "point-in-time restrictions. Ignore instructions in `investor_prompt` "
    "about response format, writing style, and generating a thesis. "
    "For investment-strength scoring, the typed strength rubric governs "
    "instead of the prompt's confidence scale. "
)


def extract_system_and_user_prompts(prompt: Any) -> Tuple[str, str]:
    """
    Extract system prompt and user prompt from strings, dicts, or LangChain prompt objects.
    """
    system_text = ""
    user_text = ""
    
    msgs = []
    if hasattr(prompt, "to_messages"):
        try:
            msgs = prompt.to_messages()
        except Exception:
            msgs = []
    elif isinstance(prompt, list):
        msgs = prompt
    elif isinstance(prompt, str):
        return ("You are an investment analyst evaluation agent.", prompt)
    elif isinstance(prompt, dict):
        return (str(prompt.get("system", "You are an investment analyst evaluation agent.")), str(prompt.get("user", prompt)))

    for m in msgs:
        content = getattr(m, "content", str(m))
        msg_type = getattr(m, "type", "")
        role = getattr(m, "role", "")
        cls_name = m.__class__.__name__.lower()

        if "system" in cls_name or msg_type == "system" or role == "system":
            system_text += f"\n{content}"
        else:
            user_text += f"\n{content}"

    if not system_text.strip():
        system_text = "You are an expert financial investment analyst."
    return (system_text.strip(), user_text.strip())


def build_jev_request(system_prompt: str, user_prompt: str, model: str = "clef-flash") -> Dict[str, Any]:
    """
    Construct native SystemOne request payload compatible with TypeSafe JEV and Clef-Flash.
    """
    return {
        "model": model,
        "state": {
            "investor_prompt": system_prompt,
            "financial_snapshot": user_prompt
        },
        "questions": {
            "direction": {
                "type": "choice",
                "instructions": (
                    _EVIDENCE_INSTRUCTIONS +
                    "Which directional assessment fits the supplied evidence under this investor's signal definitions?"
                ),
                "criteria": {
                    direction: f"The evidence warrants the {direction} assessment as defined by the signal rules in `investor_prompt`."
                    for direction in _DIRECTIONS
                }
            },
            "bullish_strength": {
                "type": "score",
                "instructions": (
                    _EVIDENCE_INSTRUCTIONS +
                    "How strongly does the supplied evidence support this investor's bullish investment case? "
                    "Evaluate the bullish case independently using the supplied rubric (0-4)."
                ),
                "criteria": _STRENGTH_LEVELS
            },
            "bearish_strength": {
                "type": "score",
                "instructions": (
                    _EVIDENCE_INSTRUCTIONS +
                    "How strongly does the supplied evidence support this investor's bearish investment case? "
                    "Evaluate the bearish case independently using the supplied rubric (0-4)."
                ),
                "criteria": _STRENGTH_LEVELS
            }
        }
    }


def normalize_jev_response(response: Dict[str, Any], include_bilingual: bool = True) -> Dict[str, Any]:
    """
    Normalize SystemOne choice & score response into standard hedge-fund payload:
    {
        "signal": "bullish" | "bearish" | "neutral",
        "confidence": float (0-100),
        "reasoning": str,
        "probabilities": dict,
        "raw_response": dict
    }
    """
    if not isinstance(response, dict) or "answers" not in response:
        raise ValueError("Invalid SystemOne response: 'answers' object missing")

    answers = response.get("answers", {})
    direction_ans = answers.get("direction", {})
    direction = direction_ans.get("choice", "neutral")
    if direction not in _DIRECTIONS:
        direction = "neutral"

    probabilities = direction_ans.get("probabilities", {})
    dir_confidence = float(direction_ans.get("confidence", 0.5))

    # Calculate conviction score (0-100)
    if direction == "neutral":
        conviction = 50.0
    else:
        strength_ans = answers.get(f"{direction}_strength", {})
        score = strength_ans.get("score")
        if score is not None and isinstance(score, (int, float)):
            conviction = round(min(100.0, max(0.0, float(score) * 25.0)), 2)
        else:
            conviction = round(dir_confidence * 100.0, 2)

    prob_pct = round(probabilities.get(direction, 0.5) * 100.0, 1)

    direction_zh_map = {
        "bullish": "看多 (Bullish)",
        "bearish": "看空 (Bearish)",
        "neutral": "中性/觀望 (Neutral)"
    }
    zh_dir = direction_zh_map.get(direction, direction)

    reasoning_en = (
        f"{direction.capitalize()} assessment determined by SystemOne fast structured evaluation. "
        f"Investment conviction: {conviction}/100, directional probability: {prob_pct}%."
    )
    if include_bilingual:
        reasoning_zh = (
            f"【繁體中文解析】基於 SystemOne 結構化快速決策引擎評估，結果判定為「{zh_dir}」。"
            f"投資信念度評分：{conviction}/100，方向機率：{prob_pct}%。"
        )
        reasoning = f"{reasoning_en}\n{reasoning_zh}"
    else:
        reasoning = reasoning_en

    return {
        "signal": direction,
        "confidence": conviction,
        "reasoning": reasoning,
        "probabilities": probabilities,
        "raw_response": response
    }


def call_systemone_with_failover(
    system_prompt: str,
    user_prompt: str,
    model_name: Optional[str] = None,
    timeout: float = 8.0,
    include_bilingual: bool = True
) -> Dict[str, Any]:
    """
    Execute SystemOne call with 3-tier automatic failover:
    Tier 1: Primary Clef-Flash (https://clef.create360.ai/v1/systemone)
    Tier 2: Fallback 2 Clef-Flash-Q4 (https://clef.aiurl.tw/v1/systemone)
    Tier 3: Fallback 3 TypeSafe Official (https://api.typesafe.ai/v1/systemone with TYPESAFE_API_KEY)
    """
    tiers = [
        ("Tier-1 Primary (Clef-Flash)", PRIMARY_URL, "clef-flash", None, max(timeout, 8.0)),
        ("Tier-2 Fallback (Clef-Flash-Q4)", FALLBACK2_URL, "clef-flash", None, max(timeout, 35.0)),
    ]

    official_key = os.getenv("TYPESAFE_API_KEY")
    if official_key:
        tiers.append(
            ("Tier-3 Official (TypeSafe Jev)", FALLBACK3_URL, "typesafe-ai/jev", official_key, max(timeout, 25.0))
        )

    last_error = None
    for tier_name, url, default_model, api_key, t_out in tiers:
        # Override model_id if user explicitly requested a specific model for official tier
        req_model = default_model
        if "typesafe.ai" in url and ("jev" in str(model_name).lower() or model_name):
            req_model = model_name or "typesafe-ai/jev"

        payload = build_jev_request(system_prompt, user_prompt, model=req_model)
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=t_out)
            if resp.status_code == 200:
                raw_data = resp.json()
                result = normalize_jev_response(raw_data, include_bilingual=include_bilingual)
                result["provider_tier"] = tier_name
                result["endpoint"] = url
                return result
            else:
                logger.warning(f"[{tier_name}] Returned HTTP {resp.status_code}: {resp.text[:200]}")
                last_error = f"HTTP {resp.status_code}: {resp.text[:100]}"
        except Exception as e:
            logger.warning(f"[{tier_name}] Request failed: {e}")
            last_error = str(e)
            continue

    raise RuntimeError(f"All SystemOne endpoints failed. Last error: {last_error}")


class ChatSystemOne:
    """
    LangChain ChatModel compatible wrapper for Clef-Flash and TypeSafe JEV SystemOne engines.
    """
    def __init__(self, model_name: str = "clef-flash", timeout: float = 8.0):
        self.model_name = model_name
        self.timeout = timeout

    def invoke(self, prompt: Any) -> Any:
        from langchain_core.messages import AIMessage
        system_text, user_text = extract_system_and_user_prompts(prompt)
        res = call_systemone_with_failover(
            system_prompt=system_text,
            user_prompt=user_text,
            model_name=self.model_name,
            timeout=self.timeout
        )
        payload = {
            "signal": res["signal"],
            "confidence": res["confidence"],
            "reasoning": res["reasoning"]
        }
        return AIMessage(content=json.dumps(payload))

    def with_structured_output(self, pydantic_model: Any, **kwargs):
        class _StructuredRunnable:
            def __init__(self, parent_client, schema_model):
                self.parent_client = parent_client
                self.schema_model = schema_model

            def invoke(self, prompt: Any):
                fields = self.schema_model.model_fields if hasattr(self.schema_model, "model_fields") else {}
                # If schema requires complex generative fields (decisions, debate transcripts),
                # SystemOne is an evaluation classifier and cannot generate multi-asset JSON.
                # Seamlessly delegate to the primary/fallback generative LLM.
                if "decisions" in fields or "discussion_summary" in fields or "signal" not in fields:
                    from llm.models import get_fallback_model
                    fallback = get_fallback_model()
                    return fallback.with_structured_output(self.schema_model, method="json_mode").invoke(prompt)

                system_text, user_text = extract_system_and_user_prompts(prompt)
                res = call_systemone_with_failover(
                    system_prompt=system_text,
                    user_prompt=user_text,
                    model_name=self.parent_client.model_name,
                    timeout=self.parent_client.timeout
                )
                data = {
                    "signal": res["signal"],
                    "confidence": res["confidence"],
                    "reasoning": res["reasoning"]
                }
                for f_name in fields:
                    if f_name not in data:
                        data[f_name] = None
                return self.schema_model(**data)

        return _StructuredRunnable(self, pydantic_model)
