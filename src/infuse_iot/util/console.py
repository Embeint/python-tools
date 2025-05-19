#!/usr/bin/env python3


import datetime

import colorama

try:
    from simple_term_menu import TerminalMenu
except NotImplementedError:
    pass


class Console:
    """Common terminal logging functions"""

    @staticmethod
    def init():
        """Initialise console logging"""
        colorama.init(autoreset=True)

    @staticmethod
    def log_error(message):
        """Log error message to terminal"""
        Console.log(datetime.datetime.now(), colorama.Fore.RED, message)

    @staticmethod
    def log_info(message):
        """Log info message to terminal"""
        Console.log(datetime.datetime.now(), colorama.Fore.MAGENTA, message)

    @staticmethod
    def log_text(message):
        """Log text to terminal"""
        Console.log(datetime.datetime.now(), colorama.Fore.RESET, message)

    @staticmethod
    def log_tx(data_type, length, prefix=""):
        """Log transmitted packet to terminal"""
        Console.log(
            datetime.datetime.now(),
            colorama.Fore.BLUE,
            f"{prefix}TX {data_type.name} {length} bytes",
        )

    @staticmethod
    def log_rx(data_type, length, prefix=""):
        """Log received packet to terminal"""
        Console.log(
            datetime.datetime.now(),
            colorama.Fore.GREEN,
            f"{prefix}RX {data_type.name} {length} bytes",
        )

    @staticmethod
    def log(timestamp: datetime.datetime, colour, string: str):
        """Log colourised string to terminal"""
        ts = timestamp.strftime("%H:%M:%S.%f")[:-3]
        print(f"[{ts}]{colour} {string}")


def choose_one(title: str, options: list[str]) -> tuple[int, str]:
    """Select a single option from a list"""

    if TerminalMenu:
        # Linux & MacOS
        terminal_menu = TerminalMenu(options, title=title)
        idx = terminal_menu.show()
        if idx is None:
            raise IndexError("No option chosen")
        return idx, options[idx]
    else:
        # Windows
        print(title)
        for idx, option in enumerate(options):
            print(f" {idx:2d}: {option}")
        idx = None
        while idx is None:
            try:
                idx = int(input(f"Enter index between 0 and {len(options) - 1}:"))
                if not (0 <= idx < len(options)):
                    idx = None
            except ValueError:
                pass

        return idx, options[idx]
