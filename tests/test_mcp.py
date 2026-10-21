"""Exercise the MCP tools against fake gateways, in process and through the installed stdio command."""

import asyncio
import ctypes
import json
import os
import queue
import shutil
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp", reason="Install the MCP extra to run protocol integration tests")
from mcp import Client
from mcp.client.stdio import StdioServerParameters

import infuse_iot.definitions.rpc as defs
import infuse_iot.mcp_server.server as mcp_server
from infuse_iot.common import InfuseType
from infuse_iot.definitions.tdf import readings, structs
from infuse_iot.epacket import interface
from infuse_iot.epacket.packet import Auth, HopReceived, PacketReceived
from infuse_iot.mcp_server.server import ReadParameters, ReadService, create_server
from infuse_iot.services.device_operations import READ_COMMANDS, READ_KEYS
from infuse_iot.socket_comms import ClientNotificationEpacketReceived, default_multicast_address
from infuse_iot.tdf import TDF

DEVICE = 0xCE7E42571A000099
DEVICE_ID = f"0x{DEVICE:016x}"
TOOLS = {"infuse_status", "infuse_scan", "infuse_devices", "infuse_device", "infuse_rpc_read", "infuse_diagnostics"}


def packet(device: int = DEVICE) -> PacketReceived:
    reading = readings.announce(0xCE710003, structs.tdf_struct_mcuboot_img_sem_ver(1, 3, 1, 0x7BEE09D5), 0, 0, 10, 0, 0)
    payload = bytes(TDF.CoreHeader(reading.ID, ctypes.sizeof(reading))) + bytes(reading)
    address = interface.Address(interface.Address.BluetoothLeAddr(0, 0x60FCF1006161))
    hop = HopReceived(device, interface.ID.BT_ADV, address, Auth.NETWORK, 0xCE7E50, 0, 0, -65)
    return PacketReceived([hop], InfuseType.TDF, payload)


def application_info() -> bytes:
    version = defs.rpc_struct_mcuboot_img_sem_ver(1, 3, 1, 0x7BEE09D5)
    return bytes(defs.application_info.response(0xCE710003, version, 0xCE7E50, 100, 3, 0xABC, 1, 2))


def run(service: ReadService, calls):
    """Run `calls(client)` against an in-process server for `service`."""

    async def main():
        async with Client(create_server(service.address, service)) as client:
            return await calls(client)

    return asyncio.run(main())


def error(result) -> dict[str, Any]:
    assert result.is_error
    return result.structured_content["error"]


def data(result) -> dict[str, Any]:
    assert not result.is_error, result.structured_content
    return result.structured_content["data"]


def test_catalog_publishes_strict_inputs_and_typed_outputs():
    async def calls(client):
        return (await client.list_tools()).tools

    tools = {tool.name: tool for tool in run(ReadService(default_multicast_address(28911)), calls)}
    assert set(tools) == TOOLS
    for tool in tools.values():
        assert tool.annotations and tool.annotations.read_only_hint
        assert tool.input_schema["additionalProperties"] is False
        assert tool.output_schema["properties"]["data"]
    # Results are typed beyond the envelope
    assert "firmware_age_seconds" in json.dumps(tools["infuse_devices"].output_schema)
    assert "window_counters" in json.dumps(tools["infuse_diagnostics"].output_schema)
    command = tools["infuse_rpc_read"].input_schema["properties"]["command"]
    assert tuple(command["enum"]) == READ_COMMANDS
    keys = ReadParameters.model_json_schema()["properties"]["keys"]["anyOf"][0]["items"]["enum"]
    assert tuple(keys) == READ_KEYS
    assert tools["infuse_device"].input_schema["properties"]["device_id"]["pattern"] == "^(0x)?[0-9a-fA-F]{1,16}$"


