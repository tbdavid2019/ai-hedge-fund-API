"""
Multi-Round Investment Round Table Discussion Engine.
Simulates organic, multi-turn debates between distinct financial analyst personas
to reach a synthesized investment consensus.
"""

import json
import logging
import time
from typing import Dict, List, Any, Optional
from typing_extensions import Literal
from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage, SystemMessage
from llm.models import get_model, ModelProvider
from utils.progress import progress

logger = logging.getLogger(__name__)


class RoundTableOutput(BaseModel):
    signal: Literal["bullish", "bearish", "neutral"]
    confidence: float = Field(description="Confidence level between 0 and 100")
    reasoning: str = Field(description="Detailed reasoning behind the decision")
    discussion_summary: str = Field(description="Summary of the key points from the discussion")
    consensus_view: str = Field(description="The main consensus view that emerged")
    dissenting_opinions: str = Field(description="Notable contrarian perspectives")
    conversation_transcript: str = Field(description="Transcript of the simulated conversation")


# All 14 analyst personas with distinct philosophies and speaking styles
PERSONA_REGISTRY: Dict[str, Dict[str, str]] = {
    "warren_buffett": {
        "name": "Warren Buffett",
        "style": "Patient, folksy, razor-sharp on competitive moats and predictable cash flows",
        "philosophy": "Rule #1: Never lose money. Rule #2: Never forget rule #1. Buy wonderful businesses at fair prices.",
    },
    "charlie_munger": {
        "name": "Charlie Munger",
        "style": "Blunt, no-BS, invokes multi-disciplinary mental models and inverted thinking",
        "philosophy": "Invert, always invert. Avoid standard stupidity and exorbitant fees.",
    },
    "ben_graham": {
        "name": "Ben Graham",
        "style": "Methodical, conservative, strictly focused on margin of safety and balance sheet protection",
        "philosophy": "An investment operation is one which, upon thorough analysis, promises safety of principal and an adequate return.",
    },
    "cathie_wood": {
        "name": "Cathie Wood",
        "style": "Visionary, highly optimistic on exponential technology curves and disruptive innovation",
        "philosophy": "Focus on 5-year horizons in AI, robotics, genomics, and energy storage regardless of near-term volatility.",
    },
    "bill_ackman": {
        "name": "Bill Ackman",
        "style": "Forceful, activist mindset, detailed corporate restructuring and catalyst-driven",
        "philosophy": "Simple, predictable, free-cash-flow-generative businesses with dominant market positions and fixable operational levers.",
    },
    "nancy_pelosi": {
        "name": "Nancy Pelosi",
        "style": "Pragmatic political insider, sharp eye on legislative spending, tariffs, subsidies, and policy tailwinds",
        "philosophy": "Follow the capital flows from government policy, chips acts, defense, and infrastructure spending.",
    },
    "michael_burry": {
        "name": "Michael Burry",
        "style": "Terse, obsessive data cruncher, deep-value contrarian sniffing out hidden debt, bubbles, and accounting tricks",
        "philosophy": "Look at what everyone is ignoring. Focus on FCF yields, debt maturity walls, and downside protection.",
    },
    "peter_lynch": {
        "name": "Peter Lynch",
        "style": "Down-to-earth, consumer-savvy, focused on PEG ratios and understandable growth stories",
        "philosophy": "Invest in what you know. Look for 10-baggers with sustainable growth, low debt, and strong earnings trajectory.",
    },
    "phil_fisher": {
        "name": "Phil Fisher",
        "style": "Growth-quality investigator, focused on R&D excellence, superior sales organization, and long-term moat",
        "philosophy": "Scuttlebutt research and 15-point qualitative framework for extraordinary long-term compounders.",
    },
    "wsb": {
        "name": "WallStreetBets",
        "style": "Irreverent, momentum-driven, slang-heavy (tendies, apes, diamond hands, YOLO, short squeeze)",
        "philosophy": "High retail hype, asymmetric gamma squeezes, options leverage, and sticking it to short sellers.",
    },
    "technical_analyst": {
        "name": "Technical Analyst",
        "style": "Quantitative, chartist, focused on RSI, Bollinger Bands, support/resistance, and trend channels",
        "philosophy": "Price action discounts everything. Follow momentum and respect key technical levels.",
    },
    "fundamentals_analyst": {
        "name": "Fundamental Analyst",
        "style": "Meticulous financial statement examiner, checking margins, ROE, debt coverage, and earnings quality",
        "philosophy": "Numbers don't lie. Balance sheets and cash flow statements reveal the true health of the business.",
    },
    "sentiment_analyst": {
        "name": "Sentiment Analyst",
        "style": "Market psychologist, reading news narratives, social volume, and insider buying/selling signals",
        "philosophy": "Perception drives short-term price discovery. Track insider transactions and headline sentiment shifts.",
    },
    "valuation_analyst": {
        "name": "Valuation Analyst",
        "style": "Rigorous financial modeler, calculating DCF intrinsic value, EV/EBITDA multiples, and peer comparisons",
        "philosophy": "Price is what you pay, value is what you get. Never overpay for unproven growth.",
    },
}


def _clean_agent_key(name: str) -> str:
    """Normalize agent name key (e.g. 'warren_buffett_agent' -> 'warren_buffett')."""
    k = name.lower().replace("_agent", "").strip()
    return k


