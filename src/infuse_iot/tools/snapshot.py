"""Collect decoded device telemetry without starting the browser viewer."""

import json
import sys

from infuse_iot.commands import InfuseCommand
from infuse_iot.services.collector import TelemetryCollector
from infuse_iot.socket_comms import GatewayControlError
from infuse_iot.util.argparse import add_server_port_parser


def describe(row: dict) -> str:
    """One line per device, giving the firmware announcement its own age"""
    if row["firmware_version"] is None:
        firmware = "firmware unknown"
    else:
        stale = ", stale" if row["firmware_stale"] else ""
        firmware = f"firmware {row['firmware_version']} (announced {row['firmware_age_seconds']:.1f}s ago{stale})"
    return f"{row['id']} {firmware}, last heard {row['age_seconds']:.1f}s ago"


class SubCommand(InfuseCommand):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--duration", type=float, default=20)
        parser.add_argument("--json", action="store_true", help="Return typed telemetry with per-reading freshness")
        add_server_port_parser(parser)

    def __init__(self, args):
        self.args = args

    def run(self):
        collector = TelemetryCollector(self.args.server_sock)
        try:
            result = collector.collect(self.args.duration, paginate=False)
        except GatewayControlError as error:
            sys.exit(f"{error.code}: {error.message}")
        except ValueError as error:
            sys.exit(str(error))
        if self.args.json:
            print(json.dumps(result, indent=2, allow_nan=False))
            return
        for row in result["items"]:
            print(describe(row))
        print(f"{result['total']} devices observed in this collection window")
        counters = result["gateway"]["counters"]
        if counters is not None:
            print("Gateway counters during the window: " + ", ".join(f"{k} {v}" for k, v in sorted(counters.items())))
