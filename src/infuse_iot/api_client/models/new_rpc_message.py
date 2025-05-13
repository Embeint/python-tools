from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.new_rpc_req import NewRPCReq


T = TypeVar("T", bound="NewRPCMessage")


@_attrs_define
class NewRPCMessage:
    """
    Attributes:
        device_id (str): The ID of the device to send the RPC to as a hex string Example: d291d4d66bf0a955.
        rpc (NewRPCReq):
        send_wait_timeout_ms (Union[Unset, int]): Maximum time to wait (in milliseconds) for the device to send a
            packet. If 0 or not set, the RPC is sent immediately using the device's last route. Default: 60000.
    """

    device_id: str
    rpc: "NewRPCReq"
    send_wait_timeout_ms: Union[Unset, int] = 60000
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        device_id = self.device_id

        rpc = self.rpc.to_dict()

        send_wait_timeout_ms = self.send_wait_timeout_ms

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "deviceId": device_id,
                "rpc": rpc,
            }
        )
        if send_wait_timeout_ms is not UNSET:
            field_dict["sendWaitTimeoutMs"] = send_wait_timeout_ms

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.new_rpc_req import NewRPCReq

        d = dict(src_dict)
        device_id = d.pop("deviceId")

        rpc = NewRPCReq.from_dict(d.pop("rpc"))

        send_wait_timeout_ms = d.pop("sendWaitTimeoutMs", UNSET)

        new_rpc_message = cls(
            device_id=device_id,
            rpc=rpc,
            send_wait_timeout_ms=send_wait_timeout_ms,
        )

        new_rpc_message.additional_properties = d
        return new_rpc_message

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