def test_every_failure_is_a_structured_error():
    cases = [
        ("infuse_rpc_read", {"device_id": "0x123", "command": "reboot"}, "invalid_request", False),
        (
            "infuse_rpc_read",
            {"device_id": "0x1", "command": "kv_read", "parameters": {"keys": ["X"]}},
            "invalid_request",
            False,
        ),
        (
            "infuse_rpc_read",
            {"device_id": "0x1", "command": "application_info", "parameters": {"keys": ["REBOOTS"]}},
            "invalid_request",
            False,
        ),
        ("infuse_devices", {"limit": "many"}, "invalid_request", False),
        ("infuse_devices", {"application": "0x2"}, "invalid_request", False),
        ("infuse_devices", {"ids": ["12_34"]}, "invalid_request", False),
        ("infuse_device", {"device_id": " 12_34 "}, "invalid_request", False),
        ("infuse_device", {"device_id": "١٢"}, "invalid_request", False),
        ("infuse_device", {"device_id": "0x1", "fields": ["announce"]}, "invalid_request", False),
        ("infuse_missing", {}, "unknown_tool", False),
        # No gateway answers on this port
        ("infuse_rpc_read", {"device_id": "0x123", "command": "application_info"}, "gateway_unavailable", True),
        ("infuse_devices", {}, "gateway_unavailable", True),
        ("infuse_scan", {"duration_seconds": 0.1}, "gateway_unavailable", True),
    ]

    async def calls(client):
        return [await client.call_tool(name, arguments) for name, arguments, _, _ in cases]

    results = run(ReadService(default_multicast_address(28913)), calls)
    for (name, arguments, code, retryable), result in zip(cases, results, strict=True):
        failure = error(result)
        assert (failure["code"], failure["retryable"]) == (code, retryable), (name, arguments, failure)
        assert json.loads(result.content[0].text)["error"] == failure
    assert error(results[4])["details"]["fields"] == ["application"]
    assert error(results[3])["details"]["fields"] == ["limit"]


def test_unexpected_failures_do_not_leak_details(monkeypatch):
    def broken(self, **query):
        raise FileNotFoundError("/private/secret/path")

    monkeypatch.setattr(ReadService, "devices", broken)

    async def calls(client):
        return await client.call_tool("infuse_devices")

    failure = error(run(ReadService(default_multicast_address(28915)), calls))
    assert (failure["code"], failure["retryable"]) == ("internal_error", False)
    assert "secret" not in json.dumps(failure)


def test_gateway_error_codes_are_preserved(loopback_gateway):
    gateway = loopback_gateway(28917)

    async def calls(client):
        expired = await client.call_tool("infuse_devices", {"cursor": "0123:1"})
        invalid = await client.call_tool("infuse_devices", {"cursor": "no-offset"})
        return expired, invalid

    expired, invalid = run(ReadService(gateway.address), calls)
    assert (error(expired)["code"], error(expired)["retryable"]) == ("snapshot_expired", False)
    assert error(invalid)["code"] == "invalid_cursor"


def test_collector_attaches_to_a_gateway_started_later(device_gateway, monkeypatch):
    address = default_multicast_address(28919)
    service = ReadService(address)
    gateways = []

    async def calls(client):
        absent = await client.call_tool("infuse_devices")
        status = data(await client.call_tool("infuse_status"))
        assert not status["gateway"]["available"] and not status["collector"]["running"]
        assert status["collector"]["error_code"] == "gateway_unavailable"
        gateways.append(device_gateway(28919))
        # Attached on demand, rather than waiting for the background retry
        assert data(await client.call_tool("infuse_devices"))["total"] == 0
        gateways[0].server.broadcast(ClientNotificationEpacketReceived(packet()))
        await asyncio.sleep(0.3)
        page = data(await client.call_tool("infuse_devices", {"fields": ["ANNOUNCE"]}))
        assert page["items"][0]["firmware_version"] == "1.3.1+7bee09d5"
        # A failed socket stops the worker, and the next call attaches again keeping the state
        attached = service.collector._client
        assert attached is not None

        def failing(timeout=None):
            raise OSError(9, "Bad file descriptor")

        monkeypatch.setattr(attached, "receive", failing)
        await asyncio.sleep(0.5)
        assert not service.collector.running
        page = data(await client.call_tool("infuse_devices"))
        status = data(await client.call_tool("infuse_status"))
        return absent, page, status

    absent, page, status = run(service, calls)
    assert (error(absent)["code"], error(absent)["retryable"]) == ("gateway_unavailable", True)
    assert page["items"][0]["id"] == DEVICE_ID
    assert status["gateway"]["available"] and status["collector"]["running"]
    assert status["collector"]["devices"] == 1 and status["collector"]["error"] is None


