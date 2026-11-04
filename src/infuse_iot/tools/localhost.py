#!/usr/bin/env python3

"""Run a local server for TDF viewing"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

import asyncio
import pathlib
import sys
from typing import Any

from aiohttp import web
from aiohttp.client_exceptions import WSMessageTypeError
from aiohttp.web_request import BaseRequest
from aiohttp.web_runner import GracefulExit

from infuse_iot.commands import InfuseCommand
from infuse_iot.definitions.tdf import structs
from infuse_iot.services.device_state import DeviceState
from infuse_iot.socket_comms import (
    ClientNotificationEpacketReceived,
    LocalClient,
)
from infuse_iot.util.argparse import add_server_port_parser
from infuse_iot.util.console import Console
from infuse_iot.util.threading import SignaledThread


class SubCommand(InfuseCommand):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--port", "-p", type=int, default=8080, help="Port number for localhost server")
        add_server_port_parser(parser)

    def __init__(self, args):
        self._state = DeviceState()
        self._data_lock = self._state.lock
        self._columns: dict[str, dict] = {}
        self._data = self._state.display_rows
        self._port: int = args.port
        self._client = LocalClient(args.server_sock, 1.0)

    # Serve the HTML file
    async def handle_index(self, _request):
        this_folder = pathlib.Path(__file__).parent

        return web.FileResponse(this_folder / "localhost" / "index.html")

    def websocket_message(self) -> dict:
        with self._data_lock:
            columns = [
                {
                    "title": "Metadata",
                    "headerHozAlign": "center",
                    "frozen": True,
                    "columns": [
                        {
                            "title": "Device",
                            "field": "infuse_id",
                            "headerHozAlign": "center",
                        },
                        {
                            "title": "App ID",
                            "field": "application",
                            "headerHozAlign": "center",
                        },
                        {
                            "title": "Network",
                            "field": "network_id",
                            "headerHozAlign": "center",
                        },
                        {
                            "title": "Last Heard",
                            "field": "time",
                            "headerHozAlign": "center",
                        },
                        {
                            "title": "Bluetooth",
                            "headerHozAlign": "center",
                            "columns": [
                                {
                                    "title": "Address",
                                    "field": "bt_addr",
                                    "headerHozAlign": "center",
                                },
                                {
                                    "title": "RSSI (dBm)",
                                    "field": "bt_rssi",
                                    "headerVertical": "flip",
                                    "hozAlign": "right",
                                },
                            ],
                        },
                    ],
                }
            ]
            # Put the announce TDFs first for clarity
            priorities = {"ANNOUNCE_V2": 0, "ANNOUNCE": 1}
            sorted_tdfs = sorted(self._columns, key=lambda x: priorities.get(x, 2))

            for tdf_name in sorted_tdfs:
                columns.append(
                    {
                        "title": tdf_name,
                        "field": tdf_name,
                        "columns": self._columns[tdf_name],
                        "headerHozAlign": "center",
                    }
                )
            devices = sorted(self._data.keys())
            rows = [self._data[d] for d in devices]
            # Filter options are the values present in the rows, so every row can be shown
            message = {
                "columns": columns,
                "rows": rows,
                "tdfs": sorted(list(self._columns.keys())),
                "apps": sorted({r["application"] for r in rows}),
                "networks": sorted({r["network_id"] for r in rows}),
            }
        return message

    async def websocket_handler(self, request: BaseRequest):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        Console.log_info(f"Websocket client connected ({request.remote})")

        try:
            while True:
                # Wait for request from browser (contents don't matter)
                _ = await ws.receive_str()

                # Data sent to the client
                message = self.websocket_message()

                await ws.send_json(message)

        except (asyncio.CancelledError, ConnectionResetError, WSMessageTypeError):
            pass
        finally:
            await ws.close()

        Console.log_info(f"Websocket client disconnected ({request.remote})")
        return ws

    def tdf_columns(self, tdf):
        out = []

        def column_title(struct, name):
            postfix = struct._postfix_[name]
            if postfix != "":
                return f"{name} ({postfix})"
            return name

        for field in tdf.field_information():
            if field["type"] == structs.tdf_struct_mcuboot_img_sem_ver:
                # Special case version struct to make reading versions easier
                s = {
                    "title": column_title(tdf, field["name"]),
                    "field": f"{tdf.NAME}.{field['name']}",
                    "headerVertical": "flip",
                    "hozAlign": "right",
                }
            elif "subfields" in field:
                sub: list[dict[str, Any]] = []
                for subfield in field["subfields"]:
                    sub.append(
                        {
                            "title": column_title(field["type"], subfield["name"]),
                            "field": f"{tdf.NAME}.{field['name']}.{subfield['name']}",
                            "headerVertical": "flip",
                            "hozAlign": "right",
                        }
                    )
                s = {"title": field["name"], "headerHozAlign": "center", "columns": sub}
            else:
                s = {
                    "title": column_title(tdf, field["name"]),
                    "field": f"{tdf.NAME}.{field['name']}",
                    "headerVertical": "flip",
                    "hozAlign": "right",
                }
            out.append(s)
        return out

    def recv_thread(self) -> None:
        msg = self._client.receive()
        if isinstance(msg, ClientNotificationEpacketReceived) and self._state.observe(msg.epacket):
            with self._data_lock:
                for name, reading in self._state.tdf_types.items():
                    if name not in self._columns:
                        self._columns[name] = self.tdf_columns(reading)

    def run(self):
        if not self._client.comms_check():
            sys.exit("No communications gateway detected (infuse gateway/bt_native)")

        Console.init()
        app = web.Application()
        # Route for serving the HTML file
        app.router.add_get("/", self.handle_index)
        # Route for WebSocket
        app.router.add_get("/ws", self.websocket_handler)

        rx_thread = SignaledThread(self.recv_thread)
        rx_thread.start()

        # Run server
        try:
            web.run_app(app, host="localhost", port=self._port)
        except GracefulExit:
            pass
        finally:
            rx_thread.stop()
        rx_thread.join(1.0)

    def close(self):
        self._client.close()
