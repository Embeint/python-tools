#!/usr/bin/env python3

"""Run a local server for TDF viewing"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Inc"

import asyncio
import ctypes
import pathlib
import threading
import time
from aiohttp import web
from aiohttp.web_request import BaseRequest
from aiohttp.web_runner import GracefulExit

from infuse_iot.util.console import Console
from infuse_iot.epacket import InfuseType, Interface
from infuse_iot.commands import InfuseCommand
from infuse_iot.socket_comms import LocalClient, default_multicast_address
from infuse_iot.tdf import TDF
from infuse_iot.time import InfuseTime


class SubCommand(InfuseCommand):
    NAME = "localhost"
    HELP = "Run a local server for TDF viewing"
    DESCRIPTION = "Run a local server for TDF viewing"

    def __init__(self, _):
        self._data_lock = threading.Lock()
        self._columns = {}
        self._data = {}

        self._thread_end = threading.Event()
        self._client = LocalClient(default_multicast_address(), 1.0)
        self._decoder = TDF()

    # Serve the HTML file
    async def handle_index(self, request):
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
                for tdf_name in sorted(self._columns):
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
        for field in tdf._fields_:
            if field[0][0] == "_":
                f_name = field[0][1:]
            else:
                f_name = field[0]
            val = getattr(tdf, f_name)
            if isinstance(val, ctypes.LittleEndianStructure):
                c = []
                for subfield_name, _, postfix, _ in val.iter_fields():
                    if postfix != "":
                        title = f"{subfield_name} ({postfix})"
                    else:
                        title = subfield_name
                    c.append(
                        {
                            "title": title,
                            "field": f"{tdf.name}.{f_name}.{subfield_name}",
                            "headerVertical": "flip",
                            "hozAlign": "right",
                        }
                    )
                s = {"title": f_name, "headerHozAlign": "center", "columns": c}
            else:
                if tdf._postfix_[f_name] != "":
                    title = f"{f_name} ({tdf._postfix_[f_name]})"
                else:
                    title = f_name

                s = {
                    "title": title,
                    "field": f"{tdf.name}.{f_name}",
                    "headerVertical": "flip",
                    "hozAlign": "right",
                }
            out.append(s)
        return out

    def recv_thread(self):
        while True:
            msg = self._client.receive()
            if self._thread_end.is_set():
                break
            if msg is None:
                continue
            if msg.ptype != InfuseType.TDF:
                continue

            decoded = self._decoder.decode(msg.payload)
            source = msg.route[0]

            self._data_lock.acquire(blocking=True)

            if source.infuse_id not in self._data:
                self._data[source.infuse_id] = {
                    "infuse_id": f"0x{source.infuse_id:016x}",
                }
            self._data[source.infuse_id]["time"] = InfuseTime.utc_time_string(
                time.time()
            )
            if source.interface == Interface.BT_ADV:
                addr_bytes = source.interface_address.val.addr_val.to_bytes(6, "big")
                addr_str = ":".join([f"{x:02x}" for x in addr_bytes])
                self._data[source.infuse_id]["bt_addr"] = addr_str
                self._data[source.infuse_id]["bt_rssi"] = source.rssi

            for tdf in decoded:
                t = tdf.data[-1]
                if t.name not in self._columns:
                    self._columns[t.name] = self.tdf_columns(t)

                for n, f, _, d in t.iter_fields():
                    f = d.format(f)
                    if t.name not in self._data[source.infuse_id]:
                        self._data[source.infuse_id][t.name] = {}
                    if "." in n:
                        struct, sub = n.split(".")
                        if struct not in self._data[source.infuse_id][t.name]:
                            self._data[source.infuse_id][t.name][struct] = {}
                        self._data[source.infuse_id][t.name][struct][sub] = f

                    self._data[source.infuse_id][t.name][n] = f

            self._data_lock.release()

    def run(self):
        Console.init()
        app = web.Application()
        # Route for serving the HTML file
        app.router.add_get("/", self.handle_index)
        # Route for WebSocket
        app.router.add_get("/ws", self.websocket_handler)

        rx_thread = threading.Thread(target=self.recv_thread)
        rx_thread.start()

        # Run server
        try:
            web.run_app(app, host="localhost", port=8080)
        except GracefulExit:
            self._thread_end.set()
        rx_thread.join(1.0)
