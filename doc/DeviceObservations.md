# Device observations and snapshots

Use an updated native Bluetooth gateway to collect raw evidence and decrypt
Infuse traffic, then query it from another terminal:

```sh
infuse native_bt
infuse scan --duration 20 --json
infuse snapshot --duration 20 --json
```

`scan` combines name, manufacturer and service observations across callbacks for
each Bluetooth identifier. Manufacturer `0x0DE4` or service `0xFC74` identifies a
candidate; this does not establish that its packets can be decrypted. Markers
outside the requested window expire. Counts describe observed identifiers, not a
verified count of physical devices. Bluetooth addresses are upper case and colon
separated in scans and telemetry. Scans request addresses rather than macOS
identifiers, as `native_bt` does.

Attached raw scans are paginated to fit the gateway's UDP messages. If a result
includes `next_cursor`, pass it to `scan --cursor <cursor>` with the same duration.
Cursors refer to immutable snapshots, valid for 60 seconds after their last use
and at most 10 minutes. Up to 8 snapshots with further pages are retained. An
expired or evicted cursor reports `snapshot_expired`, and a malformed cursor or
one from a different query `invalid_cursor`. The initial page limit is 50, with a
maximum of 200; the byte budget can return fewer rows. A row too large for a page
on its own drops markers, keeping Infuse markers, and is flagged `truncated`.
Telemetry rows cannot be shortened, so if any matching device is too large for a
page on its own, the first page fails with `item_exceeds_response_budget`;
select fewer fields. Every cursor can therefore advance to the end.

`scan --standalone --duration 20 --json` explicitly owns the local Bluetooth
adapter and needs no API key. Use it when no other gateway is scanning that
adapter. Standalone scans and CLI telemetry snapshots return all rows at once,
without a cursor. A standalone scan fails with `bluetooth_permission_denied` if
the system denies this application access to Bluetooth, and with
`bluetooth_unavailable` for other adapter failures, such as no powered adapter.

`snapshot` subscribes to decoded telemetry and needs a running native or serial
gateway. It records only the collection window. Without a gateway, `scan` and
`snapshot` fail with `gateway_unavailable`.

Results include the `filters` applied, an `observation_window` with the wall
clock `start` and `end` of the observations included, `collector_started_at`, and
the `gateway` identity (`instance_id`, `version`, `gateway_kind`,
`protocol_version`), which is `null` for standalone scans. For a new scan or
snapshot, `gateway.counters` reports how the gateway's `advertisements`,
`infuse_advertisements`, `decrypted_packets`, `unknown_network_packets` and
`invalid_tag_packets` changed during the window. It is `null` if the gateway does
not report counters, as for the serial gateway, or if it restarted during the
window, as shown by a new `instance_id` or a counter that decreased. A snapshot
also fails with `gateway_unavailable` if the gateway stops answering before the
end of its window. Unknown network or invalid tag
packets indicate a credential issue, distinct from an empty radio scan.

Device IDs are full hexadecimal strings. Telemetry values retain their numeric
types and units, except for integers that JavaScript cannot represent exactly.
Infuse IDs within readings (`infuse_id` fields) are `0x%016x` strings like the
device `id`, and any other integer beyond 2^53 - 1 in magnitude is a decimal
string. Each TDF has its own receive time and age. Its `sampled_at` is only set
when the device timestamped the sample, with its age in `sample_age_seconds`. A
reading is `stale` if it was received or sampled longer ago than
`max_age_seconds`, so a backlog sample, or one stamped by a wrong device clock,
can be stale as it arrives. A delayed sample does not replace one
with a later `sampled_at` received within the last 60 seconds. Device clocks can
be wrong, so after that window the latest sample to arrive wins, as after a
device clock reset, and a sample stamped more than 60 seconds after its receipt
never outranks a later arrival. `firmware_version` comes from the latest announcement, with its own
`firmware_age_seconds` and `firmware_stale`, so new sensor data cannot refresh a
stale announcement. Values are reported as decoded, without validity rules beyond
the TDF definitions. ID filters accept hexadecimal in either case, with or
without `0x`. The browser viewer uses the same collector through a display
adapter and retains its existing WebSocket format.

Library callers use the same services. `DeviceState.snapshot(..., paginate=False)`
returns every match without retaining a cursor, for one-shot lookups. Pagination
failures raise `PaginationError`, a `GatewayControlError` with the error `code`.
A cursor must be used with the `max_bytes` of its first page, or it is an
`invalid_cursor`. `TelemetryCollector.start()` attaches or reattaches, keeping its `state`;
`running`, `error` and `error_code` report whether it is still receiving.
Unknown or malformed notifications are skipped and counted. The collector's
socket survives a gateway restart or replacement, so it keeps `capabilities` and
the `gateway` identity current from any capability reply it receives, including
replies to other clients. `refresh(capabilities)` applies a probe made
elsewhere, which also detects a replacement by an older gateway. The socket
cannot fail when the gateway stops, so callers report probes that no gateway
answered with `unanswered()`. After 3 in a row, the collector stops receiving,
with `error_code` `gateway_unavailable` and no `gateway` identity, until
`start()` attaches to a gateway that answers.
