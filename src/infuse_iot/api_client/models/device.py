import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Type, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.new_device_metadata import NewDeviceMetadata


T = TypeVar("T", bound="Device")


@_attrs_define
class Device:
    """
    Attributes:
        id (str): Generated UUID for organisation
        created_at (datetime.datetime):
        updated_at (datetime.datetime):
        mcu_id (str): Device's MCU ID as a hex string Example: 0011223344556677.
        board_id (str): ID of board of device
        organisation_id (str): ID of organisation for board to exist in
        device_id (Union[Unset, str]): 8 byte DeviceID as a hex string (if not provided will be auto-generated) Example:
            d291d4d66bf0a955.
        metadata (Union[Unset, NewDeviceMetadata]): Metadata fields for device Example: {'Field Name': 'Field Value'}.
    """

    id: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    mcu_id: str
    board_id: str
    organisation_id: str
    device_id: Union[Unset, str] = UNSET
    metadata: Union[Unset, "NewDeviceMetadata"] = UNSET
    additional_properties: Dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        id = self.id

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        mcu_id = self.mcu_id

        board_id = self.board_id

        organisation_id = self.organisation_id

        device_id = self.device_id

        metadata: Union[Unset, Dict[str, Any]] = UNSET
        if not isinstance(self.metadata, Unset):
            metadata = self.metadata.to_dict()

        field_dict: Dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "createdAt": created_at,
                "updatedAt": updated_at,
                "mcuId": mcu_id,
                "boardId": board_id,
                "organisationId": organisation_id,
            }
        )
        if device_id is not UNSET:
            field_dict["deviceId"] = device_id
        if metadata is not UNSET:
            field_dict["metadata"] = metadata

        return field_dict

    @classmethod
    def from_dict(cls: Type[T], src_dict: Dict[str, Any]) -> T:
        from ..models.new_device_metadata import NewDeviceMetadata

        d = src_dict.copy()
        id = d.pop("id")

        created_at = isoparse(d.pop("createdAt"))

        updated_at = isoparse(d.pop("updatedAt"))

        mcu_id = d.pop("mcuId")

        board_id = d.pop("boardId")

        organisation_id = d.pop("organisationId")

        device_id = d.pop("deviceId", UNSET)

        _metadata = d.pop("metadata", UNSET)
        metadata: Union[Unset, NewDeviceMetadata]
        if isinstance(_metadata, Unset):
            metadata = UNSET
        else:
            metadata = NewDeviceMetadata.from_dict(_metadata)

        device = cls(
            id=id,
            created_at=created_at,
            updated_at=updated_at,
            mcu_id=mcu_id,
            board_id=board_id,
            organisation_id=organisation_id,
            device_id=device_id,
            metadata=metadata,
        )

        device.additional_properties = d
        return device

    @property
    def additional_keys(self) -> List[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
