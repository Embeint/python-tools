#!/usr/bin/env python3

"""Shared dispatch for cloud commands."""

from infuse_iot.api_client import Client
from infuse_iot.credentials import get_api_auth_header
from infuse_iot.util.argparse import print_subcommands_if_missing


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
