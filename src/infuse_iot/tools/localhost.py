#!/usr/bin/env python3

"""Run a local server for TDF viewing"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

import asyncio
import pathlib
import threading
import time
from typing import Any

from aiohttp import web
from aiohttp.web_request import BaseRequest
from aiohttp.web_runner import GracefulExit

import infuse_iot.epacket.interface as interface
from infuse_iot.commands import InfuseCommand
from infuse_iot.common import InfuseType
from infuse_iot.definitions.tdf import structs
from infuse_iot.generated.tdf_base import TdfStructBase
from infuse_iot.socket_comms import (
    ClientNotificationEpacketReceived,
    LocalClient,
    default_multicast_address,
)
from infuse_iot.tdf import TDF
from infuse_iot.time import InfuseTime
from infuse_iot.util.console import Console
from infuse_iot.util.threading import SignaledThread


class SubCommand(InfuseCommand):
    NAME = "localhost"
    HELP = "Run a local server for TDF viewing"
    DESCRIPTION = "Run a local server for TDF viewing"

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--port", "-p", type=int, default=8080, help="Port number for localhost server")

    def __init__(self, args):
        self._data_lock = threading.Lock()
        self._columns: dict[str, dict] = {}
        self._data: dict[int, dict] = {}
        self._port: int = args.port

        self._client = LocalClient(default_multicast_address(), 1.0)
        self._decoder = TDF()

    # Serve the HTML file
    async def handle_index(self, _request):
        this_folder = pathlib.Path(__file__).parent

        return web.FileResponse(this_folder / "localhost" / "index.html")

    async def websocket_handler(self, request: BaseRequest):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        Console.log_info(f"Websocket client connected ({request.remote})")

        try:
            while True:
                # Example data sent to the client
                self._data_lock.acquire(blocking=True)
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
                # Put ANNOUNCE TDF first, if it exists
                if "ANNOUNCE" in self._columns:
                    sorted_tdfs = ["ANNOUNCE"] + [v for v in sorted(self._columns) if v != "ANNOUNCE"]
                else:
                    sorted_tdfs = sorted(self._columns)

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
                message = {
                    "columns": columns,
                    "rows": [self._data[d] for d in devices],
                    "tdfs": list(self._columns.keys()),
                }
                self._data_lock.release()

                await ws.send_json(message)
                await asyncio.sleep(1)
        except (asyncio.CancelledError, ConnectionResetError):
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
        if msg is None:
            return
        if not isinstance(msg, ClientNotificationEpacketReceived):
            return
        if msg.epacket.ptype != InfuseType.TDF:
            return

        source = msg.epacket.route[0]

        self._data_lock.acquire(blocking=True)

        if source.infuse_id not in self._data:
            self._data[source.infuse_id] = {
                "infuse_id": f"0x{source.infuse_id:016x}",
            }
            # Set default application ID
            self._data[source.infuse_id]["ANNOUNCE"] = {"application": "Unknown"}

        self._data[source.infuse_id]["time"] = InfuseTime.utc_time_string(time.time())
        if source.interface == interface.ID.BT_ADV:
            addr_bytes = source.interface_address.val.addr_val.to_bytes(6, "big")
            addr_str = ":".join([f"{x:02x}" for x in addr_bytes])
            self._data[source.infuse_id]["bt_addr"] = addr_str
            self._data[source.infuse_id]["bt_rssi"] = source.rssi

        for tdf in self._decoder.decode(msg.epacket.payload):
            t = tdf.data[-1]
            if t.NAME not in self._columns:
                self._columns[t.NAME] = self.tdf_columns(t)
            if t.NAME not in self._data[source.infuse_id]:
                self._data[source.infuse_id][t.NAME] = {}

            for field in t.iter_fields(nested_iter=False):
                if isinstance(field.val, structs.tdf_struct_mcuboot_img_sem_ver):
                    # Special case version struct to make reading versions easier
                    val = f"{field.val.major}.{field.val.minor}.{field.val.revision}+{field.val.build_num:08x}"
                    self._data[source.infuse_id][t.NAME][field.field] = val
                elif isinstance(field.val, TdfStructBase):
                    for s in field.val.iter_fields(field.field):
                        if s.field not in self._data[source.infuse_id][t.NAME]:
                            self._data[source.infuse_id][t.NAME][s.field] = {}
                        self._data[source.infuse_id][t.NAME][s.field][s.subfield] = s.val_fmt()
                else:
                    self._data[source.infuse_id][t.NAME][field.field] = field.val_fmt()
        self._data_lock.release()

    def run(self):
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
