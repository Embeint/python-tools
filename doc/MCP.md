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

These tools are read-only; device actions need `--allow-writes`, described below.
Unknown arguments are rejected, and device IDs are 1 to 16 hexadecimal digits
with an optional `0x` prefix.

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
| `idempotency_conflict` | The `request_key` was used for a different action | no |
| `job_not_found` | No job has this ID | no |
| `state_unavailable` | The job database is locked or unavailable | yes |
| `server_stopped` | This server's job worker has stopped | yes |
| `internal_error` | Unexpected failure, detailed only in the server log | no |

Gateway control failures keep the gateway's code, such as `snapshot_expired`,
`invalid_cursor` or `operation_expired`.

## Device operations

One device operation, a read or an action job, runs at a time per server. A read
waits up to 5 seconds for another operation, or for the gateway to finish
closing a released link, then fails with `device_busy`; at most two calls wait
at once. A read owns the device at the gateway with a 30 to 40 second lease,
renewed by its traffic, so an abandoned read stops blocking the gateway soon
after. Reads finish within about 35 seconds plus `timeout_seconds`, and a
cancelled call stops its read before the next phase. Allow at least 70 seconds
for RPC tool calls in a host that configures its own request timeout.

## Isolation

Protocol stdout is reserved for MCP; logs and startup output go to stderr.
Credential availability is read only from stores that cannot prompt, within 2
seconds; stores such as the macOS Keychain report `not_checked`. Keys are never
returned. No firmware writes, provisioning, shell execution or unrestricted RPC
commands are available.

Run `tox -e mcp` for the protocol tests, which use fake gateways, SDK clients in
current and legacy modes, and the installed `infuse` command over stdio, and
`tox -e mcp-lowest` to run them with the oldest supported SDK, `mcp` 2.3. The
normal tox environment skips them when the extra is absent.

## Targeted actions and jobs

Start with `infuse mcp --allow-writes` to additionally expose `infuse_reboot`,
`infuse_kv_write`, `infuse_job_status` and `infuse_job_cancel`. No per-call terminal
prompt is added. The host supplies user authorization, and each action requires
an explicit device ID and a stable `request_key` of 1 to 128 characters.

KV writes initially support only DEVICE_NAME with 1..128 UTF-8 bytes. Reboot delay
is an integer in 0..60000 milliseconds. Invalid actions fail with `invalid_request`
before a job is created. Actions require a gateway with operation ownership; the
adapter will not silently downgrade writes to a legacy gateway.

Calls return a job promptly. Progress, inputs and outcomes are saved in a
profile-scoped local SQLite database. `--state-directory` overrides its location.
The same request key and specification return the existing job, including failed
or uncertain outcomes, until finished jobs are pruned after 30 days. Device IDs
are compared in full 64-bit form. Reusing a key for a different operation fails
with `idempotency_conflict`.

The server opens this database and recovers its jobs before serving. If the
database or its instance lock is unavailable, `infuse mcp --allow-writes` exits
with a non-zero status and the reason on stderr, rather than starting without
writes.

Only the server that accepted a job runs it, one at a time in submission order,
through that server's gateway. Other servers sharing the database can read and
cancel it. A job waits up to 60 seconds in total, in cancellable steps, for this
server's reads and for another MCP server or CLI client that owns the gateway
operation, then fails with retryable `device_busy` having sent nothing. It owns
the device with the same short lease as reads. Cancelling queued work takes effect
immediately; running work stops only at a checkpoint before sending. An action
already sent to the device cannot be undone by cancellation.

A job ends `completed` with the device's acknowledgement in `result`, or `failed`
with an `error` when nothing was sent or the device rejected the action
(`rpc_rejected`). It is `unknown` when the action may have reached the device: no
acknowledgement arrived (`outcome_unknown`), or the server stopped after sending
(`interrupted`). Finished jobs never change state.

Jobs are never replayed. When a server stops, its queued jobs and any job that
has not sent anything become `cancelled` with `server_stopped`. Shutdown waits up
to 12 seconds for an acknowledgement already in flight; without one the job is
`unknown`, even if the device acts afterwards. If a server exits abruptly, the
next server to notice cancels its queued jobs and marks its running job
`unknown`. Reconcile fresh device state before intentionally issuing a new
request key. `infuse_status` reports `writes_enabled` and, in `jobs`, whether this
server's job worker is running and its last storage error; each job reports the
same in `worker`. Read-only startup does not create a job database or expose
action tools.

Pre-release builds kept jobs in a `jobs` table of the same database. This version
uses `jobs_v1` and leaves that table untouched, so a pre-release server still
running on the profile cannot claim or overwrite its jobs. Jobs accepted by a
pre-release server are not reported, and their request keys start new jobs.
