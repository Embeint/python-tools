from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.route_type import RouteType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.bt_le_route import BtLeRoute
    from ..models.forwarded_downlink_route import ForwardedDownlinkRoute
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
        bt_adv (Union[Unset, BtLeRoute]):
        bt_peripheral (Union[Unset, BtLeRoute]):
        bt_central (Union[Unset, BtLeRoute]):
        forwarded (Union[Unset, ForwardedDownlinkRoute]):
    """

    interface: RouteType
    interface_data: "InterfaceData"
    udp: Union[Unset, "UdpDownlinkRoute"] = UNSET
    bt_adv: Union[Unset, "BtLeRoute"] = UNSET
    bt_peripheral: Union[Unset, "BtLeRoute"] = UNSET
    bt_central: Union[Unset, "BtLeRoute"] = UNSET
    forwarded: Union[Unset, "ForwardedDownlinkRoute"] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        interface = self.interface.value

        interface_data = self.interface_data.to_dict()

        udp: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.udp, Unset):
            udp = self.udp.to_dict()

        bt_adv: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.bt_adv, Unset):
            bt_adv = self.bt_adv.to_dict()

        bt_peripheral: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.bt_peripheral, Unset):
            bt_peripheral = self.bt_peripheral.to_dict()

        bt_central: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.bt_central, Unset):
            bt_central = self.bt_central.to_dict()

        forwarded: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.forwarded, Unset):
            forwarded = self.forwarded.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "interface": interface,
                "interfaceData": interface_data,
            }
        )
        if udp is not UNSET:
            field_dict["udp"] = udp
        if bt_adv is not UNSET:
            field_dict["btAdv"] = bt_adv
        if bt_peripheral is not UNSET:
            field_dict["btPeripheral"] = bt_peripheral
        if bt_central is not UNSET:
            field_dict["btCentral"] = bt_central
        if forwarded is not UNSET:
            field_dict["forwarded"] = forwarded

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.bt_le_route import BtLeRoute
        from ..models.forwarded_downlink_route import ForwardedDownlinkRoute
        from ..models.interface_data import InterfaceData
        from ..models.udp_downlink_route import UdpDownlinkRoute

        d = dict(src_dict)
        interface = RouteType(d.pop("interface"))

        interface_data = InterfaceData.from_dict(d.pop("interfaceData"))

        _udp = d.pop("udp", UNSET)
        udp: Union[Unset, UdpDownlinkRoute]
        if isinstance(_udp, Unset):
            udp = UNSET
        else:
            udp = UdpDownlinkRoute.from_dict(_udp)

        _bt_adv = d.pop("btAdv", UNSET)
        bt_adv: Union[Unset, BtLeRoute]
        if isinstance(_bt_adv, Unset):
            bt_adv = UNSET
        else:
            bt_adv = BtLeRoute.from_dict(_bt_adv)

        _bt_peripheral = d.pop("btPeripheral", UNSET)
        bt_peripheral: Union[Unset, BtLeRoute]
        if isinstance(_bt_peripheral, Unset):
            bt_peripheral = UNSET
        else:
            bt_peripheral = BtLeRoute.from_dict(_bt_peripheral)

        _bt_central = d.pop("btCentral", UNSET)
        bt_central: Union[Unset, BtLeRoute]
        if isinstance(_bt_central, Unset):
            bt_central = UNSET
        else:
            bt_central = BtLeRoute.from_dict(_bt_central)

        _forwarded = d.pop("forwarded", UNSET)
        forwarded: Union[Unset, ForwardedDownlinkRoute]
        if isinstance(_forwarded, Unset):
            forwarded = UNSET
        else:
            forwarded = ForwardedDownlinkRoute.from_dict(_forwarded)

        downlink_route = cls(
            interface=interface,
            interface_data=interface_data,
            udp=udp,
            bt_adv=bt_adv,
            bt_peripheral=bt_peripheral,
            bt_central=bt_central,
            forwarded=forwarded,
        )

        downlink_route.additional_properties = d
        return downlink_route

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
