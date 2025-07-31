from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.bt_le_route_type import BtLeRouteType

T = TypeVar("T", bound="BtLeRoute")


@_attrs_define
class BtLeRoute:
    """
    Attributes:
        address (str): Bluetooth LE address of device
        type_ (BtLeRouteType): Type of Bluetooth LE address (public or random)
    """

    address: str
    type_: BtLeRouteType
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        address = self.address

        type_ = self.type_.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "address": address,
                "type": type_,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        address = d.pop("address")

        type_ = BtLeRouteType(d.pop("type"))

        bt_le_route = cls(
            address=address,
            type_=type_,
        )

        bt_le_route.additional_properties = d
        return bt_le_route

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
