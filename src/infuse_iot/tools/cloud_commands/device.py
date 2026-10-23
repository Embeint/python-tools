#!/usr/bin/env python3

"""Infuse-IoT cloud interaction"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

import base64
import sys
from http import HTTPStatus
from typing import Any

from tabulate import tabulate

import infuse_iot.api_client.models as models
from infuse_iot.api_client import Client
from infuse_iot.api_client.api.board import (
    get_board_by_id,
)
from infuse_iot.api_client.api.device import (
    cancel_pending_device_application_updates_by_device_id,
    create_device_application_update_by_device_id,
    create_device_kv_entry_update_by_device_id_and_key_id,
    get_device_application_state_by_device_id,
    get_device_application_updates_by_device_id,
    get_device_by_device_id,
    get_device_kv_entries_by_device_id,
    get_device_last_route_by_device_id,
    get_device_logger_states_by_device_id,
    get_device_state_by_id,
    update_device_logger_state_by_device_id_and_index,
)
from infuse_iot.api_client.api.organisation import (
    get_organisation_by_id,
)
from infuse_iot.api_client.types import Unset
from infuse_iot.util.api import check_api_response, check_api_response_allow_errors, format_api_error
from infuse_iot.util.argparse import (
    HexString,
    InfuseDeviceId,
    ValidFile,
    add_subparsers_with_list,
)

from .base import CloudSubCommand


class Device(CloudSubCommand):
    logger_names = {
        0: "Onboard",
        1: "Removable",
    }

    @classmethod
    def add_parser(cls, parser):
        parser_boards = parser.add_parser("device", help="Infuse-IoT devices")
        parser_boards.set_defaults(command_class=cls)

        tool_parser = add_subparsers_with_list(parser_boards, dest="_cloud_device_command")

        info_parser = tool_parser.add_parser("info", help="General device information")
        info_parser.set_defaults(command_fn=cls.info)
        info_parser.add_argument("--id", type=InfuseDeviceId, required=True, help="Infuse-IoT device ID")

        kv_parser = tool_parser.add_parser("kv_state", help="Key-Value device state")
        kv_parser.set_defaults(command_fn=cls.kv_state)
        kv_parser.add_argument("--id", type=InfuseDeviceId, required=True, help="Infuse-IoT device ID")
        kv_parser.add_argument("--schedules", action="store_true", help="Display task schedules")
        kv_parser.add_argument("--devstate", action="store_true", help="Display Z_DEVSTATE")
        kv_display = kv_parser.add_mutually_exclusive_group()
        kv_display.add_argument("--hex", action="store_true", help="Display values as hex strings instead of decoding")
        kv_display.add_argument(
            "--base64", action="store_true", help="Display values as base64 strings instead of decoding"
        )

        kv_update = tool_parser.add_parser("kv_update", help="Key-Value update")
        kv_update.set_defaults(command_fn=cls.kv_update)
        kv_update.add_argument("--id", type=InfuseDeviceId, required=True, help="Infuse-IoT device ID")
        kv_update.add_argument("--key", "-k", type=int, required=True, help="Key ID to update")
        kv_update.add_argument("--val", "-v", type=HexString, required=True, help="Key value as a hex string")

        dfu_parser = tool_parser.add_parser("dfu", help="Manage device firmware upgrades")
        dfu_parser.set_defaults(command_fn=cls.dfu)
        dfu_device = dfu_parser.add_mutually_exclusive_group(required=True)
        dfu_device.add_argument("--id", type=InfuseDeviceId, help="Infuse-IoT device ID")
        dfu_device.add_argument(
            "--list",
            type=ValidFile,
            help="File containing a list of Infuse-IoT device IDs, one per line",
        )
        dfu_action = dfu_parser.add_mutually_exclusive_group(required=True)
        dfu_action.add_argument("--schedule", type=str, help="Release ID to upgrade to")
        dfu_action.add_argument("--status", action="store_true", help="Check DFU status")
        dfu_action.add_argument("--cancel", action="store_true", help="Cancel pending DFU")

        logger_parser = tool_parser.add_parser("logger", help="Configure logger download state")
        logger_parser.set_defaults(command_fn=cls.logger)
        logger_parser.add_argument("--id", type=InfuseDeviceId, required=True, help="Infuse-IoT device ID")
        control_action = logger_parser.add_mutually_exclusive_group(required=True)
        control_action.add_argument("--enable", action="store_true", help="Enable logger download")
        control_action.add_argument("--disable", action="store_true", help="Disable logger download")
        logger_choice = logger_parser.add_mutually_exclusive_group(required=True)
        logger_choice.add_argument(
            "--onboard", dest="logger_idx", action="store_const", const=0, help="Onboard flash logger"
        )

    @staticmethod
    def _val_or_na(value) -> str:
        if isinstance(value, Unset):
            return "N/A"
        return str(value)

    def info(self, client: Client):
        id_str = f"{self.args.id:016x}"
        info = check_api_response(get_device_by_device_id.sync_detailed(client=client, device_id=id_str), "Get device")
        metadata: list[tuple[str, Any]] = []
        if info.metadata:
            metadata = [(f"Metadata.{k}", v) for k, v in info.metadata.additional_properties.items()]

        # Supplementary information, displayed only if available
        accepted_errors = [HTTPStatus.NOT_FOUND, HTTPStatus.FORBIDDEN]
        org = check_api_response_allow_errors(
            get_organisation_by_id.sync_detailed(client=client, id=info.organisation_id),
            "Get organisation",
            accepted_errors,
        )
        board = check_api_response_allow_errors(
            get_board_by_id.sync_detailed(client=client, id=info.board_id), "Get board", accepted_errors
        )
        state = check_api_response_allow_errors(
            get_device_state_by_id.sync_detailed(client=client, id=info.id), "Get device state", accepted_errors
        )
        route = check_api_response_allow_errors(
            get_device_last_route_by_device_id.sync_detailed(client=client, device_id=id_str),
            "Get device route",
            accepted_errors,
        )
        app = check_api_response_allow_errors(
            get_device_application_state_by_device_id.sync_detailed(client=client, device_id=id_str),
            "Get device application state",
            accepted_errors,
        )
        logger_states = check_api_response_allow_errors(
            get_device_logger_states_by_device_id.sync_detailed(client=client, device_id=id_str),
            "Get device logger states",
            accepted_errors,
        )

        table: list[tuple[str, Any]] = [
            ("Infuse ID", id_str),
            ("UUID", info.id),
            ("MCU ID", info.mcu_id),
            (
                "Organisation",
                f"{info.organisation_id} ({org.name if isinstance(org, models.Organisation) else 'Unknown'})",
            ),
            ("Board", f"{info.board_id} ({board.name if isinstance(board, models.Board) else 'Unknown'})"),
            ("Created", info.created_at),
            ("Updated", info.updated_at),
            *metadata,
        ]
        if isinstance(state, models.DeviceState):
            v = state.application_version

            table += [
                ("~~~State~~~", ""),
                ("Updated", state.updated_at),
            ]
            if state.application_id:
                table += [("Application ID", f"0x{state.application_id:08x}")]
            if v:
                table += [("Version", f"{v.major}.{v.minor}.{v.revision}+{v.build_num:08x}")]
            if isinstance(app, models.DeviceApplicationState):
                table += [("Release ID", app.release_id if app.release_id else "N/A")]
        if isinstance(route, models.UplinkRoute):
            table += [
                ("~~~Latest Route~~~", ""),
                ("Interface", route.interface.upper()),
            ]
            if route.forwarded:
                table += [("Forwarded From", f"{route.forwarded.device_id} ({route.forwarded.rssi} dBm)")]
            if route.bt_adv:
                table += [("BT Address", f"{route.bt_adv.address} ({route.bt_adv.type_})")]
            if route.udp:
                table += [("IP Address", route.udp.address)]
        if isinstance(state, models.DeviceState) and state.last_route_udp_time:
            table += [
                ("~~~Latest UDP~~~", ""),
            ]
            table += [("Latest Packet", state.last_route_udp_time)]
            table += [("IP Address", self._val_or_na(state.last_route_udp_address))]
        if isinstance(logger_states, list) and len(logger_states) > 0:
            for logger in logger_states:
                name = self.logger_names.get(logger.index, str(logger.index))
                table += [
                    (f"~~~{name} Logger Sync~~~", ""),
                    ("Enabled", logger.download_enabled),
                    ("Last Report Time", self._val_or_na(logger.last_reported_time)),
                    ("Last Downloaded Time", self._val_or_na(logger.last_downloaded_time)),
                    ("Reported Block", self._val_or_na(logger.last_reported_block)),
                    ("Downloaded Block", self._val_or_na(logger.last_downloaded_block)),
                ]
                if isinstance(logger.last_reported_block, int) and isinstance(logger.last_downloaded_block, int):
                    table += [("Block Lag", logger.last_reported_block - logger.last_downloaded_block)]

        print(tabulate(table))

    def _kv_display(self, table: list[tuple[str, str, Any]], key_val: str, name_base: str, dictionary: dict):
        for name, value in dictionary.items():
            if isinstance(value, dict):
                self._kv_display(table, key_val, f"{name_base}.{name}", value)
            else:
                table.append((key_val, f"{name_base}.{name}", value))
            key_val = ""

    def kv_state(self, client: Client):
        id_str = f"{self.args.id:016x}"

        kv_state = check_api_response(
            get_device_kv_entries_by_device_id.sync_detailed(client=client, device_id=id_str), "Get KV state"
        )

        table: list[tuple[str, str, Any]] = []
        for element in kv_state:
            key = element.key_name if isinstance(element.key_name, str) else ""
            key_id = str(element.key_id)

            # Don't display some keys unless explicitly requested
            if key == "TASK_SCHEDULES" and not self.args.schedules:
                continue
            if key == "Z_DEVSTATE" and not self.args.devstate:
                continue

            if isinstance(element.data, Unset):
                if element.crc:
                    table.append((key_id, key, f"Write-only (CRC: 0x{element.crc:08x})"))
                else:
                    table.append((key_id, key, "Not set"))
            else:
                if self.args.hex:
                    table.append((key_id, key, base64.b64decode(element.data).hex()))
                elif self.args.base64:
                    table.append((key_id, key, element.data))
                else:
                    if isinstance(element.decoded, Unset):
                        table.append((key_id, key, element.data))
                    else:
                        self._kv_display(table, key_id, key, element.decoded.additional_properties)

        print(tabulate(table))

    def kv_update(self, client: Client):
        id_str = f"{self.args.id:016x}"

        val_encoded = base64.b64encode(self.args.val).decode("utf-8")
        update = models.NewDeviceKVEntryUpdate(data=val_encoded)

        # Checked here as mypy cannot infer `check_api_response` for responses with multiple success types
        rsp = create_device_kv_entry_update_by_device_id_and_key_id.sync_detailed(
            client=client,
            device_id=id_str,
            key_id=self.args.key,
            body=update,
        )
        if isinstance(rsp.parsed, models.DeviceKVEntry):
            print(f"Device {id_str} key {self.args.key} already has value {self.args.val.hex()}")
        elif isinstance(rsp.parsed, models.DeviceKVEntryUpdate):
            print(f"Device {id_str} update scheduled with ID {rsp.parsed.id}")
        else:
            sys.exit(f"KV update: {format_api_error(rsp)}")

    def dfu(self, client: Client):
        if self.args.id is not None:
            device_ids = [self.args.id]
        else:
            assert self.args.list is not None
            with self.args.list.open(encoding="utf-8") as f:
                device_ids = [InfuseDeviceId(line.strip()) for line in f]

        for device_id in device_ids:
            self._dfu_device(client, device_id)

    def _dfu_device(self, client: Client, device_id: int):
        id_str = f"{device_id:016x}"

        if self.args.schedule:
            body = models.NewDeviceApplicationUpdate(self.args.schedule)
            # Failures specific to this device, report and continue with the remaining devices
            rsp = create_device_application_update_by_device_id.sync_detailed(
                client=client, device_id=id_str, body=body
            )
            if isinstance(rsp.parsed, models.DeviceApplicationState):
                print(f"{id_str}: Device already on release {self.args.schedule}")
            elif isinstance(rsp.parsed, models.DeviceApplicationUpdate):
                print(f"{id_str}: DFU scheduled with ID {rsp.parsed.id}")
            else:
                print(f"{id_str}: Create application update: {format_api_error(rsp)}")
        elif self.args.status:
            # Failures specific to this device, report and continue with the remaining devices
            updates_rsp = get_device_application_updates_by_device_id.sync_detailed(
                client=client,
                device_id=id_str,
            )
            if not isinstance(updates_rsp.parsed, list):
                print(f"{id_str}: Get application updates: {format_api_error(updates_rsp)}")
                return
            updates = updates_rsp.parsed

            for update in updates:
                print(
                    tabulate(
                        [
                            ["DFU ID", str(update.id)],
                            ["To Release", update.release_id],
                            ["Status", str(update.status)],
                            ["Attempts", str(update.attempt_count)],
                            ["Last Attempt", self._val_or_na(update.last_attempt_at)],
                            ["Completed", self._val_or_na(update.completed_at)],
                        ]
                    )
                )
        elif self.args.cancel:
            # Failures specific to this device, report and continue with the remaining devices
            cancel_rsp = cancel_pending_device_application_updates_by_device_id.sync_detailed(
                client=client,
                device_id=id_str,
            )
            if isinstance(cancel_rsp.parsed, models.DeviceApplicationUpdate):
                print(f"{id_str}: Cancelled DFU {cancel_rsp.parsed.id} to release {cancel_rsp.parsed.release_id}")
            elif cancel_rsp.status_code == HTTPStatus.NO_CONTENT:
                print(f"{id_str}: No pending DFU")
            else:
                print(f"{id_str}: Cancel application update: {format_api_error(cancel_rsp)}")
        else:
            raise NotImplementedError("Unknown DFU subcommand")

    def logger(self, client: Client):
        id_str = f"{self.args.id:016x}"

        resp = check_api_response(
            update_device_logger_state_by_device_id_and_index.sync_detailed(
                client=client,
                device_id=id_str,
                index=self.args.logger_idx,
                body=models.DeviceLoggerStateUpdate(self.args.enable),
            ),
            "Update logger state",
        )
        name = self.logger_names.get(self.args.logger_idx, str(self.args.logger_idx))
        table = [
            (f"~~~{name} Logger Sync~~~", ""),
            ("Enabled", resp.download_enabled),
            ("Last Report Time", self._val_or_na(resp.last_reported_time)),
            ("Last Downloaded Time", self._val_or_na(resp.last_downloaded_time)),
            ("Reported Block", self._val_or_na(resp.last_reported_block)),
            ("Downloaded Block", self._val_or_na(resp.last_downloaded_block)),
        ]
        if isinstance(resp.last_reported_block, int) and isinstance(resp.last_downloaded_block, int):
            table += [("Block Lag", resp.last_reported_block - resp.last_downloaded_block)]

        print(tabulate(table))
