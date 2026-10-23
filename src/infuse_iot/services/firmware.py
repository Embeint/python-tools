"""Plan exact firmware targets, transfer approved bytes and verify fresh versions."""

import binascii
import copy
import hashlib
import json
import os
import re
import tempfile
import threading
import time
from contextlib import ExitStack, closing, suppress
from pathlib import Path
from typing import Any

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import rpc_return_code_str
from infuse_iot.common import InfuseType
from infuse_iot.epacket.packet import Auth
from infuse_iot.rpc_client import RpcClient
from infuse_iot.services.device_operations import (
    MAX_SAFE_INTEGER,
    DeviceError,
    DeviceOperations,
    device_id,
    struct_data,
)
from infuse_iot.services.device_state import FIRMWARE_READINGS, DeviceState
from infuse_iot.services.jobs import JobCancelled
from infuse_iot.services.release_package import _bounded_read, inspect_release, prune_cache
from infuse_iot.socket_comms import (
    ClientNotificationEpacketReceived,
    GatewayControlError,
    GatewayRequestConnectionRequest,
    LocalClient,
)
from infuse_iot.tdf import TDF
from infuse_iot.time import InfuseTime
from infuse_iot.util.crc import crc16_ccitt

PLAN_SECONDS = 900
# Plans only use firmware announcements this recent; other telemetry does not refresh them.
ANNOUNCEMENT_MAX_AGE_S = 60
PLAN_FILE = re.compile(r"[0-9a-f]{64}\.json")
# Verification is silent at the gateway, so renew the owned operation well inside its lease.
OPERATION_SECONDS = 60
RENEW_SECONDS = 20
# A just-released gateway link can report busy while it is torn down.
BUSY_SECONDS = 20


def version_relation(current: str, target: str) -> str:
    """Compare `major.minor.revision+build` versions; a different build of the same release is a rebuild"""
    if current == target:
        return "current"
    old, new = (tuple(int(part) for part in value.split("+")[0].split(".")) for value in (current, target))
    return "upgrade" if new > old else ("downgrade" if new < old else "rebuild")


