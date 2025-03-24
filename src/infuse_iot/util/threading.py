#!/usr/bin/env python3

import threading
from collections.abc import Callable


class SignaledThread(threading.Thread):
    """Thread that can be signaled to terminate"""

    def __init__(self, fn: Callable[[], None], sig: threading.Event | None = None):
        self._fn = fn
        self._sig = sig if sig is not None else threading.Event()
        super().__init__(target=self.run_loop)

    def stop(self):
        """Signal thread to terminate"""
        self._sig.set()

    def run_loop(self):
        """Run the thread function in a loop"""
        try:
            while not self._sig.is_set():
                self._fn()
        except Exception as e:
            import traceback

            # Print the exception traceback
            traceback.print_exception(e)
            # Set the termination signal
            self._sig.set()