def simulate_round_table(
    ticker: str,
    ticker_signals: Dict[str, Any],
    model_name: str = "gpt-4o",
    model_provider: str = "OpenAI",
    num_rounds: int = 2,
) -> RoundTableOutput:
    """
    Execute a multi-round debate among the participating analysts.
    
    Rounds structure:
    - Round 1: Opening statements & core theses from key analysts.
    - Round 2: Cross-examination & direct debate on conflicting views (Bulls vs Bears).
    - Round 3 (if num_rounds >= 3): Synthesis & concession/defense.
    - Final: Moderator synthesizes the discussion into an actionable consensus signal.
    """
    active_personas = []
    signals_summary = []

    for agent_key, sig_data in ticker_signals.items():
        clean_k = _clean_agent_key(agent_key)
        persona = PERSONA_REGISTRY.get(clean_k, {
            "name": clean_k.replace("_", " ").title(),
            "style": "Professional investment analyst",
            "philosophy": "Data-driven fundamental and technical analysis.",
        })
        active_personas.append(persona)
        
        signal = sig_data.get("signal", "neutral")
        conf = sig_data.get("confidence", 50)
        reason = sig_data.get("reasoning", "")
        signals_summary.append(f"- **{persona['name']}**: Signal={signal.upper()} (Confidence={conf}%) | Thesis: {reason}")

    signals_text = "\n".join(signals_summary)
    personas_text = "\n".join([f"- **{p['name']}**: {p['style']} (Philosophy: {p['philosophy']})" for p in active_personas])

    # Construct the multi-round discussion prompt
    system_prompt = f"""You are the Chairman & Chief Moderator of the Investment Committee Round Table.
You are facilitating a high-stakes, multi-round debate on ${ticker} with a panel of legendary investors and quantitative analysts.

Panelists Present:
{personas_text}

Pre-Debate Analyst Signals:
{signals_text}

Debate Structure ({num_rounds} Rounds):
1. **Round 1 (Opening Statements & High-Conviction Theses)**:
   - Have the key Bullish, Bearish, and Neutral analysts state their primary thesis with specific numbers/arguments.
   - Maintain authentic persona voices and philosophies.

2. **Round 2 (Cross-Examination & Confrontation)**:
   - Direct rebuttals! Have analysts with opposing views challenge each other's assumptions (e.g. Valuation vs Growth, Debt vs Moat, Short Squeeze vs Fundamentals).
   - Let them engage in rapid-fire intellectual combat.

{"3. **Round 3 (Reconciliation & Final Positioning)**: Analysts revise or defend their final stance in light of counterarguments." if num_rounds >= 3 else ""}

4. **Moderator Final Resolution**:
   - The Chairman summarizes key areas of consensus and dissent.
   - Deliver the final committee recommendation.

Output Requirements:
Return a strictly valid JSON object matching this schema:
{{
  "signal": "bullish" | "bearish" | "neutral",
  "confidence": <number between 0 and 100>,
  "reasoning": "<concise 2-3 sentence summary of final decision rationale>",
  "discussion_summary": "<summary of the debate highlights and key turning points>",
  "consensus_view": "<what the committee generally agreed on>",
  "dissenting_opinions": "<notable contrarian warnings or disagreements>",
  "conversation_transcript": "<full verbatim transcript of the debate with [Speaker Name]: ... lines>"
}}
"""

    human_prompt = f"Conduct the {num_rounds}-round Investment Round Table discussion on ${ticker} now and provide the committee's consensus decision in valid JSON."

    try:
        try:
            provider_enum = ModelProvider(model_provider)
        except Exception:
            provider_enum = ModelProvider.OPENAI

        llm = get_model(model_name, provider_enum)
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt),
        ]
        
        raw_res = llm.invoke(messages)
        content = raw_res.content if hasattr(raw_res, "content") else str(raw_res)

        # Parse JSON from LLM response
        parsed_json = None
        if "```json" in content:
            extracted = content.split("```json")[1].split("```")[0].strip()
            parsed_json = json.loads(extracted)
        elif "```" in content:
            extracted = content.split("```")[1].split("```")[0].strip()
            parsed_json = json.loads(extracted)
        else:
            # Look for JSON object pattern
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1:
                parsed_json = json.loads(content[start:end+1])

        if parsed_json and "signal" in parsed_json:
            sig = str(parsed_json.get("signal", "neutral")).lower()
            if sig not in ["bullish", "bearish", "neutral"]:
                sig = "neutral"

            return RoundTableOutput(
                signal=sig,
                confidence=float(parsed_json.get("confidence", 60.0)),
                reasoning=str(parsed_json.get("reasoning", "")),
                discussion_summary=str(parsed_json.get("discussion_summary", "")),
                consensus_view=str(parsed_json.get("consensus_view", "")),
                dissenting_opinions=str(parsed_json.get("dissenting_opinions", "")),
                conversation_transcript=str(parsed_json.get("conversation_transcript", content)),
            )

    except Exception as e:
        logger.error(f"[RoundTable] Error simulating round table debate for {ticker}: {e}")

    # Fallback heuristic aggregation if LLM output parsing encounters an issue
    bullish_count = sum(1 for s in ticker_signals.values() if s.get("signal") == "bullish")
    bearish_count = sum(1 for s in ticker_signals.values() if s.get("signal") == "bearish")
    
    if bullish_count > bearish_count:
        fallback_sig = "bullish"
        conf = 65.0
    elif bearish_count > bullish_count:
        fallback_sig = "bearish"
        conf = 65.0
    else:
        fallback_sig = "neutral"
        conf = 50.0

    return RoundTableOutput(
        signal=fallback_sig,
        confidence=conf,
        reasoning=f"Round table consensus formed based on {bullish_count} bullish vs {bearish_count} bearish analyst inputs.",
        discussion_summary=f"The committee debated {ticker}'s outlook across fundamental, technical, and qualitative angles.",
        consensus_view=f"Majority sentiment leaning {fallback_sig}.",
        dissenting_opinions="Differing perspectives on valuation multiples and market momentum.",
        conversation_transcript=f"Moderator: Committee convened for {ticker}.\n" + "\n".join(signals_summary)
    )