def test_background_attach_collects_before_the_first_call(device_gateway):
    address = default_multicast_address(28921)
    service = ReadService(address)
    service.attach_interval = 0.1

    async def calls(client):
        gateway = device_gateway(28921)
        for _ in range(50):
            if service.collector.running:
                break
            await asyncio.sleep(0.1)
        gateway.server.broadcast(ClientNotificationEpacketReceived(packet()))
        await asyncio.sleep(0.3)
        return data(await client.call_tool("infuse_device", {"device_id": DEVICE_ID}))

    result = run(service, calls)
    assert result["device"]["id"] == DEVICE_ID


def test_pages_report_a_replaced_gateway(loopback_gateway):
    address = default_multicast_address(28963)
    service = ReadService(address)
    service.attach_interval = 0.1

    async def calls(client):
        first = loopback_gateway(28963)
        page = data(await client.call_tool("infuse_devices"))
        assert page["gateway"]["instance_id"] == first.server.control.instance_id
        # The collector's socket survives the restart, so only a probe reveals the new gateway.
        first.close()
        second = loopback_gateway(28963)
        second.server.control.kind = "native_bt"
        for _ in range(50):
            page = data(await client.call_tool("infuse_devices"))
            if page["gateway"]["instance_id"] == second.server.control.instance_id:
                break
            await asyncio.sleep(0.1)
        assert service.collector.running
        return page["gateway"], second.server.control.instance_id

    gateway, instance = run(service, calls)
    assert (gateway["instance_id"], gateway["gateway_kind"]) == (instance, "native_bt")


def test_rpc_reads_through_a_gateway(device_gateway):
    local = 0xABCD0001
    gateway = device_gateway(28923, local_device=local)

    def respond(device, command, request):
        if command == defs.kv_read.COMMAND_ID:
            return 0, struct.pack("<HhI", 0, 4, 7) + struct.pack("<Hh", 4, -2)
        if device == 0x99:
            return 0, b"\x01"
        return 0, application_info()

    gateway.respond = respond

    async def calls(client):
        kv = await client.call_tool(
            "infuse_rpc_read",
            {"device_id": DEVICE_ID, "command": "kv_read", "parameters": {"keys": ["REBOOTS", "DEVICE_NAME"]}},
        )
        info = [
            await client.call_tool("infuse_rpc_read", {"device_id": f"0x{target:x}", "command": "application_info"})
            for target in (local, local, DEVICE)
        ]
        malformed = await client.call_tool("infuse_rpc_read", {"device_id": "0x99", "command": "application_info"})
        return kv, info, malformed

    kv, info, malformed = run(ReadService(gateway.address), calls)
    values = data(kv)["response"]["values"]
    assert values[0]["value"] == {"count": 7}
    assert values[1]["status"] == "not_set"
    assert [data(result)["response"]["version"] for result in info] == ["1.3.1+7bee09d5"] * 3
    assert error(malformed)["code"] == "device_response_invalid"


def test_busy_read_fails_promptly_and_other_tools_still_answer(device_gateway):
    gateway = device_gateway(28925)
    service = ReadService(gateway.address)
    service.operations.busy_wait_seconds = 2.0
    held, release = threading.Event(), threading.Event()

    def long_operation():
        with service.operations.exclusive():
            held.set()
            release.wait(10)

    worker = threading.Thread(target=long_operation)
    worker.start()
    held.wait(5)

    async def calls(client):
        async def status():
            await asyncio.sleep(0.1)
            start = time.monotonic()
            result = await client.call_tool("infuse_status", read_timeout_seconds=10)
            return result, time.monotonic() - start

        start = time.monotonic()
        read = {"device_id": DEVICE_ID, "command": "application_info"}
        *reads, (state, answered) = await asyncio.gather(
            *[client.call_tool("infuse_rpc_read", read) for _ in range(40)], status()
        )
        return reads, time.monotonic() - start, state, answered

    try:
        reads, elapsed, status, answered = run(service, calls)
    finally:
        release.set()
        worker.join()
    assert {(error(read)["code"], error(read)["retryable"]) for read in reads} == {("device_busy", True)}
    # Only two reads wait for the lock, so the other tools keep their worker threads
    assert elapsed < 5
    assert answered < 1.5
    assert data(status)["gateway"]["available"]


