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

These tools do not change devices; release inspection and update planning write
only a local cache, and device actions need `--allow-writes`, described below.
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
- `infuse_firmware_inspect(release, trusted_public_key)` and
  `infuse_update_plan(release, device_ids, device_boards, allow_downgrade,
  trusted_public_key, verification_seconds)`: release validation and update
  planning, described below. Neither contacts a device.

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
| `release_unavailable` | The release or key file is missing or unreadable | no |
| `release_changed` | The release no longer matches its plan | no |
| `plan_not_found`, `plan_invalid`, `plan_expired`, `plan_blocked` | Create a new plan | no |
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
returned. Read-only startup also exposes release inspection and update planning.
Device writes require `--allow-writes`; provisioning, shell execution and
unrestricted RPC commands are not available.

Run `tox -e mcp` for the protocol tests, which use fake gateways, SDK clients in
current and legacy modes, and the installed `infuse` command over stdio, and
`tox -e mcp-lowest` to run them with the oldest supported SDK, `mcp` 2.3. The
normal tox environment skips them when the extra is absent.

## Targeted actions and jobs

Start with `infuse mcp --allow-writes` to additionally expose `infuse_reboot`,
`infuse_kv_write`, `infuse_update_start`, `infuse_job_status` and
`infuse_job_cancel`. No per-call terminal prompt is added. The host supplies
user authorization, and each action requires an explicit device ID and a stable
`request_key` of 1 to 128 characters.

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

A device action job ends `completed` with the device's acknowledgement in
`result`, or `failed` with an `error` when nothing was sent or the device rejected
the action (`rpc_rejected`). It is `unknown` when the action may have reached the
device: no acknowledgement arrived (`outcome_unknown`), or the server stopped
after sending (`interrupted`). Firmware update jobs cover several devices and
report each one, as described below. Finished jobs never change state.

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

## Firmware inspection, planning and execution

`infuse_firmware_inspect(release, trusted_public_key)` accepts a local release
directory or `.7z`. Archives need `7zz`, `7z` or `7za` on PATH; otherwise supply an
extracted directory. The inspector streams selected members without executing
archive contents, rejects unsafe paths, and bounds archive size, expanded size,
member counts, output and total extraction time (120 seconds). Inspection and
planning never contact devices. They only write a local cache of selected files,
identified by SHA-256, and of plans. Entries unused for a day are pruned, as are
the oldest beyond 16 packages or 1024 plans once an hour old. Each transfer
marks its package as used, so a running job or `ota_upgrade` keeps it for later
devices, and a job starting after its package was pruned stages it again from
the release. A cached package that is incomplete or modified, for example after
an interrupted prune, is likewise discarded and staged again. Temporary files
left by interrupted staging or plan writes are removed once an hour old.

At most two inspections or plans run at once, on threads separate from the
other tools, so `infuse_status` and the job tools still answer. A cancelled call
returns at once and stops any extraction under way, freeing its place. The
server exits without waiting for release work.

The OTA image is selected like the cloud release upload: `ota-*.bin`, otherwise
the primary application's `tfm_s_zephyr_ns_signed.bin`, otherwise its
`zephyr.signed.bin`. A release must contain exactly one such image, since its
diffs are checked against it. Inspection checks the manifest against the image's
MCUboot version and digest. Images with MCUboot header flags, such as encrypted,
compressed, RAM-load or ROM-fixed images, are rejected because the host cannot
verify what the device will apply. Bytes after the TLV area are accepted only as
erased padding (all `0xff` or all `0x00`), optionally ending in the MCUboot
trailer magic, as `imgtool sign --pad` produces; other trailing bytes, such as a
`--confirm` image state, reject the image. For each `diffs/<version>.bin` patch it
checks the header and payload CRCs, and that the output length and CRC declared
in the header match the selected image; patches are not applied on the host. A
patch that fails these checks, for example one generated against an older build,
is listed in `rejected_patches` with its reason and is not staged, without
rejecting the release. Devices running its source version are planned with a
full image when `full_image_fallback` and board evidence allow it, or blocked as
`patch_rejected`; either way the device entry reports the `rejected_patch`.
Files in `diffs/` that are not named after a version, such as `._*` metadata,
are reported and ignored.
`diffs/0x<application>/<version>.bin` patches are indexed as application
migrations, which only `ota_upgrade` with explicit `--id` or `--list` devices uses.
A signature's presence is reported as `present_unverified` unless a trusted
public key was supplied and verification succeeds. Host verification currently
supports MCUboot RSA-2048 and RSA-3072 PEM public keys. Bootloader signature
enforcement still applies on the device.

Planning attaches the collector, failing with `gateway_unavailable` without a
gateway. After collecting fresh announcements, call:

```text
infuse_update_plan(
  release="/absolute/path/to/release.7z",
  device_ids=["0xce7e42571a000099", "0xce7e42571a0000ac"],
  device_boards={"0xce7e42571a0000ac": "sr2202/nrf52840"},
  verification_seconds=180
)
```

