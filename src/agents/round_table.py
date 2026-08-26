"""
Round table discussion wrapper for agent graph workflow and standalone execution.
"""

from graph.state import show_agent_reasoning
from utils.progress import progress
from colorama import Fore, Style
from round_table.engine import simulate_round_table, RoundTableOutput
from round_table.display import print_readable_conversation, get_signal_color


def round_table(data: dict, model_name: str, model_provider: str, show_reasoning: bool = True, num_rounds: int = 2) -> dict:
    """
    Simulates a multi-round round table discussion among investment analysts based on their signals.
    """
    print(f"\n{Fore.CYAN}{Style.BRIGHT}Investment Round Table Discussion ({num_rounds} Rounds){Style.RESET_ALL}")
    
    analyst_signals = data.get("analyst_signals", {})
    tickers = data.get("tickers", [])
    
    if not analyst_signals:
        print(f"{Fore.RED}No analyst signals available for round table discussion{Style.RESET_ALL}")
        return {}
    
    # Filter out manager signals
    filtered_signals = {
        agent: signals for agent, signals in analyst_signals.items() 
        if agent not in ["risk_management_agent", "portfolio_management_agent", "round_table"]
    }
    
    round_table_analysis = {}
    
    for ticker in tickers:
        progress.update_status("round_table", ticker, "Collecting analyst inputs")
        
        # Collect signals for this specific ticker
        ticker_signals = {}
        for agent_name, signals in filtered_signals.items():
            if ticker in signals:
                ticker_signals[agent_name] = signals[ticker]
        
        if not ticker_signals:
            progress.update_status("round_table", ticker, "No signals found for discussion")
            print(f"{Fore.RED}No analyst signals found for {ticker}. Cannot conduct round table.{Style.RESET_ALL}")
            continue
        
        print(f"{Fore.CYAN}Found {len(ticker_signals)} analyst signals for {ticker}{Style.RESET_ALL}")
        progress.update_status("round_table", ticker, f"Simulating {num_rounds}-round debate with {len(ticker_signals)} analysts")
        
        round_table_output: RoundTableOutput = simulate_round_table(
            ticker=ticker,
            ticker_signals=ticker_signals,
            model_name=model_name,
            model_provider=model_provider,
            num_rounds=num_rounds,
        )
        
        round_table_analysis[ticker] = {
            "signal": round_table_output.signal,
            "confidence": round_table_output.confidence,
            "reasoning": round_table_output.reasoning,
            "discussion_summary": round_table_output.discussion_summary,
            "consensus_view": round_table_output.consensus_view,
            "dissenting_opinions": round_table_output.dissenting_opinions,
            "conversation_transcript": round_table_output.conversation_transcript
        }
        
        print(f"\n{Fore.WHITE}{Style.BRIGHT}===== INVESTMENT ROUND TABLE: {Fore.CYAN}{ticker}{Fore.WHITE} ====={Style.RESET_ALL}")
        if show_reasoning:
            print_readable_conversation(round_table_output.conversation_transcript)
            print(f"\n{Fore.WHITE}{Style.BRIGHT}===== CONCLUSION ====={Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Signal: {get_signal_color(round_table_output.signal)}{round_table_output.signal.upper()}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Confidence: {Fore.WHITE}{round_table_output.confidence}%{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Reasoning: {Fore.WHITE}{round_table_output.reasoning}{Style.RESET_ALL}\n")
        else:
            preview = round_table_output.conversation_transcript.split('\n')[:5]
            print('\n'.join(preview))
            print(f"{Fore.YELLOW}... [Set show_reasoning=True to view full debate transcript] ...{Style.RESET_ALL}")
            
        print(f"{Fore.WHITE}{Style.BRIGHT}{'=' * 80}{Style.RESET_ALL}\n")
        progress.update_status("round_table", ticker, "Discussion completed")
    
    if show_reasoning:
        show_agent_reasoning(round_table_analysis, "Investment Round Table")
    
    return round_table_analysis