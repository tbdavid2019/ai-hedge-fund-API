import sys

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph
from colorama import Fore, Back, Style, init
import questionary
from agents.ben_graham import ben_graham_agent
from agents.bill_ackman import bill_ackman_agent
from agents.fundamentals import fundamentals_agent
from agents.portfolio_manager import portfolio_management_agent
from agents.technicals import technical_analyst_agent
from agents.risk_manager import risk_management_agent
from agents.sentiment import sentiment_agent
from agents.warren_buffett import warren_buffett_agent
from graph.state import AgentState
from agents.valuation import valuation_agent
from utils.display import print_trading_output
from utils.analysts import ANALYST_ORDER, get_analyst_nodes
from utils.progress import progress
from llm.models import LLM_ORDER, get_model_info
from agents.round_table import round_table

import argparse
from datetime import datetime
from dateutil.relativedelta import relativedelta
from tabulate import tabulate
from utils.visualize import save_graph_as_png
import json

# Load environment variables from .env file
load_dotenv()

init(autoreset=True)


def parse_hedge_fund_response(response):
    import json

    try:
        return json.loads(response)
    except:
        print(f"Error parsing response: {response}")
        return None


##### Run the Hedge Fund #####
def run_hedge_fund(
    tickers: list[str],
    start_date: str,
    end_date: str,
    portfolio: dict,
    show_reasoning: bool = False,
    selected_analysts: list[str] = [],
    model_name: str = "deepseek-v4-flash",
    model_provider: str = "OpenAI-Compatible",
    is_crypto: bool = False,
    enable_round_table: bool = False,
    round_table_rounds: int = 2,
):
    # Start progress tracking
    progress.start()

    try:
        # Create a new workflow with the specified analysts
        workflow = create_workflow(selected_analysts)
        
        # Print the selected analysts for debugging
        print(f"\n{Fore.CYAN}Selected analysts for workflow: {selected_analysts}{Style.RESET_ALL}\n")
        
        app = workflow.compile()

        # Create the initial state
        initial_state = {
            "messages": [],
            "data": {
                "tickers": tickers,
                "start_date": start_date,
                "end_date": end_date,
                "portfolio": portfolio,
                "analyst_signals": {},
                "is_crypto": is_crypto,
            },
            "metadata": {
                "show_reasoning": show_reasoning,
                "model_name": model_name,
                "model_provider": model_provider,
                "is_crypto": is_crypto,
            },
        }

        # Run the workflow
        result = app.invoke(initial_state)
        
        # Stop progress tracking
        progress.stop()

        # Extract the portfolio decisions
        if "portfolio_decision" in result["data"]:
            portfolio_decision = result["data"]["portfolio_decision"]
        else:
            # Handle the case where portfolio_decision might be missing
            for message in reversed(result["messages"]):
                if hasattr(message, "name") and message.name == "portfolio_management_agent":
                    try:
                        portfolio_decision = json.loads(message.content)
                        break
                    except:
                        pass
            else:
                portfolio_decision = {}
                print(f"{Fore.RED}Warning: Could not find portfolio decisions in output{Style.RESET_ALL}")
        
        response_dict = {
            "decisions": portfolio_decision,
            "analyst_signals": result["data"]["analyst_signals"],
        }

        # Run Multi-Round Round Table if enabled
        if enable_round_table:
            progress.start()
            from agents.round_table import round_table
            rt_results = round_table(
                data={
                    "tickers": tickers,
                    "analyst_signals": result["data"]["analyst_signals"]
                },
                model_name=model_name,
                model_provider=model_provider,
                show_reasoning=show_reasoning,
                num_rounds=round_table_rounds,
            )
            progress.stop()
            response_dict["round_table"] = rt_results
            response_dict["analyst_signals"]["round_table"] = rt_results

        return response_dict
    except Exception as e:
        progress.stop()
        print(f"Error running hedge fund: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def start(state: AgentState):
    """Initialize the workflow with the input message."""
    return state


def create_workflow(selected_analysts=None):
    """Create the workflow with selected analysts."""
    workflow = StateGraph(AgentState)
    workflow.add_node("start_node", start)

    # Get analyst nodes from the configuration
    analyst_nodes = get_analyst_nodes()
    
    print(f"\n{Fore.YELLOW}Creating workflow with analysts: {selected_analysts}{Style.RESET_ALL}")
    
    # Default to all analysts if none selected or empty list passed
    if not selected_analysts:
        selected_analysts = list(analyst_nodes.keys())
        print(f"{Fore.CYAN}No analysts specified, defaulting to all: {selected_analysts}{Style.RESET_ALL}")
    
    # Add all selected analyst nodes
    for analyst_key in selected_analysts:
        if analyst_key in analyst_nodes:
            node_name, node_func = analyst_nodes[analyst_key]
            workflow.add_node(node_name, node_func)
            workflow.add_edge("start_node", node_name)
        else:
            print(f"{Fore.RED}Warning: Analyst {analyst_key} not found in configuration{Style.RESET_ALL}")
    
    # Always add risk and portfolio management
    workflow.add_node("risk_management_agent", risk_management_agent)
    workflow.add_node("portfolio_management_agent", portfolio_management_agent)
    
    # Connect all analysts to risk management
    for analyst_key in selected_analysts:
        if analyst_key in analyst_nodes:
            node_name = analyst_nodes[analyst_key][0]
            workflow.add_edge(node_name, "risk_management_agent")
    
    # Connect risk management to portfolio management
    workflow.add_edge("risk_management_agent", "portfolio_management_agent")
    workflow.add_edge("portfolio_management_agent", END)

    workflow.set_entry_point("start_node")
    return workflow


def run_all_analysts_with_round_table(tickers, start_date, end_date, portfolio, show_reasoning, model_name, model_provider, is_crypto=False):
    """
    Run all available analysts and then conduct a round table discussion without user selection.
    This is a simplified workflow for when the user specifies the --round-table flag.
    """
    # Get all available analyst keys (except master which we're removing)
    analyst_nodes = get_analyst_nodes()
    all_analysts = [key for key in analyst_nodes.keys() if key != "master"]
    
    print(f"\n{Fore.YELLOW}Running all analysts for Round Table discussion:{Style.RESET_ALL}")
    for analyst in all_analysts:
        print(f"  {analyst_nodes[analyst][0].replace('_agent', '').replace('_', ' ').title()}")
    print("")  # Empty line for spacing
    
    # Run the regular hedge fund with all analysts
    result = run_hedge_fund(
        tickers=tickers,
        start_date=start_date,
        end_date=end_date,
        portfolio=portfolio,
        show_reasoning=show_reasoning,
        selected_analysts=all_analysts,
        model_name=model_name,
        model_provider=model_provider,
        is_crypto=is_crypto,
    )
    
    # Run the round table discussion
    from round_table import run_round_table
    round_table_results = run_round_table(
        data={
            "tickers": tickers,
            "analyst_signals": result["analyst_signals"]
        },
        model_name=model_name,
        model_provider=model_provider,
        show_reasoning=show_reasoning
    )
    
    # Add the round table results to the analyst signals
    result["analyst_signals"]["round_table"] = round_table_results
    
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the hedge fund trading system")
    parser.add_argument(
        "--initial-cash",
        type=float,
        default=100000.0,
        help="Initial cash position. Defaults to 100000.0)"
    )
    parser.add_argument(
        "--margin-requirement",
        type=float,
        default=0.0,
        help="Initial margin requirement. Defaults to 0.0"
    )
    parser.add_argument("--tickers", type=str, required=True, help="Comma-separated list of stock ticker symbols")
    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date (YYYY-MM-DD). Defaults to 3 months before end date",
    )
    parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD). Defaults to today")
    parser.add_argument("--show-reasoning", action="store_true", help="Show reasoning from each agent")
    parser.add_argument(
        "--show-agent-graph", action="store_true", help="Show the agent graph"
    )
    parser.add_argument(
        "--round-table",
        action="store_true",
        help="Run an investment round table discussion after individual analyst evaluations"
    )
    parser.add_argument(
        "--crypto",
        action="store_true",
        help="Analyze cryptocurrency instead of stocks (append -USD to ticker symbols)"
    )

    args = parser.parse_args()

    # Parse tickers from comma-separated string
    tickers = [ticker.strip() for ticker in args.tickers.split(",")]
    
    # If crypto mode is enabled, append USD suffix to tickers if not already present
    if args.crypto:
        tickers = [ticker if ("-USD" in ticker.upper() or "/USD" in ticker.upper()) 
                  else f"{ticker}-USD" for ticker in tickers]

    # Select LLM model
    model_choice = questionary.select(
        "Select your LLM model:",
        choices=[questionary.Choice(display, value=value) for display, value, _ in LLM_ORDER],
        style=questionary.Style([
            ("selected", "fg:green bold"),
            ("pointer", "fg:green bold"),
            ("highlighted", "fg:green"),
            ("answer", "fg:green bold"),
        ])
    ).ask()

    if not model_choice:
        print("\n\nInterrupt received. Exiting...")
        sys.exit(0)
    else:
        model_info = get_model_info(model_choice)
        if model_info:
            model_provider = model_info.provider.value
            print(f"\nSelected {Fore.CYAN}{model_provider}{Style.RESET_ALL} model: {Fore.GREEN + Style.BRIGHT}{model_choice}{Style.RESET_ALL}\n")
        else:
            model_provider = "Unknown"
            print(f"\nSelected model: {Fore.GREEN + Style.BRIGHT}{model_choice}{Style.RESET_ALL}\n")

    # Validate dates if provided
    if args.start_date:
        try:
            datetime.strptime(args.start_date, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Start date must be in YYYY-MM-DD format")

    if args.end_date:
        try:
            datetime.strptime(args.end_date, "%Y-%m-%d")
        except ValueError:
            raise ValueError("End date must be in YYYY-MM-DD format")

    # Set the start and end dates
    end_date = args.end_date or datetime.now().strftime("%Y-%m-%d")
    if not args.start_date:
        # Calculate 3 months before end_date
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
        start_date = (end_date_obj - relativedelta(months=3)).strftime("%Y-%m-%d")
    else:
        start_date = args.start_date

    # Initialize portfolio with cash amount and stock positions
    portfolio = {
        "cash": args.initial_cash,  # Initial cash amount
        "margin_requirement": args.margin_requirement,  # Initial margin requirement
        "positions": {
            ticker: {
                "long": 0,  # Number of shares held long
                "short": 0,  # Number of shares held short
                "long_cost_basis": 0.0,  # Average cost basis for long positions
                "short_cost_basis": 0.0,  # Average price at which shares were sold short
            } for ticker in tickers
        },
        "realized_gains": {
            ticker: {
                "long": 0.0,  # Realized gains from long positions
                "short": 0.0,  # Realized gains from short positions
            } for ticker in tickers
        }
    }

    # Bypass analyst selection when round table is specified
    if args.round_table:
        # Run all analysts and round table without requiring user selection
        result = run_all_analysts_with_round_table(
            tickers=tickers,
            start_date=start_date,
            end_date=end_date,
            portfolio=portfolio,
            show_reasoning=args.show_reasoning,
            model_name=model_choice,
            model_provider=model_provider,
            is_crypto=args.crypto
        )
        print_trading_output(result)
    else:
        # Regular flow - prompt user to select analysts
        selected_analysts = None
        choices = questionary.checkbox(
            "Select your AI analysts.",
            choices=[questionary.Choice(display, value=value) for display, value in ANALYST_ORDER],
            instruction="\n\nInstructions: \n1. Press Space to select/unselect analysts.\n2. Press 'a' to select/unselect all.\n3. Press Enter when done to run the hedge fund.\n",
            validate=lambda x: len(x) > 0 or "You must select at least one analyst.",
            style=questionary.Style(
                [
                    ("checkbox-selected", "fg:green"),
                    ("selected", "fg:green noinherit"),
                    ("highlighted", "noinherit"),
                    ("pointer", "noinherit"),
                ]
            ),
        ).ask()
        
        if not choices:
            print("\n\nInterrupt received. Exiting...")
            sys.exit(0)
        else:
            selected_analysts = choices
            print(f"\nSelected analysts: {', '.join(Fore.GREEN + choice.title().replace('_', ' ') + Style.RESET_ALL for choice in choices)}\n")

        # Create workflow for visualization if requested
        if args.show_agent_graph:
            workflow = create_workflow(selected_analysts)
            app = workflow.compile()
            
            file_path = ""
            for selected_analyst in selected_analysts:
                file_path += selected_analyst + "_"
            file_path += "graph.png"
            save_graph_as_png(app, file_path)

        # Run the hedge fund with is_crypto flag
        result = run_hedge_fund(
            tickers=tickers,
            start_date=start_date,
            end_date=end_date,
            portfolio=portfolio,
            show_reasoning=args.show_reasoning,
            selected_analysts=selected_analysts,
            model_name=model_choice,
            model_provider=model_provider,
            is_crypto=args.crypto
        )
        print_trading_output(result)