The plan lists exact IDs, observed versions and timestamps, the version relation,
compatibility evidence, selected patch or full signed image, sizes, hashes and
blocked/skip reasons. Each device's evidence is its latest firmware announcement,
which must be at most 60 seconds old (`firmware_age_seconds`); newer telemetry of
another kind cannot refresh it. The device's application ID must match the
release. A release older than the running `major.minor.revision` is blocked as
`downgrade` unless `allow_downgrade` is set; a different build of the same
version is a `rebuild`. A patch is selected only for the exact observed version
and build, without board evidence (`patch_source_version`). Its header declares
the source image length and CRC, which Infuse firmware is expected to check
before applying; the host cannot verify this. A full image requires
`announcement_crc` evidence, from an ANNOUNCE_V2 board CRC, or a
`caller_assertion` in `device_boards`. That is your statement of each device's
board from your own inventory: the plan records it, but cannot observe it, so
never copy the release's board into it.

Review that result, then use `infuse_update_start(plan_id, request_key)` on a
write-enabled server. A plan must be started, and its job must begin executing,
within 15 minutes of planning; otherwise it fails with `plan_expired` before any
device is contacted. Missing plans fail with `plan_not_found`, and blocked plans
cannot start. The service rechecks release contents and each device's application
and version before transfer. The plan's package hashes, selected devices, board
assertions and verification window are bound together; changing them requires a
new plan. A repeated request key returns its original job even after the plan
expires. Use the same `--state-directory` when moving between read-only planning
and write-enabled execution. Without that override the package/plan cache is
shared between those modes, while job records remain scoped to the active profile.

Transfers run sequentially under gateway operation ownership. Like other device
operations, a connection and transfer waits for this server's reads; verification
does not. Only failures before a firmware write, including a disconnect during
the precondition reads, are retried automatically, and a busy gateway is retried
for up to 20 seconds. Length/CRC acknowledgement is transfer evidence.
Successful update status requires a new post-transfer announcement for the exact
device, application, full version and build hash. The verification subscription
opens after transfer so queued earlier packets cannot satisfy this check. The
gateway operation stays owned during verification, renewed every 20 seconds, so
other device reads report `device_busy`. If ownership renewal fails, for example
after a gateway restart, verification continues and the result reports
`ownership_lost`. A lost acknowledgement or disconnect may still be verified from
a fresh announcement; otherwise the outcome is `unknown`, never automatically
replayed. The verification window is configurable from 5 to 600 seconds,
defaulting to 180.

A job counts as sent once it sets a device's time, just before the first
firmware write. Cancellation stops queued devices and safely abortable
transfers. Once the last bytes have been sent, progress reports
`cancellation_deferred`: the device may already be applying the image, so
verification continues before cancellation can stop the next target. Per-device
results are checkpointed to the job record, including failures and uncertain
outcomes. A job is `completed` only when every device is `version_verified` or
`already_current`. A job with any `unknown` device ends `unknown` with
`outcome_unknown`, even if it was cancelled afterwards; a job cancelled or stopped
after sending ends `unknown` with `interrupted`. Otherwise a failed device makes
the job `failed` with `update_failed`, even if earlier devices were written and
verified, so check each device in `result.devices`. Inspect fresh device state
before replanning.

`infuse ota_upgrade --release <directory>` uses the same inspection, planning
and transfer service, while keeping its fleet behavior. It inspects the release
once at startup, exiting if it is rejected, and plans each announcement against
that inspection; each transfer rechecks the staged bytes it sends. Staged bytes
that were pruned are staged again, but if the release itself changed the scan
stops. A device whose plan fails is skipped with the reason.

Leave it running without `--id` or `--list` to upgrade matching devices as they
come into range, even after quiet periods or after all devices seen so far have
been handled. It keeps scanning until Ctrl+C; `--verification-seconds` limits
each device's verification window, not the scanning session. Handled devices are
not written again during that run. With `--id` or `--list`, it exits once those
devices have been handled.

For example, start a gateway in one terminal, then leave this running in another:

```sh
infuse ota_upgrade --release /path/to/release --log updates.csv
```

It writes patches only, including application migration patches for explicit
`--id` or `--list` devices, and counts devices without a matching diff as "No
Diff". `--full-image` allows the signed image for those devices, given board CRC
telemetry or `--board`, which asserts the board of the explicit devices. Older
releases are skipped unless `--allow-downgrade` is given. After each transfer
the device is pending while other devices are upgraded, and later announcements
of the new version within `--verification-seconds` (default 60) record it as
upgraded; otherwise it is logged as `failed` with the observed version. Devices
still awaiting verification when the scan stops, for example on Ctrl+C, are
logged as `unverified` with the version they ran before the transfer. The
`--log` CSV keeps its five columns, so failure reasons such as
`verification_timeout` or `rpc_rejected` are listed in the console summary
instead. Devices that could not be connected to are retried on a later
announcement. Its existing RSSI, connection timeout and CSV log options remain
available. Serial and protocol v1 gateways still have their time set, and the
existing `--single` gateway-copy mode retains its transport-specific
implementation.

Release acceptance still includes hardware update testing and real MCP host
configuration on the intended platforms. Automated coverage uses simulated
transfers and SDK clients; read-only macOS gateway attachment was exercised
against live observations. Firmware bytes are not written by the test suite.