class FirmwareService:
    def __init__(
        self,
        address: tuple[str, int],
        state: DeviceState,
        cache: Path,
        operations: DeviceOperations | None = None,
        require_ownership: bool = True,
        connection_timeout_ms: int = 30000,
    ):
        self.address, self.state, self.cache = address, state, cache
        self.operations = operations or DeviceOperations(address)
        self.require_ownership = require_ownership
        self.connection_timeout_ms = connection_timeout_ms

    def inspect(
        self, release: str, trusted_public_key: str | None = None, cancel: threading.Event | None = None
    ) -> dict:
        """Inspect a release; setting `cancel` stops any extraction with a `cancelled` `DeviceError`"""
        key = Path(trusted_public_key) if trusted_public_key else None
        try:
            return inspect_release(Path(release), self.cache, key, cancel)
        except OSError as error:
            raise DeviceError("release_unavailable", "Release or key file is missing or unreadable") from error

    def plan(
        self,
        release: str,
        device_ids: list[str],
        device_boards: dict[str, str] | None = None,
        trusted_public_key: str | None = None,
        verification_seconds: float = 180,
        allow_downgrade: bool = False,
        full_image_fallback: bool = True,
        allow_application_change: bool = False,
        store: bool = True,
        cancel: threading.Event | None = None,
        package: dict | None = None,
    ) -> dict:
        """Plan targets of `release`, or of its already inspected `package`; transfers recheck the staged bytes"""
        if not 5 <= verification_seconds <= 600:
            raise ValueError("verification_seconds must be between 5 and 600")
        targets = [f"0x{device_id(identifier):016x}" for identifier in device_ids]
        if not 1 <= len(targets) <= 100 or len(set(targets)) != len(targets):
            raise ValueError("Supply 1..100 distinct, explicit device IDs")
        boards = {f"0x{device_id(key):016x}": value for key, value in (device_boards or {}).items()}
        if len(boards) != len(device_boards or {}) or not set(boards) <= set(targets):
            raise ValueError("device_boards must map distinct device IDs from device_ids to board names")
        if any(not isinstance(value, str) or not 1 <= len(value) <= 128 for value in boards.values()):
            raise ValueError("device_boards values must be board names of 1..128 characters")
        if package is None:
            package = self.inspect(release, trusted_public_key, cancel)
        # One unpaginated lookup, so planning never evicts another caller's cursor. Every row since the
        # collector started is included, and judged by the age of its firmware announcement.
        snapshot = self.state.snapshot(
            ids=targets, fields=list(FIRMWARE_READINGS), max_age_seconds=MAX_SAFE_INTEGER, paginate=False
        )
        observed = {row["id"]: row for row in snapshot["items"]}
        release_board_crc = crc16_ccitt(package["board"].encode())
        rejected = {(row["source_application_id"], row["source_version"]): row for row in package["rejected_patches"]}
        entries = []
        for identifier in targets:
            row = observed.get(identifier)
            entry: dict[str, Any] = {"device_id": identifier, "status": "blocked", "reason": "device_not_observed"}
            entries.append(entry)
            if row is None:
                continue
            age = row["firmware_age_seconds"]
            announcements = [value for name, value in row["readings"].items() if name in FIRMWARE_READINGS]
            if age is None or age > ANNOUNCEMENT_MAX_AGE_S or not announcements:
                entry.update(reason="firmware_announcement_stale", firmware_age_seconds=age)
                continue
            announcement = min(announcements, key=lambda value: value["age_seconds"])
            values = announcement["values"]
            current_version = values["version"]
            current_application = f"0x{values['application']:08x}"
            entry.update(
                current_application_id=current_application,
                current_version=current_version,
                version_observed_at=row["firmware_observed_at"],
                firmware_age_seconds=age,
            )
            board_crc = values.get("board_crc")
            asserted = boards.get(identifier)
            if asserted is not None:
                entry["asserted_board"] = asserted
            if (board_crc is not None and board_crc != release_board_crc) or asserted not in (None, package["board"]):
                entry["reason"] = "board_mismatch"
                continue
            if board_crc is not None:
                entry["board_evidence"] = "announcement_crc"
            elif asserted is not None:
                # Not observed: the caller states this device's board from its own inventory.
                entry["board_evidence"] = "caller_assertion"
            unusable = rejected.get((current_application, current_version))
            if current_application == package["application_id"]:
                relation = version_relation(current_version, package["version"])
                entry["version_relation"] = relation
                if relation == "current":
                    entry.update(status="already_current", reason="target_version_observed")
                    continue
                if relation == "downgrade" and not allow_downgrade:
                    entry["reason"] = "downgrade"
                    continue
                image = package["patches"].get(current_version)
            else:
                image = package["migration_patches"].get(current_application, {}).get(current_version)
                if (image is None and unusable is None) or not allow_application_change:
                    entry["reason"] = "application_mismatch"
                    continue
                entry["version_relation"] = "application_change"
            if unusable is not None:
                # The release's diff for this version failed inspection, so only a full image can apply.
                entry["rejected_patch"] = copy.deepcopy(unusable)
            if image is not None:
                entry.update(method="patch", image=copy.deepcopy(image))
                entry.setdefault("board_evidence", "patch_source_version")
            elif not full_image_fallback or entry["version_relation"] == "application_change":
                entry["reason"] = "patch_rejected" if unusable is not None else "no_matching_patch"
                continue
            elif "board_evidence" not in entry:
                entry["reason"] = "board_unknown_for_full_image; assert this device's board in device_boards"
                continue
            else:
                entry.update(method="full_image", image=copy.deepcopy(package["image"]))
            entry.update(status="ready", reason="application_and_transfer_preconditions_selected")
        created = time.time()
        plan = {
            "schema_version": 1,
            "created_at": created,
            "expires_at": created + PLAN_SECONDS,
            "package": package,
            "device_boards": boards,
            "allow_downgrade": allow_downgrade,
            "full_image_fallback": full_image_fallback,
            "allow_application_change": allow_application_change,
            "verification_seconds": verification_seconds,
            "devices": entries,
        }
        plan_id = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
        plan["plan_id"] = plan_id
        if not store:
            return plan
        directory = self.cache / "plans"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False, encoding="utf-8") as temporary:
            temporary_path = Path(temporary.name)
            json.dump(plan, temporary, allow_nan=False)
        os.replace(temporary_path, directory / f"{plan_id}.json")
        prune_cache(directory, PLAN_FILE, directory / f"{plan_id}.json", 1024)
        return plan

    def load_plan(self, plan_id: str) -> dict:
        if not isinstance(plan_id, str) or not PLAN_FILE.fullmatch(f"{plan_id}.json"):
            raise DeviceError("plan_invalid", "Plan IDs are 64 lowercase hexadecimal characters")
        path = self.cache / "plans" / f"{plan_id}.json"
        try:
            if path.stat().st_size > 1024 * 1024:
                raise DeviceError("plan_invalid", "Stored plan exceeds its size limit")
            plan = json.loads(path.read_text(encoding="utf-8"))
            claimed = plan.pop("plan_id")
        except FileNotFoundError:
            raise DeviceError("plan_not_found", "No stored plan has this ID; create a new plan") from None
        except (OSError, ValueError, KeyError, AttributeError):
            raise DeviceError("plan_invalid", "Stored plan could not be read; create a new plan") from None
        actual = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
        if claimed != plan_id or actual != plan_id:
            raise DeviceError("plan_invalid", "Plan integrity check failed; create a new plan")
        plan["plan_id"] = plan_id
        return plan

    def validate_start(self, plan_id: str) -> dict:
        """Check a stored plan can still start; failures happen before any device contact"""
        plan = self.load_plan(plan_id)
        if time.time() - plan["created_at"] > PLAN_SECONDS:
            raise DeviceError("plan_expired", "Plan is older than 15 minutes; refresh device evidence and replan")
        if any(row["status"] == "blocked" for row in plan["devices"]):
            raise DeviceError(
                "plan_blocked", "Plan contains blocked targets; resolve the evidence or replan with explicit ready IDs"
            )
        return plan

    @staticmethod
    def _rpc(rpc: RpcClient, definition, request) -> object:
        decoder = getattr(definition.response, "vla_from_buffer_copy", definition.response.from_buffer_copy)
        header, response = rpc.run_standard_cmd(definition.COMMAND_ID, Auth.DEVICE, bytes(request), decoder)
        if header is None:
            raise DeviceError("rpc_timeout", "Device did not return a precondition response", True)
        if header.return_code:
            raise DeviceError("rpc_rejected", rpc_return_code_str(header.return_code))
        if response is None:
            raise DeviceError("device_response_invalid", "Device returned an invalid precondition response")
        return response

    def transfer(self, entry: dict, package: dict, context, verification_seconds: float | None = 180) -> dict:
        """Write one planned image, then verify a fresh announcement unless `verification_seconds` is None"""
        identifier = entry["device_id"]
        target = device_id(identifier)
        if verification_seconds is not None and not 0 < verification_seconds <= 600:
            raise ValueError("verification_seconds must be in (0, 600]")
        staged = Path(package["staged_directory"])
        with suppress(OSError):
            # Mark the package as used, so cache pruning keeps it for the job's or fleet's later devices.
            os.utime(staged)
        try:
            payload = _bounded_read(staged / entry["image"]["file"], staged)
        except (OSError, ValueError) as error:
            raise DeviceError("release_changed", "Staged transfer bytes are missing; replan") from error
        if hashlib.sha256(payload).hexdigest() != entry["image"]["sha256"]:
            raise DeviceError("release_changed", "Selected transfer bytes changed after planning")
        expected_crc = binascii.crc32(payload)
        source_application = entry.get("current_application_id", package["application_id"])
        write_started = False
        client = LocalClient(self.address)
        try:
            with ExitStack() as owned:
                # This server's other operations wait for the connection and transfer only; verification below
                # just observes announcements.
                with self.operations.exclusive(), ExitStack() as connected:
                    context.check_cancelled()
                    try:
                        features = client.capabilities().get("features", [])
                    except OSError:
                        raise DeviceError("gateway_unavailable", "No gateway answered", True) from None
                    if self.require_ownership and "operation_ownership" not in features:
                        raise DeviceError(
                            "unsupported_capability", "Firmware writes require gateway operation ownership"
                        )
                    operation_id = (
                        owned.enter_context(client.operation(target, duration_seconds=OPERATION_SECONDS))
                        if "operation_ownership" in features
                        else None
                    )
                    context.progress("connecting", device_id=identifier)
                    try:
                        mtu = connected.enter_context(
                            client.connection(
                                target, GatewayRequestConnectionRequest.DataType.COMMAND, self.connection_timeout_ms
                            )
                        )
                    except ConnectionRefusedError as error:
                        raise DeviceError("connection_failed", f"Gateway could not connect: {error}", True) from None
                    except TimeoutError:
                        raise DeviceError("connection_timeout", "Timed out connecting to the device", True) from None
                    rpc = RpcClient(client, mtu, target)
                    rpc.set_timeout(30)
                    info = struct_data(self._rpc(rpc, defs.application_info, defs.application_info.request()))
                    application = f"0x{info['application_id']:08x}"
                    if application == package["application_id"] and info["version"] == package["version"]:
                        return {
                            "device_id": identifier,
                            "status": "already_current",
                            "version": info["version"],
                            "observed_at": time.time(),
                        }
                    if application != source_application:
                        raise DeviceError("application_mismatch", "Application changed after planning")
                    if info["version"] != entry["current_version"]:
                        raise DeviceError("precondition_changed", "Firmware changed after planning; replan")
                    # Setting the time is the first change to the device, so a stop can no longer cancel the job.
                    context.sending()
                    self._rpc(rpc, defs.time_set, defs.time_set.request(InfuseTime.epoch_time_from_unix(time.time())))
                    context.check_cancelled()
                    context.progress("transferring", device_id=identifier, total_bytes=len(payload), bytes_sent=0)
                    last_progress = 0.0

                    def progress(offset):
                        nonlocal last_progress
                        if offset < len(payload):
                            context.check_cancelled()
                        if time.monotonic() - last_progress >= 0.5 or offset == len(payload):
                            last_progress = time.monotonic()
                            context.progress(
                                "transferring" if offset < len(payload) else "awaiting_ack",
                                device_id=identifier,
                                bytes_sent=offset,
                                total_bytes=len(payload),
                                cancellation_deferred=offset == len(payload),
                            )

                    action = (
                        defs.rpc_enum_file_action.APP_CPATCH
                        if entry["method"] == "patch"
                        else (defs.rpc_enum_file_action.APP_IMG)
                    )
                    write_started = True
                    try:
                        header, response = rpc.run_data_send_cmd(
                            defs.file_write_basic.COMMAND_ID,
                            Auth.DEVICE,
                            bytes(defs.file_write_basic.request(action, expected_crc)),
                            payload,
                            progress,
                            defs.file_write_basic.response.from_buffer_copy,
                        )
                    except (ConnectionAbortedError, TimeoutError):
                        # A disconnect can be a reboot. Never replay a possibly accepted write.
                        header, response = None, None
                    if header is not None and header.return_code:
                        raise DeviceError("rpc_rejected", rpc_return_code_str(header.return_code))
                    acknowledged = header is not None and response is not None
                    if (
                        response is not None
                        and acknowledged
                        and (response.recv_len not in (0, len(payload)) or response.recv_crc != expected_crc)
                    ):
                        raise DeviceError("outcome_unknown", "Transfer length or CRC acknowledgement did not match")
                transferred = {
                    "device_id": identifier,
                    "transfer_verified": acknowledged,
                    "bytes": len(payload),
                    "crc32": f"0x{expected_crc:08x}",
                }
                if verification_seconds is None:
                    return {**transferred, "status": "transferred"}
                # Releasing the physical connection lets the device apply/reboot, but keep the operation owned.
                context.progress(
                    "awaiting_reboot",
                    device_id=identifier,
                    transfer_verified=acknowledged,
                    cancellation_deferred=True,
                )
                return self._verify(client, operation_id, package, context, verification_seconds, transferred)
        except (DeviceError, JobCancelled):
            raise
        except Exception as error:
            if write_started:
                raise DeviceError("outcome_unknown", "Write started; reconcile fresh device state") from error
            # Nothing was written, including when the link drops during the precondition reads.
            if isinstance(error, GatewayControlError):
                retryable = error.code in ("device_busy", "operation_expired", "gateway_unavailable")
                raise DeviceError(error.code, error.message or error.code, retryable) from None
            if isinstance(error, ConnectionAbortedError):
                raise DeviceError("connection_dropped", "Device disconnected before any write", True) from None
            if isinstance(error, OSError):
                raise DeviceError("gateway_unavailable", "Gateway stopped answering before any write", True) from None
            raise
        finally:
            client.close()

    def _verify(
        self, client: LocalClient, operation_id: str | None, package: dict, context, seconds: float, transferred: dict
    ) -> dict:
        identifier = transferred["device_id"]
        target = device_id(identifier)
        last_version, last_observed = None, None
        ownership_lost = False
        with closing(LocalClient(self.address)) as verifier:
            deadline = time.monotonic() + seconds
            # The collector decodes with the state's own decoder on its thread.
            decoder = TDF()
            renew_at = time.monotonic() + RENEW_SECONDS
            while time.monotonic() < deadline:
                if operation_id and not ownership_lost and time.monotonic() >= renew_at:
                    # The owner socket is unread during verification; drop its backlog so the reply is not lost.
                    for _ in range(4096):
                        if client.receive(timeout=0) is None:
                            break
                    try:
                        client.control_request("renew_operation", {"owner": operation_id})
                        renew_at = time.monotonic() + RENEW_SECONDS
                    except (TimeoutError, OSError):
                        renew_at = time.monotonic() + 5
                    except GatewayControlError:
                        # For example a restarted gateway. Announcements can still verify the running version.
                        ownership_lost = True
                        context.progress(
                            "awaiting_reboot", device_id=identifier, cancellation_deferred=True, ownership_lost=True
                        )
                message = verifier.receive(timeout=min(0.2, max(0, deadline - time.monotonic())))
                if not isinstance(message, ClientNotificationEpacketReceived):
                    continue
                packet = message.epacket
                if packet.ptype != InfuseType.TDF or not packet.route or packet.route[0].infuse_id != target:
                    continue
                try:
                    for reading in decoder.decode(packet.payload):
                        if not reading.data or reading.data[-1].NAME not in ("ANNOUNCE", "ANNOUNCE_V2"):
                            continue
                        announcement = reading.data[-1]
                        last_version, last_observed = struct_data(announcement.version), time.time()
                        if announcement.application != int(package["application_id"], 16):
                            continue
                        if last_version == package["version"]:
                            context.progress("version_verified", device_id=identifier, version=last_version)
                            return {
                                **transferred,
                                "status": "version_verified",
                                "version": last_version,
                                "observed_at": last_observed,
                                "ownership_lost": ownership_lost,
                            }
                except (ValueError, TypeError, IndexError, RuntimeError):
                    continue
        return {
            **transferred,
            "status": "unknown",
            "reason": "verification_timeout",
            "last_version": last_version,
            "last_observed_at": last_observed,
            "ownership_lost": ownership_lost,
        }

    def _retrying(self, operation, identifier: str, context, phase: str):
        """Retry failures that happened before any write, waiting out a gateway that is still closing a link"""
        attempt, busy_until = 1, time.monotonic() + BUSY_SECONDS
        while True:
            try:
                return operation()
            except DeviceError as error:
                busy = error.code == "device_busy" and time.monotonic() < busy_until
                if not busy and (not error.retryable or error.code == "device_busy" or attempt == 3):
                    raise
                delay = 2 if busy else attempt
                attempt += 0 if busy else 1
            context.check_cancelled()
            context.progress(phase, device_id=identifier, attempt=attempt)
            # Cancellable, so a job stop or cancellation does not wait out the delay.
            context.wait(delay)

    def _current_information(self, identifier: str, context) -> dict:
        def read():
            context.check_cancelled()
            return self.operations.read(identifier, "application_info")

        return self._retrying(read, identifier, context, "retrying_read")

    def run(self, specification: dict, context) -> dict:
        # Expired, blocked or missing plans fail here, before any device contact.
        plan = self.validate_start(specification["plan_id"])
        package = plan["package"]
        try:
            inspected = self.inspect(package["source"], package["trusted_public_key"])
        except ValueError as error:
            raise DeviceError("release_changed", "Release no longer passes inspection") from error
        if inspected != package:
            raise DeviceError("release_changed", "Release contents or signature evidence changed after planning")
        outcomes: list[dict] = []
        result: dict[str, Any] = {"plan_id": plan["plan_id"], "devices": [], "success": True}
        try:
            for entry in plan["devices"]:
                context.check_cancelled()
                outcomes.append(self._run_device(entry, package, plan["verification_seconds"], context))
                result = {
                    "plan_id": plan["plan_id"],
                    "devices": copy.deepcopy(outcomes),
                    "success": all(row["status"] in ("version_verified", "already_current") for row in outcomes),
                }
                context.checkpoint(result)
        except JobCancelled as error:
            if any(row["status"] == "unknown" for row in outcomes):
                # Cancellation must not hide a device whose firmware state is uncertain.
                raise DeviceError(
                    "outcome_unknown", "Cancelled after an uncertain device outcome; inspect the job results"
                ) from error
            raise
        if any(row["status"] == "unknown" for row in outcomes):
            raise DeviceError(
                "outcome_unknown", "Some device versions could not be established; inspect the job results"
            )
        if not result["success"]:
            raise DeviceError("update_failed", "One or more selected devices failed; inspect the job results")
        return result

    def _run_device(self, entry: dict, package: dict, verification_seconds: float, context) -> dict:
        try:
            if entry["status"] == "already_current":
                # Recheck skip evidence through a fresh read; do not turn a planned skip into a write.
                info = self._current_information(entry["device_id"], context)
                response = info["response"]
                if (
                    response["version"] != package["version"]
                    or f"0x{response['application_id']:08x}" != package["application_id"]
                ):
                    raise DeviceError("precondition_changed", "An already-current target changed; replan")
                return {
                    "device_id": entry["device_id"],
                    "status": "already_current",
                    "version": package["version"],
                    "observed_at": info["observed_at"],
                }
            return self._retrying(
                lambda: self.transfer(entry, package, context, verification_seconds),
                entry["device_id"],
                context,
                "retrying_connection",
            )
        except DeviceError as error:
            return {
                "device_id": entry["device_id"],
                "status": "unknown" if error.code == "outcome_unknown" else "failed",
                "reason": error.code,
                "message": error.message,
            }
