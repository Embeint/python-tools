#!/usr/bin/env python3

"""Shared dispatch and error handling for cloud commands."""

import sys
from typing import Any

from infuse_iot.api_client import Client
from infuse_iot.api_client.models import Error
from infuse_iot.api_client.types import Response
from infuse_iot.credentials import get_api_auth_header
from infuse_iot.util.argparse import print_subcommands_if_missing


def require_response(response: Any, action: str) -> Any:
    """Report failed API requests with a nonzero exit status."""
    if isinstance(response, Response):
        if response.parsed is None:
            sys.exit(f"{action}: <{response.status_code}> {response.content.decode('utf-8', errors='replace')}")
        response = response.parsed
    if response is None:
        sys.exit(f"{action}: No response")
    if isinstance(response, Error):
        sys.exit(f"{action}: <{response.code}> {response.message}")
    return response


class CloudSubCommand:
    def __init__(self, args):
        self.args = args

    def run(self):
        if print_subcommands_if_missing(self.args):
            return
        with self.client() as client:
            self.args.command_fn(self, client)

    def client(self):
        return Client(base_url="https://api.infuse-iot.com").with_headers(get_api_auth_header(self.args.api_key))
