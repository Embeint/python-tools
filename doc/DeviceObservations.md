# Device observations and snapshots

`DeviceState` records typed TDF state decoded from gateway telemetry.

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
without `0x`.

Library callers use these services directly. `DeviceState.snapshot(..., paginate=False)`
returns every match without retaining a cursor, for one-shot lookups. Pagination
failures raise `PaginationError`, a `GatewayControlError` with the error `code`.
A cursor must be used with the `max_bytes` of its first page, or it is an
`invalid_cursor`.
