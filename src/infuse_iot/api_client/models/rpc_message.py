import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

if TYPE_CHECKING:
    from ..models.device import Device
    from ..models.downlink_message import DownlinkMessage


T = TypeVar("T", bound="RpcMessage")


@_attrs_define
class RpcMessage:
    """
    Attributes:
        created_at (datetime.datetime): The time the RPC message was created
        id (UUID): The ID of the RPC message Example: 5f4b1b2b-3b4d-4b5e-8c6f-7d8e9f0a1b2c.
        downlink_message_id (UUID): The ID of the corresponding downlink message sent to the device Example:
            7527bf1c-9868-4afd-b07d-16dc7eb7bed3.
        device (Device):
        downlink_message (DownlinkMessage):
    """

    created_at: datetime.datetime
    id: UUID
    downlink_message_id: UUID
    device: "Device"
    downlink_message: "DownlinkMessage"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        created_at = self.created_at.isoformat()

        id = str(self.id)

        downlink_message_id = str(self.downlink_message_id)

        device = self.device.to_dict()

        downlink_message = self.downlink_message.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "createdAt": created_at,
                "id": id,
                "downlinkMessageId": downlink_message_id,
                "device": device,
                "downlinkMessage": downlink_message,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.device import Device
        from ..models.downlink_message import DownlinkMessage

        d = dict(src_dict)
        created_at = isoparse(d.pop("createdAt"))

        id = UUID(d.pop("id"))

        downlink_message_id = UUID(d.pop("downlinkMessageId"))

        device = Device.from_dict(d.pop("device"))

        downlink_message = DownlinkMessage.from_dict(d.pop("downlinkMessage"))

        rpc_message = cls(
            created_at=created_at,
            id=id,
            downlink_message_id=downlink_message_id,
            device=device,
            downlink_message=downlink_message,
        )

        rpc_message.additional_properties = d
        return rpc_message

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
