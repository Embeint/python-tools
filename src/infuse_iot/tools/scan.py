"""Collect raw Bluetooth evidence with an explicit scanner owner."""

import argparse
import asyncio
import json
import sys

from bleak import BleakScanner

from infuse_iot.commands import InfuseCommand
from infuse_iot.services.ble_observations import MAX_AGE_SECONDS, BleObservations
from infuse_iot.services.collector import counter_changes, gateway_counters
from infuse_iot.socket_comms import GatewayControlError, LocalClient
from infuse_iot.util.argparse import add_server_port_parser


async def collect_scan(
    address: tuple[str, int], duration: float = 20, standalone: bool = False, cursor: str | None = None, limit: int = 50
) -> dict:
    if not 0 < duration <= 60:
        raise ValueError("duration must be between 0 and 60 seconds")
    if standalone:
        if cursor is not None:
            raise ValueError("Standalone scans do not accept a cursor")
        observations = BleObservations()

        def callback(device, advertisement):
            observations.observe(
                device.address,
                advertisement.local_name or device.name,
                advertisement.rssi,
                advertisement.manufacturer_data,
                advertisement.service_uuids,
            )

        # Report addresses rather than macOS identifiers, and repeated advertisements, as native_bt does.
        async with BleakScanner(
            callback,
            scanning_mode="active",
            bluez={"filters": {"DuplicateData": True}},
            cb=dict(use_bdaddr=True),
        ):
            await asyncio.sleep(duration)
        # These observations began with the scan, so all of them are within its window.
        return observations.snapshot(max_age_seconds=MAX_AGE_SECONDS, paginate=False, metadata={"gateway": None})
    client = LocalClient(address)
    try:
        try:
            capabilities = await asyncio.to_thread(client.capabilities)
        except TimeoutError:
            raise GatewayControlError(
                "gateway_unavailable", "No gateway answered; start infuse native_bt or scan with --standalone"
            ) from None
        if "raw_observations" not in capabilities.get("features", []):
            raise GatewayControlError(
                "unsupported_capability", "Use an updated native_bt gateway or scan with --standalone"
            )
        before = None
        if cursor is None:
            before = await asyncio.to_thread(gateway_counters, address, capabilities)
            await asyncio.sleep(duration)
        parameters = {"max_age_seconds": duration, "cursor": cursor, "limit": limit}
        try:
            result = await asyncio.to_thread(client.control_request, "raw_observations", parameters)
        except TimeoutError:
            raise GatewayControlError("gateway_unavailable", "The gateway did not answer the scan query") from None
        after = None if before is None else await asyncio.to_thread(gateway_counters, address, capabilities)
        # Counters only describe the window of a new scan, not the continuation of a snapshot.
        result["gateway"] = {**(result.get("gateway") or {}), "counters": counter_changes(before, after)}
        return result
    finally:
        client.close()


class SubCommand(InfuseCommand):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--duration", type=float, default=20)
        parser.add_argument("--cursor", help="Continue an attached scan snapshot using the same duration")
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument(
            "--standalone", action="store_true", help="Own the adapter instead of attaching to a gateway"
        )
        parser.add_argument("--json", action="store_true", help="Return a typed JSON snapshot")
        add_server_port_parser(parser)

    def __init__(self, args: argparse.Namespace):
        self.args = args

    def run(self):
        try:
            result = asyncio.run(
                collect_scan(
                    self.args.server_sock, self.args.duration, self.args.standalone, self.args.cursor, self.args.limit
                )
            )
        except GatewayControlError as error:
            sys.exit(f"{error.code}: {error.message}")
        except ValueError as error:
            sys.exit(str(error))
        if self.args.json:
            print(json.dumps(result, indent=2, allow_nan=False))
        else:
            for row in result["items"]:
                marker = " INFUSE candidate" if row["infuse_candidate"] else ""
                truncated = " (markers truncated)" if row["truncated"] else ""
                print(f"{row['identifier']} {row['rssi']:4d} {row['name'] or '(unnamed)'}{marker}{truncated}")
            print(f"{result['total']} observed identifiers; more cursor: {result['next_cursor']}")
