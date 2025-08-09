#!/usr/bin/env python3

import tabulate

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.zephyr.errno import errno


class infuse_states_query(InfuseRpcCommand, defs.infuse_states_query):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--offset", type=int, default=0)

    def __init__(self, args):
        self.args = args

    def request_struct(self):
        return self.request(self.args.offset)

    def request_json(self):
        return {}

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to query states ({errno.strerror(-return_code)})")
            return

        states = []
        for state in response.states:
            states.append([state.state, "Permanent" if state.timeout == 0 else f"{state.timeout} seconds"])
        print(tabulate.tabulate(states, headers=["State", "Duration"]))
