from __future__ import annotations

import sys
from datetime import datetime
from colorama import Fore, Style, init as colorama_init


colorama_init()


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def info(msg: str) -> None:
    print(f"{Fore.CYAN}[{_ts()}] INFO{Style.RESET_ALL} {msg}")


def success(msg: str) -> None:
    print(f"{Fore.GREEN}[{_ts()}] OK  {Style.RESET_ALL} {msg}")


def warn(msg: str) -> None:
    print(f"{Fore.YELLOW}[{_ts()}] WARN{Style.RESET_ALL} {msg}")


def error(msg: str) -> None:
    print(f"{Fore.RED}[{_ts()}] ERR {Style.RESET_ALL} {msg}", file=sys.stderr)

