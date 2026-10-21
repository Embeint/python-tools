# Infuse MCP server

Install the optional MCP extra, which needs Python 3.11 or newer; other `infuse`
commands still support Python 3.10. CI tests it with Python 3.11 and 3.12:

```sh
python -m pip install '.[mcp]'
```

Start `infuse native_bt` or a serial `infuse gateway` separately. Configure your
MCP host to launch the absolute path to that environment's `infuse` executable:

```json
{
  "mcpServers": {
    "infuse": {
      "command": "/absolute/path/to/.venv/bin/infuse",
      "args": ["mcp", "--transport", "stdio", "--server-port", "8751"]
    }
  }
}
```

On Windows use the environment's `Scripts/infuse.exe`. The host must run on the
machine with the gateway; no remote HTTP endpoint is started. Other `infuse`
commands do not need the MCP extra.

## Tools

All tools are read-only. Unknown arguments are rejected, and device IDs are 1 to
16 hexadecimal digits with an optional `0x` prefix.

- `infuse_status()`: gateway capabilities, collector health and credential
  availability. It succeeds without a gateway, reporting it unavailable.
- `infuse_scan(duration_seconds, cursor, limit, infuse_only)`: a raw BLE window
  of up to 60 s from a `native_bt` gateway advertising `raw_observations`.
- `infuse_devices(ids, application_id, network_id, max_age_seconds, fields,
  cursor, limit)`: decoded telemetry seen within `max_age_seconds` (default 120).
  Follow `next_cursor` with the same filters within 60 seconds of the last page.
- `infuse_device(device_id, fields, max_age_seconds)`: one device's latest
  readings. Without `max_age_seconds` any observation is returned, and the
  `stale` flags are null; judge freshness from the ages.
- `infuse_rpc_read(device_id, command, parameters, timeout_seconds)`:
  `application_info`, `last_reboot`, `data_logger_state` (`logger`) or `kv_read`
  (`keys` from REBOOTS, DEVICE_NAME and BLUETOOTH_ADDR). Each KV value reports a
  `status` of `ok` with its decoded `value`, `not_set`, `error` or `invalid`.
- `infuse_diagnostics(device_ids, observation_seconds)`: status plus radio
  findings (`no_counters`, `no_radio_traffic`, `no_infuse_advertisements`,
  `unknown_network`, `decryption_failures`, `decrypting`). With
  `observation_seconds` (up to 60), the gateway's counters are compared across
  that window, or `null` if the gateway restarted during it, and each device
  reports whether it was heard during it.

Telemetry covers what this server observed since it started, not the lifetime
fleet. The collector attaches in the background, retrying every 5 seconds, and
on demand when a telemetry tool is called. A gateway started after the host is
therefore used without restarting the server. While attached, the server probes
the gateway at the same interval, so results report the `gateway` identity of a
restarted or replaced gateway within about 5 seconds. Each reading and firmware
announcement has its own age; check it before using a reading as evidence.

## Results and errors

Every result is `{schema_version, data, error}`, and each tool publishes an
output schema for its `data`. Failures are MCP error results (`isError`) whose
`error` holds `code`, `message`, `retryable` and optional `details`:

| Code | Meaning | Retryable |
| --- | --- | --- |
| `invalid_request` | Arguments failed validation; `details.fields` names them | no |
| `unknown_tool` | No tool has this name | no |
| `gateway_unavailable` | No gateway answered | yes |
| `device_busy` | Another operation holds the device | yes |
| `connection_failed`, `connection_timeout`, `connection_dropped` | Device link | yes |
| `rpc_timeout` | No RPC response within `timeout_seconds` | yes |
| `rpc_rejected` | The device returned an error code | no |
| `device_response_invalid` | The response did not decode | no |
| `device_not_observed` | No telemetry from the device in the window | yes |
| `unsupported_capability` | The gateway lacks the feature | no |
| `internal_error` | Unexpected failure, detailed only in the server log | no |

Gateway control failures keep the gateway's code, such as `snapshot_expired`,
`invalid_cursor` or `operation_expired`.

## Device operations

One device operation runs at a time per server. A read waits up to 5 seconds
for another operation, or for the gateway to finish closing a released link,
then fails with `device_busy`; at most two calls wait at once. A read owns the
device at the gateway with a 30 to 40 second lease, renewed by its traffic, so
an abandoned read stops blocking the gateway soon after. Reads finish within
about 35 seconds plus `timeout_seconds`, and a cancelled call stops its read
before the next phase. Allow at least 70 seconds for RPC tool calls in a host
that configures its own request timeout.

## Isolation

Protocol stdout is reserved for MCP; logs and startup output go to stderr.
Credential availability is read only from stores that cannot prompt, within 2
seconds; stores such as the macOS Keychain report `not_checked`. Keys are never
returned. No firmware writes, provisioning, shell execution or unrestricted RPC
commands are available.

Run `tox -e mcp` for the protocol tests, which use fake gateways, SDK clients in
current and legacy modes, and the installed `infuse` command over stdio. The
normal tox environment skips them when the extra is absent.
