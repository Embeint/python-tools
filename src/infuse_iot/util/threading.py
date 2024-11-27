#!/usr/bin/env python3

import threading


class SignaledThread(threading.Thread):
    """Thread that can be signaled to terminate"""

    def __init__(self, fn):
        self._fn = fn
        self._sig = threading.Event()
        super().__init__(target=self.run_loop)

    def stop(self):
        """Signal thread to terminate"""
        self._sig.set()

    def run_loop(self):
        """Run the thread function in a loop"""
        while not self._sig.is_set():
            self._fn()
