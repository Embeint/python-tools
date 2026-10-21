# Infuse MCP implementation plan

Add `infuse mcp` so an AI can discover nearby devices, inspect fresh telemetry, diagnose connection problems, and perform explicitly targeted device operations. Build reusable Python services beneath the CLI and MCP adapters so both interfaces use the same decoding, connection, and update logic.

Deliver discovery and inspection first, then device actions and verified firmware updates. The first release should work alongside an existing `infuse native_bt` or serial gateway without needing the browser viewer.

## Dependency on PR 206

Build on [PR 206](https://github.com/Embeint/python-tools/pull/206), reviewed here at head `ffa8602940ffe4e225484be3c582b01174bd098d`, rather than repeating its lifecycle fixes. Its common ancestor with this checkout is `8fc47239017df50ebc19e8cbe28625599e7d30a2`; this checkout is on main commit `e95ed2a`. Reconcile the newer main commits when establishing the implementation base.

PR 206 already implements device matching for connection results, bounded monotonic connection/RPC waits, the RPC timeout-unit conversion, shared Bluetooth connections and subscriptions, setup deadlines, orderly shutdown, and resource cleanup. It also adds regression tests for those behaviors. These are inherited prerequisites, not new MCP deliverables.

Keep the MCP work in a separate follow-up series. If implementation starts before PR 206 merges, base the new branch on its reviewed head and record that dependency; retarget/rebase onto main after it merges. Keep one independently meaningful change per commit with descriptive bodies, consistent with the review feedback on PR 206. Do not add MCP implementation to the existing cleanup PR.

## Decisions

- Start with local stdio transport. The MCP host launches `infuse mcp --transport stdio --server-port 8751`. Attach to an existing gateway by default; return an actionable `gateway_unavailable` result when none is running. Starting a gateway automatically is a later, explicit option with clear process ownership.
- Use the official Python MCP SDK through an optional `mcp` package extra. The current stable SDK is v2 and requires Python 3.11 or newer. Keep ordinary Infuse commands usable on the existing Python 3.10 baseline; require Python 3.11 or newer for the MCP extra. Select and test a bounded SDK version range during implementation. [SDK requirements](https://py.sdk.modelcontextprotocol.io/), [release v2.3.0](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.3.0).
- Return typed, versioned JSON and concise text summaries. Publish input and output schemas using the SDK, including compatibility coverage for the MCP host versions used by the team. [Structured output](https://py.sdk.modelcontextprotocol.io/servers/structured-output/).
- Keep `native_bt` as the owner of its Bluetooth scanner and connections. Share observations through the gateway interface; an attached MCP server must not start a competing scanner.
- Make read-only tools the default. Enable implemented mutation tools through an explicit server option such as `--allow-writes`. This is a capability setting, not a confirmation prompt on every call. Require explicit device IDs for writes and preserve authorization supplied by the host.
- Keep serial and Bluetooth transport differences inside service adapters. Expose capability differences to callers; a serial gateway cannot supply a raw scan of the host Bluetooth adapter unless a separate scan owner is explicitly selected.

The MCP specification supports stdio and Streamable HTTP. Start with stdio; defer remote HTTP hosting, authentication, and deployment to a separate change when there is a concrete remote client requirement. [Transport specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports).

## Existing code to reuse

- [native_bt.py](../src/infuse_iot/tools/native_bt.py) owns Bleak scanning, packet decryption, and device connections. Extract reusable observation handling without changing its normal gateway role.
- [socket_comms.py](../src/infuse_iot/socket_comms.py) supplies `LocalClient` and `LocalServer`. Inherit PR 206's deadlines, connection-result matching, receive synchronization, and cleanup. Add explicit handling for observation and capability requests. Existing connection requests/releases identify a device, not a particular client operation; distinguish that remaining concurrency contract from the fixes already in PR 206.
- [rpc_client.py](../src/infuse_iot/rpc_client.py) supplies structured RPC execution. Reuse PR 206's monotonic deadlines, disconnect handling, and corrected timeout conversion in [rpc.py](../src/infuse_iot/tools/rpc.py).
- [localhost.py](../src/infuse_iot/tools/localhost.py) collects decoded TDF values, but mixes collection with presentation formatting and records only an overall last-heard time. Extract state collection while preserving the viewer's existing WebSocket shape and PR 206's lock/thread cleanup.
- [ota_upgrade.py](../src/infuse_iot/tools/ota_upgrade.py) selects patches and observes versions. PR 206 fixes its gateway connection timeout and resource cleanup; its startup still assumes a local gateway time-setting connection, which does not fit the native Bluetooth gateway. Move update execution into a service that supports either transport and returns structured outcomes.
- Existing generated RPC/TDF definitions and profile credential lookup remain authoritative. Adapt supported commands incrementally; do not expose every registered CLI command automatically.

## Data contracts

Use canonical, fixed-width hexadecimal strings for 64-bit device IDs, including when a custom display name is available. This prevents precision loss in JavaScript clients. Preserve Bluetooth identifiers separately from Infuse IDs; an identifier observed during scanning is not proof of a distinct physical device.

Each device snapshot includes application ID, network ID, complete firmware version and build hash, Bluetooth identifier/address when available, RSSI, first/last observation times, and typed TDF readings with units. Store receive time and device sample time separately, with freshness for each TDF and particularly for firmware announcements. New temperature packets must not make an old version announcement appear current.

Keep invalid sensor sentinels as raw evidence while presenting a decoded value of `null` with a validity reason where the definition establishes an invalid reading. Represent missing, invalid, and stale readings distinctly. Avoid inventing validity rules from observed values alone.

Snapshot responses include `schema_version`, generation time, collector start time, gateway identity, observation coverage, filters, and a stable snapshot revision. Support explicit IDs, application/network filters, field selection, age limits, and pagination. Default to compact summaries, for example 50 devices per page, with an initial maximum of 200 and a serialized response budget.

Keep raw scan observations distinct from decrypted telemetry. Merge names, service UUIDs, and manufacturer IDs across advertisement callbacks within an observation window. Record when each marker was seen; expire old evidence rather than treating a marker as permanent. Identify Infuse candidates by manufacturer `0x0DE4` or service `0xFC74`, without claiming that the payload was successfully decrypted.

Use stable error codes such as `gateway_unavailable`, `bluetooth_permission_denied`, `credentials_unavailable`, `device_not_observed`, `connection_timeout`, `device_busy`, `rpc_rejected`, and `verification_timeout`. Include retryability, the failing phase, device ID where applicable, and suggested recovery. Tool execution failures must use the MCP error result rather than a success-looking text message; batch jobs report outcomes per device.

## Proposed MCP interface

The initial read-only tools are:

- `infuse_status()` reports server/gateway versions, capabilities, profile name, whether credentials are available, collector uptime, and radio/decryption counters. Never return keys or tokens.
- `infuse_scan(duration_seconds=20, filters, cursor)` returns a bounded raw observation window, marker evidence, RSSI, names, and counts. Initially cap duration at 60 seconds. Return an unsupported-capability result when the attached gateway cannot provide raw observations.
- `infuse_devices(ids, application_id, network_id, max_age_seconds, fields, cursor, limit)` returns cached device summaries with explicit freshness and observation coverage.
- `infuse_device(device_id, fields)` returns the device's latest decoded telemetry and per-reading timestamps.
- `infuse_rpc_read(device_id, command, parameters, timeout_seconds)` performs a typed read RPC from an explicit allowlist. Start with application information, last reboot, logger state, and supported KV reads. Publish the supported parameter schemas; exclude arbitrary memory reads and credential material.
- `infuse_diagnostics(device_ids, observation_seconds)` produces a bounded diagnostic report that distinguishes no radio traffic, candidate advertisements, unknown networks, decryption failures, connection failures, and device RPC errors.

Later tools add `infuse_firmware_inspect`, `infuse_update_plan`, `infuse_update_start`, `infuse_job_status`, `infuse_job_cancel`, and individually implemented actions such as `infuse_reboot` and `infuse_kv_write`.

Offer snapshot and job resources as an additional interface once the tool results are stable. Tools remain sufficient for clients that do not browse resources. Add short workflow prompts only if they improve actual host usage; they are not a dependency for the first release.

## Implementation sequence

### PR 1 Gateway capabilities and operation ownership

1. Establish the implementation base on PR 206 and carry forward its regression tests. Check the relevant behavior after integrating newer main changes; do not recreate the fixes already present.
2. Add gateway capability discovery with a bounded fallback for older gateways. Design new gateway messages as additive changes with a protocol version.
3. Extend existing device matching with operation/client correlation and response-source validation where required. Reuse PR 206's shared physical connection and subscription logic; a reference count is distinct from identifying the operation that owns a mutation.
4. Add gateway-owned operation ownership and expiry for mutating clients. Reject conflicting requests with `device_busy`; a legacy release must not close another client's owned connection. Serialize device operations initially, including across MCP sessions. Require this gateway capability for MCP writes.
5. Validate cleanup and terminal results for new protocol paths, including cancellation, malformed input, and authentication failure, using the lifecycle mechanisms inherited from PR 206.

Acceptance: PR 206's relevant regressions remain passing; two clients cannot take over or release each other's owned operation; new capability/ownership requests terminate within their deadlines. Existing supported CLI clients and shared subscriptions continue working when no exclusive operation conflicts.

### PR 2 Discovery and shared device state

1. Add `services/ble_observations.py`, `services/device_state.py`, and plain typed data models with no MCP dependency.
2. Extract raw advertisement aggregation and a shared TDF state collector. Use synchronized snapshots so readers cannot observe partially updated data. Bound retained devices, raw payloads, history, and diagnostic logs.
3. Add gateway support for querying paginated raw observation summaries and scan counters. Keep these replies below the existing UDP receive limit rather than broadcasting a complete fleet snapshot in one datagram. Label observation windows and incomplete coverage explicitly.
4. Add `infuse scan --duration 20 --json` and `infuse snapshot --duration 20 --json`, using the same services as MCP. A scan can explicitly own the adapter when no gateway is attached; attached mode uses gateway observations. A snapshot collects decoded telemetry for a bounded window without requiring the browser.
5. Switch the localhost viewer to the common collector through a presentation adapter, keeping its existing HTML and WebSocket contract.

Acceptance: a name-only callback followed by manufacturer/service data yields one combined candidate; known 64-bit IDs round-trip exactly; stale announcements remain stale when other telemetry arrives; malformed TDF data does not stop collection; the existing viewer still displays current data.

### PR 3 MCP discovery and inspection

1. Add the optional dependency extra and a lazily loaded `infuse mcp` command through `tools/registry.py`. Normal help and unrelated commands must work without the extra installed.
2. Add `mcp_server/server.py`, schemas, read tools, diagnostics, and lifecycle management. Keep services independent of MCP classes. Run blocking socket/RPC work in managed workers while allowing the server to answer status and cancellation requests.
3. Reserve stdout for MCP messages. Send logs, profile banners, SDK diagnostics, and progress output to stderr or structured notifications; do not rely only on redirecting the outer CLI's prints.
4. Supply example host configuration with the absolute virtual-environment executable, working directory where required, gateway port, and installation instructions. Use existing profile/keyring lookup without embedding credentials in client configuration.
5. Test the selected SDK's supported protocol versions against an actual configured MCP host. Add a compatibility adapter only where required by that test.

Acceptance: an SDK client can launch the installed stdio command, discover schemas, request filtered snapshots, run read RPCs, and receive useful errors. Captured stdout remains protocol-clean throughout startup and shutdown. Scan cancellation releases owned resources without stopping a gateway started by the user.

This is the first useful release: an AI can discover and inspect devices without scraping the viewer or writing temporary Python scripts.

### PR 4 Device actions and jobs

1. Add `services/device_operations.py` and `services/jobs.py`. Expose only implemented operations with typed parameters and explicit targets; require the write capability for mutations.
2. Keep an RPC's version check, required time synchronization, and related action in one owned connection when appropriate. Use bounded retries for transient connection failures; do not automatically replay a mutation whose outcome is unknown. Ownership leases are short and renewed by owned traffic, so renew them explicitly across silent phases.
3. Return a job ID promptly for long operations. Persist state transitions and per-device outcomes so a host disconnect does not lose the result. Repeated start requests with the same operation key return the existing job rather than repeating writes.
4. On restart, reconcile interrupted jobs against fresh device state before any continuation. Expose an explicit unknown/interrupted state when the result cannot be established.
5. Define cancellation by phase. Stop queued work, close safely abortable transfers, and stop additional writes; report when an accepted firmware action is already applying and cannot be rolled back by cancelling the job.

Acceptance: duplicate starts cannot duplicate actions; progress and diagnostics remain available during work; a second client receives `device_busy`; cancellation and server restart preserve accurate outcomes.

### PR 5 Verified firmware updates

1. Extract package inspection, update selection, transfer, and verification into `services/firmware.py`. Accept a local release directory first; support the supplied `.7z` format through validated extraction into staging with traversal and decompression limits. Return a clear missing-extractor result rather than failing midway through a device operation.
2. Make `infuse_update_plan(release, device_ids)` read-only. Return each exact target, fresh current version, intended version, application/board compatibility evidence, selected patch or full signed image, transfer size, and reason for skipping or blocking it. Use board metadata when available; mark compatibility unknown when it cannot be established. An explicit ID must not bypass application checks.
3. Bind the plan to package hashes, target IDs, and relevant preconditions. At execution, recheck the package and device version. Choose the provided version-specific patch when applicable; select the full signed application image for a supported older version without a patch, as required for the `1.2.0` device in this session.
4. Separate package SHA-256 integrity, signed-image structure/hash checks, and cryptographic signature verification. Verify a signature when trusted key material is available; report its verification status accurately and retain the bootloader's signature enforcement.
5. Model each update as `queued`, `connecting`, `transferring`, `transfer_verified`, `awaiting_reboot`, and `version_verified`, with terminal failure, cancellation, and uncertain outcomes. Validate the acknowledged length and CRC. Never equate successful transfer with completed upgrade.
6. Verify a fresh post-transfer announcement or direct application-info response with the complete target build hash. Allow a configurable apply/reboot window, initially 180 seconds, and return the last observed version and timestamps if it expires.
7. Adapt `infuse ota_upgrade` to the shared service and preserve its existing invocation forms. Add full-image fallback deliberately and test transport-specific behavior, including the absence of a physical gateway under `native_bt`.

Acceptance: reproduce the six-device scenario in deterministic tests: three patches, one full-image transfer, and two already-current skips. Inject failed connections, wrong CRCs, stale version announcements, missing patches, package changes, and reboot/verification timeouts. Every result must distinguish transferred, verified, skipped, failed, and unknown.

## Validation and release

Keep automated validation hardware-independent with a fake gateway, fake Bleak observations, recorded/synthetic TDF packets, and simulated RPC transfers. Extend PR 206's socket, RPC, native Bluetooth, and gateway fixtures rather than creating a parallel test framework. Add SDK-level stdio integration tests and packaging checks for installations with and without the MCP extra. Run the repository's tox, ruff, and mypy checks, extending the tox environments to cover Python 3.10 for the base CLI and Python 3.11 or newer for MCP.

Perform read-only smoke tests on macOS, Linux, and Windows: raw markers, decrypted state, adapter permissions, cancellation, and gateway attachment. Hardware write acceptance uses explicitly selected test devices and a known release, with before/after version evidence. It is a release check, not part of CI or a side effect of developing this plan.

Defer remote hosting, cloud provisioning, arbitrary shell commands, generic file upload, destructive logger erasure, automatic extension exposure, and unrestricted RPC execution. Custom tools can opt in later through an explicit schema and capability contract.

The implementation is ready when an MCP host can answer which devices need an update, show the evidence and selected images, execute only the requested targets, and report verified versions without browser scraping or temporary scripts.
