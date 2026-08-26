"""
Entry point for running investment round table discussions.
"""

from agents.round_table import round_table

def run_round_table(data: dict, model_name: str, model_provider: str, show_reasoning: bool = True, num_rounds: int = 2) -> dict:
    """
    Simulates a multi-round round table discussion among investment analysts.
    """
    return round_table(
        data=data,
        model_name=model_name,
        model_provider=model_provider,
        show_reasoning=show_reasoning,
        num_rounds=num_rounds,
    )