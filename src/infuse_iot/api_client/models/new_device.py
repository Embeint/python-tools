from typing import Any, Dict, List, Type, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="NewDevice")


@_attrs_define
class NewDevice:
    """
    Attributes:
        mcu_id (str): Device's MCU ID as a hex string Example: 0011223344556677.
        board_id (str): ID of board of device
        organisation_id (str): ID of organisation for board to exist in
        device_id (Union[Unset, str]): 8 byte DeviceID as a hex string (if not provided will be auto-generated) Example:
            d291d4d66bf0a955.
    """

    mcu_id: str
    board_id: str
    organisation_id: str
    device_id: Union[Unset, str] = UNSET
    additional_properties: Dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        mcu_id = self.mcu_id

        board_id = self.board_id

        organisation_id = self.organisation_id

        device_id = self.device_id

        field_dict: Dict[str, Any] = {}
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

        return field_dict

    @classmethod
    def from_dict(cls: Type[T], src_dict: Dict[str, Any]) -> T:
        d = src_dict.copy()
        mcu_id = d.pop("mcuId")

        board_id = d.pop("boardId")

        organisation_id = d.pop("organisationId")

        device_id = d.pop("deviceId", UNSET)

        new_device = cls(
            mcu_id=mcu_id,
            board_id=board_id,
            organisation_id=organisation_id,
            device_id=device_id,
        )

        new_device.additional_properties = d
        return new_device

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