def test_lookups_do_not_evict_device_cursors(loopback_gateway):
    gateway = loopback_gateway(28927)
    service = ReadService(gateway.address)
    for index in range(60):
        service.collector.state.observe(packet(DEVICE + index))

    async def calls(client):
        first = data(await client.call_tool("infuse_devices", {"limit": 50}))
        for row in first["items"][:10]:
            data(await client.call_tool("infuse_device", {"device_id": row["id"]}))
            data(await client.call_tool("infuse_diagnostics", {"device_ids": [row["id"]]}))
        second = data(await client.call_tool("infuse_devices", {"limit": 50, "cursor": first["next_cursor"]}))
        return first, second

    first, second = run(service, calls)
    assert first["total"] == 60 and len(second["items"]) == 10


def test_device_age_limit_is_explicit(monkeypatch):
    service = ReadService(default_multicast_address(28929))
    # Use the collected state as if attached, as the clock below is frozen
    monkeypatch.setattr(service, "attach", lambda: service.collector.state)
    now = [1000.0]
    monkeypatch.setattr("infuse_iot.services.device_state.time.monotonic", lambda: now[0])
    service.collector.state.observe(packet())
    now[0] += 130
    result = service.device(DEVICE_ID)
    assert result["max_age_seconds"] is None
    assert result["device"]["age_seconds"] == 130
    assert result["device"]["firmware_age_seconds"] == 130
    assert result["device"]["firmware_stale"] is None
    assert result["device"]["readings"]["ANNOUNCE"]["stale"] is None
    assert service.device(DEVICE_ID, max_age_seconds=200)["device"]["firmware_stale"] is False
    with pytest.raises(mcp_server.DeviceError) as missing:
        service.device(DEVICE_ID, max_age_seconds=120)
    assert (missing.value.code, missing.value.retryable) == ("device_not_observed", True)


def test_status_and_diagnostics_report_an_absent_gateway():
    async def calls(client):
        status = await client.call_tool("infuse_status")
        diagnostics = await client.call_tool("infuse_diagnostics", {"device_ids": [DEVICE_ID]})
        return status, diagnostics

    status, diagnostics = run(ReadService(default_multicast_address(28931)), calls)
    for result in (data(status), data(diagnostics)):
        assert result["gateway"]["available"] is False
        assert result["gateway"]["error"]["code"] == "gateway_unavailable"
        assert result["collector"]["running"] is False
        assert result["credentials"]["status"] in ("available", "unavailable")
    assert data(diagnostics)["radio"]["findings"] == ["no_counters"]
    assert data(diagnostics)["devices"] == [
        {
            "id": DEVICE_ID,
            "observed": False,
            "last_seen_at": None,
            "age_seconds": None,
            "application_id": None,
            "network_id": None,
            "firmware_version": None,
        }
    ]


def test_credentials_are_checked_without_prompting(monkeypatch):
    class Keychain:
        def get_password(self, service, username):
            raise AssertionError("An interactive store must not be read")

    probe = mcp_server.CredentialProbe(timeout=0.2)
    monkeypatch.setattr(mcp_server.keyring, "get_keyring", lambda: Keychain())
    assert probe.check()["status"] == "not_checked"

    class Locked:
        def get_password(self, service, username):
            time.sleep(1)
            return None

    monkeypatch.setattr(mcp_server, "NON_INTERACTIVE_KEYRINGS", (f"{Locked.__module__}.{Locked.__qualname__}",))
    monkeypatch.setattr(mcp_server.keyring, "get_keyring", lambda: Locked())
    monkeypatch.setattr("infuse_iot.credentials.keyring.get_password", Locked().get_password)
    start = time.monotonic()
    assert probe.check()["status"] == "unknown"
    assert probe.check()["status"] == "unknown"
    assert time.monotonic() - start < 1
    time.sleep(1)
    assert probe.check()["status"] == "unavailable"


