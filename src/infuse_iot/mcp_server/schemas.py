"""Published result schemas. Extra fields are allowed, so additive service changes remain valid."""

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Open(BaseModel):
    model_config = ConfigDict(extra="allow")


class ErrorResult(Open):
    code: str = Field(description="Stable error code, such as gateway_unavailable or device_busy")
    message: str
    retryable: bool = Field(False, description="Whether repeating the same call later may succeed")
    details: dict[str, Any] | None = None


class Envelope(BaseModel, Generic[T]):
    schema_version: Literal[1] = 1
    data: T | None = None
    error: ErrorResult | None = None


class Window(Open):
    start: float
    end: float


class Reading(Open):
    values: dict[str, Any]
    units: dict[str, str]
    received_at: float
    sampled_at: float | None = Field(description="The device's own sample time, when the reading has one")
    age_seconds: float
    sample_age_seconds: float | None = Field(None, description="Age of sampled_at, when the reading has one")
    stale: bool | None = Field(
        description="Received or sampled longer ago than max_age_seconds; null without an age limit"
    )


class Bluetooth(Open):
    address: str
    rssi_dbm: int


class Device(Open):
    id: str
    first_seen_at: float
    last_seen_at: float
    age_seconds: float
    application_id: str | None
    network_id: str | None
    firmware_version: str | None
    firmware_observed_at: float | None
    firmware_age_seconds: float | None = Field(description="Age of the firmware announcement itself")
    firmware_stale: bool | None
    bluetooth: Bluetooth | None = None
    readings: dict[str, Reading]


class DevicePage(Open):
    snapshot_id: str | None
    generated_at: float
    collector_started_at: float
    filters: dict[str, Any]
    observation_window: Window
    gateway: dict[str, Any] | None
    decode_errors: int
    evictions: int
    total: int
    items: list[Device]
    next_cursor: str | None


class DeviceResult(Open):
    device: Device
    max_age_seconds: float | None
    generated_at: float
    collector_started_at: float
    observation_window: Window
    gateway: dict[str, Any] | None


class RawObservation(Open):
    identifier: str
    name: str | None = None
    rssi: int | None = None
    first_seen_at: float | None = None
    last_seen_at: float | None = None
    manufacturer_ids: list[str] = []
    service_uuids: list[str] = []
    infuse_candidate: bool = False
    truncated: bool = False


class RawPage(Open):
    snapshot_id: str | None = None
    generated_at: float | None = None
    filters: dict[str, Any] | None = None
    observation_window: Window | None = None
    gateway: dict[str, Any] | None = None
    total: int
    items: list[RawObservation]
    next_cursor: str | None = None


class RpcRead(Open):
    device_id: str
    command: str
    observed_at: float
    response: dict[str, Any] = Field(
        description="Decoded response fields; kv_read returns values with a per-key status of ok, not_set, "
        "error or invalid"
    )


class GatewayStatus(Open):
    available: bool
    capabilities: dict[str, Any] | None
    error: ErrorResult | None


class CollectorStatus(Open):
    running: bool
    started_at: float = Field(description="When this server began collecting; observations accumulate from here")
    error_code: str | None
    error: str | None
    skipped_notifications: int
    decode_errors: int
    evictions: int
    devices: int


class CredentialStatus(Open):
    status: Literal["available", "unavailable", "unknown", "not_checked"]
    reason: str | None = None


class JobWorker(Open):
    worker_running: bool = Field(description="Whether this server is running the jobs it accepted")
    last_error: str | None = Field(description="The worker's last storage or recovery failure")


class Status(Open):
    version: str
    profile: str | None
    gateway: GatewayStatus
    collector: CollectorStatus
    credentials: CredentialStatus
    writes_enabled: bool
    jobs: JobWorker | None = Field(None, description="This server's job worker; null without --allow-writes")


class DeviceEvidence(Open):
    id: str
    observed: bool = Field(description="Telemetry was decoded from the device during the observation window")
    last_seen_at: float | None
    age_seconds: float | None
    application_id: str | None
    network_id: str | None
    firmware_version: str | None


class Radio(Open):
    counters: dict[str, int] | None = Field(description="Gateway radio and decryption counters since it started")
    window_seconds: float
    window_counters: dict[str, int] | None = Field(description="Counter increments during the observation window")
    findings: list[str] = Field(
        description="no_counters, no_radio_traffic, no_infuse_advertisements, unknown_network, "
        "decryption_failures or decrypting"
    )


class Diagnostics(Status):
    radio: Radio
    devices: list[DeviceEvidence] | None


class Job(Open):
    id: str
    request_key: str
    specification: dict[str, Any] = Field(description="The action, full device ID and parameters")
    state: Literal["queued", "running", "completed", "failed", "cancelled", "unknown"] = Field(
        description="unknown means the action may have reached the device; inspect it before a new request"
    )
    created: float
    updated: float
    progress: dict[str, Any] = Field(description="The latest phase, such as waiting, connecting or executing")
    result: dict[str, Any] | None = Field(description="The device's acknowledgement once completed")
    error: ErrorResult | None
    cancel_requested: bool
    gateway: str | None
    worker: JobWorker


class FirmwareImage(Open):
    file: str
    version: str
    size_bytes: int
    sha256: str
    image_digest_verified: bool
    signature_status: Literal["verified", "present_unverified"] = Field(
        description="verified only against a supplied trusted public key"
    )
    trusted_public_key_sha256: str | None


class FirmwarePatch(Open):
    file: str
    size_bytes: int
    sha256: str
    source_length: int
    source_crc32: str


class RejectedPatch(Open):
    file: str
    source_application_id: str
    source_version: str
    reason: str


class FirmwareRelease(Open):
    source: str
    package_sha256: str
    staged_directory: str
    application_id: str
    board: str
    version: str
    image: FirmwareImage
    patches: dict[str, FirmwarePatch] = Field(description="Patches keyed by the exact source version")
    migration_patches: dict[str, dict[str, FirmwarePatch]] = Field(
        description="Patches from other applications, keyed by application ID and source version"
    )
    rejected_patches: list[RejectedPatch] = Field(description="Patches that do not produce this image, and why")
    ignored_files: list[str]
    file_hashes: dict[str, str]
    trusted_public_key: str | None


class PlannedDevice(Open):
    device_id: str
    status: Literal["ready", "already_current", "blocked"]
    reason: str
    current_application_id: str | None = None
    current_version: str | None = None
    version_observed_at: float | None = None
    firmware_age_seconds: float | None = Field(None, description="Age of the announcement used as evidence")
    version_relation: Literal["current", "upgrade", "downgrade", "rebuild", "application_change"] | None = None
    board_evidence: Literal["announcement_crc", "caller_assertion", "patch_source_version"] | None = None
    asserted_board: str | None = None
    method: Literal["patch", "full_image"] | None = None
    image: dict[str, Any] | None = Field(None, description="The selected patch or full image, with its hash")


class UpdatePlan(Open):
    plan_id: str
    schema_version: int
    created_at: float
    expires_at: float
    package: FirmwareRelease
    device_boards: dict[str, str] = Field(description="Caller board assertions, by full device ID")
    allow_downgrade: bool
    full_image_fallback: bool
    allow_application_change: bool
    verification_seconds: float
    devices: list[PlannedDevice]
