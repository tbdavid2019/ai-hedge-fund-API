"""Constants and utilities related to analysts configuration."""

from agents.ben_graham import ben_graham_agent
from agents.bill_ackman import bill_ackman_agent
from agents.cathie_wood import cathie_wood_agent
from agents.charlie_munger import charlie_munger_agent
from agents.fundamentals import fundamentals_agent
from agents.michael_burry import michael_burry_agent
from agents.nancy_pelosi import nancy_pelosi_agent
from agents.peter_lynch import peter_lynch_agent
from agents.sentiment import sentiment_agent
from agents.technicals import technical_analyst_agent
from agents.valuation import valuation_agent
from agents.warren_buffett import warren_buffett_agent
from agents.wsb_agent import wsb_agent

# Define analyst configuration - single source of truth
ANALYST_CONFIG = {
    "ben_graham": {
        "display_name": "Ben Graham",
        "agent_func": ben_graham_agent,
        "order": 0,
    },
    "bill_ackman": {
        "display_name": "Bill Ackman",
        "agent_func": bill_ackman_agent,
        "order": 1,
    },
    "cathie_wood": {
        "display_name": "Cathie Wood",
        "agent_func": cathie_wood_agent,
        "order": 2,
    },
    "charlie_munger": {
        "display_name": "Charlie Munger",
        "agent_func": charlie_munger_agent,
        "order": 3,
    },
    "nancy_pelosi": {
        "display_name": "Nancy Pelosi",
        "agent_func": nancy_pelosi_agent,
        "order": 4,
    },
    "michael_burry": {
        "display_name": "Michael Burry",
        "agent_func": michael_burry_agent,
        "order": 5,
    },
    "peter_lynch": {
        "display_name": "Peter Lynch",
        "agent_func": peter_lynch_agent,
        "order": 6,
    },
    "warren_buffett": {
        "display_name": "Warren Buffett",
        "agent_func": warren_buffett_agent,
        "order": 7,
    },
    "wsb": {
        "display_name": "WallStreetBets",
        "agent_func": wsb_agent,
        "order": 8,
    },
    "technical_analyst": {
        "display_name": "Technical Analyst",
        "agent_func": technical_analyst_agent,
        "order": 9,
    },
    "fundamentals_analyst": {
        "display_name": "Fundamentals Analyst",
        "agent_func": fundamentals_agent,
        "order": 10,
    },
    "sentiment_analyst": {
        "display_name": "Sentiment Analyst",
        "agent_func": sentiment_agent,
        "order": 11,
    },
    "valuation_analyst": {
        "display_name": "Valuation Analyst",
        "agent_func": valuation_agent,
        "order": 12,
    },
}

# Derive ANALYST_ORDER from ANALYST_CONFIG for backwards compatibility
ANALYST_ORDER = [(config["display_name"], key) for key, config in sorted(ANALYST_CONFIG.items(), key=lambda x: x[1]["order"])]


def get_analyst_nodes():
    """Get the mapping of analyst keys to their (node_name, agent_func) tuples."""
    return {key: (f"{key}_agent", config["agent_func"]) for key, config in ANALYST_CONFIG.items()}