def test_diagnostics_compare_counters_over_a_window(device_gateway):
    gateway = device_gateway(28933)
    gateway.server.control.kind = "native_bt"
    replies = [
        {"advertisements": 10, "infuse_advertisements": 4, "decrypted_packets": 3, "unknown_network_packets": 1},
        {"advertisements": 30, "infuse_advertisements": 9, "decrypted_packets": 3, "unknown_network_packets": 6},
    ]

    def diagnostics(_parameters):
        if len(replies) == 2:
            # Telemetry during the window
            gateway.server.broadcast(ClientNotificationEpacketReceived(packet()))
        return replies.pop(0) if len(replies) > 1 else replies[0]

    gateway.server.control.handlers["diagnostics"] = diagnostics
    service = ReadService(gateway.address)

    async def calls(client):
        await client.call_tool("infuse_status")
        return data(
            await client.call_tool("infuse_diagnostics", {"device_ids": [DEVICE_ID, "0x1"], "observation_seconds": 0.3})
        )

    result = run(service, calls)
    assert result["radio"]["window_counters"] == {
        "advertisements": 20,
        "infuse_advertisements": 5,
        "decrypted_packets": 0,
        "unknown_network_packets": 5,
    }
    assert result["radio"]["findings"] == ["unknown_network"]
    assert [(device["id"], device["observed"]) for device in result["devices"]] == [
        ("0x0000000000000001", False),
        (DEVICE_ID, True),
    ]


def entry_point() -> str:
    """The `infuse` command installed alongside this interpreter."""
    command = shutil.which("infuse", path=str(Path(sys.executable).parent))
    assert command is not None, "Install the package to test its entry point"
    return command


def test_installed_command_writes_only_json_rpc_to_stdout(device_gateway, tmp_path):
    gateway = device_gateway(28935)
    process = subprocess.Popen(
        [entry_point(), "mcp", "--server-port", "28935"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=tmp_path,
        env=dict(os.environ),
    )
    assert process.stdin is not None and process.stdout is not None and process.stderr is not None
    lines: queue.Queue[bytes | None] = queue.Queue()
    stdout, stderr = process.stdout, process.stderr

    def read():
        for line in stdout:
            lines.put(line)
        lines.put(None)

    threading.Thread(target=read, daemon=True).start()
    threading.Thread(target=stderr.read, daemon=True).start()
    received: list[bytes] = []

    def send(message: dict):
        assert process.stdin is not None
        process.stdin.write(json.dumps(message).encode() + b"\n")
        process.stdin.flush()

    def call(identifier: int, method: str, params: dict) -> dict:
        send({"jsonrpc": "2.0", "id": identifier, "method": method, "params": params})
        deadline = time.monotonic() + 30
        while True:
            line = lines.get(timeout=max(deadline - time.monotonic(), 0.1))
            assert line is not None, "Server exited"
            received.append(line)
            message = json.loads(line)
            if message.get("id") == identifier:
                return message

    try:
        client = {"name": "test", "version": "0"}
        call(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": client})
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert {tool["name"] for tool in call(2, "tools/list", {})["result"]["tools"]} == TOOLS
        status = call(3, "tools/call", {"name": "infuse_status", "arguments": {}})["result"]
        assert status["structuredContent"]["data"]["collector"]["running"]
        devices: dict = {}
        for identifier in range(4, 24):
            gateway.server.broadcast(ClientNotificationEpacketReceived(packet()))
            time.sleep(0.1)
            devices = call(identifier, "tools/call", {"name": "infuse_devices", "arguments": {}})["result"]
            if devices["structuredContent"]["data"]["total"]:
                break
        assert devices["structuredContent"]["data"]["items"][0]["id"] == DEVICE_ID
        process.stdin.close()
        process.wait(timeout=30)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    while (line := lines.get(timeout=5)) is not None:
        received.append(line)
    assert process.returncode == 0
    for line in received:
        assert json.loads(line)["jsonrpc"] == "2.0"


@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_sdk_clients_use_the_installed_command(device_gateway, tmp_path, mode):
    gateway = device_gateway(28937 if mode == "auto" else 28939)

    async def main():
        parameters = StdioServerParameters(
            command=entry_point(),
            args=["mcp", "--server-port", str(gateway.address[1])],
            env=dict(os.environ),
            cwd=tmp_path,
        )
        async with Client(parameters, mode=mode) as client:
            assert len((await client.list_tools()).tools) == len(TOOLS)
            status = data(await client.call_tool("infuse_status"))
            assert status["gateway"]["capabilities"]["protocol_version"] == 2
            for _ in range(20):
                gateway.server.broadcast(ClientNotificationEpacketReceived(packet()))
                await asyncio.sleep(0.1)
                page = data(await client.call_tool("infuse_devices"))
                if page["total"]:
                    return page
        raise AssertionError("Telemetry was not collected")

    assert asyncio.run(main())["items"][0]["id"] == DEVICE_ID
