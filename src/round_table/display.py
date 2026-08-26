from colorama import Fore, Style

def print_readable_conversation(transcript: str):
    """Format and print the conversation in a more readable way with color coding."""
    lines = transcript.split('\n')
    
    # Define colors for different analysts
    analyst_colors = {
        "Warren Buffett": Fore.GREEN,
        "Charlie Munger": Fore.GREEN + Style.BRIGHT,
        "Ben Graham": Fore.GREEN,
        "Cathie Wood": Fore.MAGENTA,
        "Bill Ackman": Fore.BLUE + Style.BRIGHT,
        "Nancy Pelosi": Fore.CYAN,
        "Michael Burry": Fore.RED + Style.BRIGHT,
        "Peter Lynch": Fore.YELLOW + Style.BRIGHT,
        "Phil Fisher": Fore.GREEN + Style.BRIGHT,
        "Technical Analyst": Fore.YELLOW,
        "Fundamental Analyst": Fore.WHITE + Style.BRIGHT,
        "Sentiment Analyst": Fore.RED,
        "Valuation Analyst": Fore.BLUE,
        "WallStreetBets": Fore.RED + Style.BRIGHT,
        "WSB": Fore.RED + Style.BRIGHT,
        "Moderator": Fore.WHITE + Style.BRIGHT,
        "Chairman": Fore.WHITE + Style.BRIGHT,
    }
    
    current_analyst = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check if this line starts a new speaker
        for analyst in analyst_colors:
            if line.startswith(f"{analyst}:") or line.startswith(f"**{analyst}:**") or line.startswith(f"[{analyst}]:"):
                current_analyst = analyst
                name_end = line.find(':') + 1
                print(f"{analyst_colors[analyst]}{line[:name_end]}{Style.RESET_ALL}{line[name_end:]}")
                break
        else:
            # Continuation of previous speaker or general text
            if current_analyst and not any(marker in line for marker in ['===', '---', '***']):
                print(f"  {line}")
            else:
                # Section headers or other formatting
                print(f"{Fore.WHITE}{Style.BRIGHT}{line}{Style.RESET_ALL}")


def get_signal_color(signal: str) -> str:
    """Return the appropriate color for a signal"""
    if str(signal).lower() == "bullish":
        return Fore.GREEN
    elif str(signal).lower() == "bearish":
        return Fore.RED
    else:
        return Fore.YELLOW