from typing import TYPE_CHECKING, Any, Dict, List, Type, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.route_type import RouteType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.interface_data import InterfaceData
    from ..models.udp_downlink_route import UdpDownlinkRoute


T = TypeVar("T", bound="DownlinkRoute")


@_attrs_define
class DownlinkRoute:
    """
    Attributes:
        interface (RouteType): Interface of route
        interface_data (InterfaceData):
        udp (Union[Unset, UdpDownlinkRoute]):
    """

    interface: RouteType
    interface_data: "InterfaceData"
    udp: Union[Unset, "UdpDownlinkRoute"] = UNSET
    additional_properties: Dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        interface = self.interface.value

        interface_data = self.interface_data.to_dict()

        udp: Union[Unset, Dict[str, Any]] = UNSET
        if not isinstance(self.udp, Unset):
            udp = self.udp.to_dict()

        field_dict: Dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "interface": interface,
                "interfaceData": interface_data,
            }
        )
        if udp is not UNSET:
            field_dict["udp"] = udp

        return field_dict

    @classmethod
    def from_dict(cls: Type[T], src_dict: Dict[str, Any]) -> T:
        from ..models.interface_data import InterfaceData
        from ..models.udp_downlink_route import UdpDownlinkRoute

        d = src_dict.copy()
        interface = RouteType(d.pop("interface"))

        interface_data = InterfaceData.from_dict(d.pop("interfaceData"))

        _udp = d.pop("udp", UNSET)
        udp: Union[Unset, UdpDownlinkRoute]
        if isinstance(_udp, Unset):
            udp = UNSET
        else:
            udp = UdpDownlinkRoute.from_dict(_udp)

        downlink_route = cls(
            interface=interface,
            interface_data=interface_data,
            udp=udp,
        )

        downlink_route.additional_properties = d
        return downlink_route

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
