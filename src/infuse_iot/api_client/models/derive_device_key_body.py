from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.key_interface import KeyInterface
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.security_state import SecurityState


T = TypeVar("T", bound="DeriveDeviceKeyBody")


@_attrs_define
class DeriveDeviceKeyBody:
    """
    Attributes:
        device_id (str): The ID of the device to send the RPC to as a hex string Example: d291d4d66bf0a955.
        interface (KeyInterface):
        security_state (Union[Unset, SecurityState]):
    """

    device_id: str
    interface: KeyInterface
    security_state: Union[Unset, "SecurityState"] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        device_id = self.device_id

        interface = self.interface.value

        security_state: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.security_state, Unset):
            security_state = self.security_state.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "deviceId": device_id,
                "interface": interface,
            }
        )
        if security_state is not UNSET:
            field_dict["securityState"] = security_state

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.security_state import SecurityState

        d = dict(src_dict)
        device_id = d.pop("deviceId")

        interface = KeyInterface(d.pop("interface"))

        _security_state = d.pop("securityState", UNSET)
        security_state: Union[Unset, SecurityState]
        if isinstance(_security_state, Unset):
            security_state = UNSET
        else:
            security_state = SecurityState.from_dict(_security_state)

        derive_device_key_body = cls(
            device_id=device_id,
            interface=interface,
            security_state=security_state,
        )

        derive_device_key_body.additional_properties = d
        return derive_device_key_body

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
