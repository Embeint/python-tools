from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="RPCReqDataHeader")


@_attrs_define
class RPCReqDataHeader:
    """
    Attributes:
        size (int): Amount of data expected
        rx_ack_period (int): Send an ACK every N packets received Default: 0.
    """

    size: int
    rx_ack_period: int = 0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        size = self.size

        rx_ack_period = self.rx_ack_period

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "size": size,
                "rxAckPeriod": rx_ack_period,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        size = d.pop("size")

        rx_ack_period = d.pop("rxAckPeriod")

        rpc_req_data_header = cls(
            size=size,
            rx_ack_period=rx_ack_period,
        )

        rpc_req_data_header.additional_properties = d
        return rpc_req_data_header

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
