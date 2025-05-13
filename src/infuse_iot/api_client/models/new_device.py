from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.device_metadata import DeviceMetadata
    from ..models.new_device_state import NewDeviceState


T = TypeVar("T", bound="NewDevice")


@_attrs_define
class NewDevice:
    """
    Attributes:
        mcu_id (str): Device's MCU ID as a hex string Example: 0011223344556677.
        board_id (UUID): ID of board of device
        organisation_id (UUID): ID of organisation for board to exist in
        device_id (Union[Unset, str]): 8 byte DeviceID as a hex string (if not provided will be auto-generated) Example:
            d291d4d66bf0a955.
        metadata (Union[Unset, DeviceMetadata]): Metadata fields for device Example: {'Field Name': 'Field Value'}.
        initial_device_state (Union[Unset, NewDeviceState]):
    """

    mcu_id: str
    board_id: UUID
    organisation_id: UUID
    device_id: Union[Unset, str] = UNSET
    metadata: Union[Unset, "DeviceMetadata"] = UNSET
    initial_device_state: Union[Unset, "NewDeviceState"] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        mcu_id = self.mcu_id

        board_id = str(self.board_id)

        organisation_id = str(self.organisation_id)

        device_id = self.device_id

        metadata: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.metadata, Unset):
            metadata = self.metadata.to_dict()

        initial_device_state: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.initial_device_state, Unset):
            initial_device_state = self.initial_device_state.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "mcuId": mcu_id,
                "boardId": board_id,
                "organisationId": organisation_id,
            }
        )
        if device_id is not UNSET:
            field_dict["deviceId"] = device_id
        if metadata is not UNSET:
            field_dict["metadata"] = metadata
        if initial_device_state is not UNSET:
            field_dict["initialDeviceState"] = initial_device_state

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.device_metadata import DeviceMetadata
        from ..models.new_device_state import NewDeviceState

        d = dict(src_dict)
        mcu_id = d.pop("mcuId")

        board_id = UUID(d.pop("boardId"))

        organisation_id = UUID(d.pop("organisationId"))

        device_id = d.pop("deviceId", UNSET)

        _metadata = d.pop("metadata", UNSET)
        metadata: Union[Unset, DeviceMetadata]
        if isinstance(_metadata, Unset):
            metadata = UNSET
        else:
            metadata = DeviceMetadata.from_dict(_metadata)

        _initial_device_state = d.pop("initialDeviceState", UNSET)
        initial_device_state: Union[Unset, NewDeviceState]
        if isinstance(_initial_device_state, Unset):
            initial_device_state = UNSET
        else:
            initial_device_state = NewDeviceState.from_dict(_initial_device_state)

        new_device = cls(
            mcu_id=mcu_id,
            board_id=board_id,
            organisation_id=organisation_id,
            device_id=device_id,
            metadata=metadata,
            initial_device_state=initial_device_state,
        )

        new_device.additional_properties = d
        return new_device

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
