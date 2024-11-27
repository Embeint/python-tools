#!/usr/bin/env python3


import datetime

import colorama


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
    def log_tx(data_type, length):
        """Log transmitted packet to terminal"""
        Console.log(
            datetime.datetime.now(),
            colorama.Fore.BLUE,
            f"TX {data_type.name} {length} bytes",
        )

    @staticmethod
    def log_rx(data_type, length):
        """Log received packet to terminal"""
        Console.log(
            datetime.datetime.now(),
            colorama.Fore.GREEN,
            f"RX {data_type.name} {length} bytes",
        )

    @staticmethod
    def log(timestamp: datetime.datetime, colour, string: str):
        """Log colourised string to terminal"""
        ts = timestamp.strftime("%H:%M:%S.%f")[:-3]
        print(f"[{ts}]{colour} {string}")
