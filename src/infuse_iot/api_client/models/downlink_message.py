import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.downlink_message_status import DownlinkMessageStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.rpc_req import RpcReq
    from ..models.rpc_rsp import RpcRsp


T = TypeVar("T", bound="DownlinkMessage")


@_attrs_define
class DownlinkMessage:
    """
    Attributes:
        id (UUID): The ID of the downlink message Example: 7527bf1c-9868-4afd-b07d-16dc7eb7bed3.
        created_at (datetime.datetime): The time the downlink message was created
        updated_at (datetime.datetime): The time the downlink message was last updated
        device_id (UUID): The ID of the device the message is for Example: 5f4b1b2b-3b4d-4b5e-8c6f-7d8e9f0a1b2c.
        payload_type (int): The type of payload
        auth (int): The auth level of the message
        rpc_req (RpcReq):
        status (DownlinkMessageStatus): Status of downlink message
        rpc_rsp (Union[Unset, RpcRsp]):
        send_wait_timeout_ms (Union[Unset, int]): Maximum time to wait (in milliseconds) for the device to send a packet
            before expiring. If 0 or not set, the RPC was sent immediately using the device's last route.
        sent_at (Union[Unset, datetime.datetime]): The time the downlink message was sent
        expires_at (Union[Unset, datetime.datetime]): The time the downlink message expires
        completed_at (Union[Unset, datetime.datetime]): The time the downlink message was completed
    """

    id: UUID
    created_at: datetime.datetime
    updated_at: datetime.datetime
    device_id: UUID
    payload_type: int
    auth: int
    rpc_req: "RpcReq"
    status: DownlinkMessageStatus
    rpc_rsp: Union[Unset, "RpcRsp"] = UNSET
    send_wait_timeout_ms: Union[Unset, int] = UNSET
    sent_at: Union[Unset, datetime.datetime] = UNSET
    expires_at: Union[Unset, datetime.datetime] = UNSET
    completed_at: Union[Unset, datetime.datetime] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        device_id = str(self.device_id)

        payload_type = self.payload_type

        auth = self.auth

        rpc_req = self.rpc_req.to_dict()

        status = self.status.value

        rpc_rsp: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.rpc_rsp, Unset):
            rpc_rsp = self.rpc_rsp.to_dict()

        send_wait_timeout_ms = self.send_wait_timeout_ms

        sent_at: Union[Unset, str] = UNSET
        if not isinstance(self.sent_at, Unset):
            sent_at = self.sent_at.isoformat()

        expires_at: Union[Unset, str] = UNSET
        if not isinstance(self.expires_at, Unset):
            expires_at = self.expires_at.isoformat()

        completed_at: Union[Unset, str] = UNSET
        if not isinstance(self.completed_at, Unset):
            completed_at = self.completed_at.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "createdAt": created_at,
                "updatedAt": updated_at,
                "deviceId": device_id,
                "payloadType": payload_type,
                "auth": auth,
                "rpcReq": rpc_req,
                "status": status,
            }
        )
        if rpc_rsp is not UNSET:
            field_dict["rpcRsp"] = rpc_rsp
        if send_wait_timeout_ms is not UNSET:
            field_dict["sendWaitTimeoutMs"] = send_wait_timeout_ms
        if sent_at is not UNSET:
            field_dict["sentAt"] = sent_at
        if expires_at is not UNSET:
            field_dict["expiresAt"] = expires_at
        if completed_at is not UNSET:
            field_dict["completedAt"] = completed_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.rpc_req import RpcReq
        from ..models.rpc_rsp import RpcRsp

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        created_at = isoparse(d.pop("createdAt"))

        updated_at = isoparse(d.pop("updatedAt"))

        device_id = UUID(d.pop("deviceId"))

        payload_type = d.pop("payloadType")

        auth = d.pop("auth")

        rpc_req = RpcReq.from_dict(d.pop("rpcReq"))

        status = DownlinkMessageStatus(d.pop("status"))

        _rpc_rsp = d.pop("rpcRsp", UNSET)
        rpc_rsp: Union[Unset, RpcRsp]
        if isinstance(_rpc_rsp, Unset):
            rpc_rsp = UNSET
        else:
            rpc_rsp = RpcRsp.from_dict(_rpc_rsp)

        send_wait_timeout_ms = d.pop("sendWaitTimeoutMs", UNSET)

        _sent_at = d.pop("sentAt", UNSET)
        sent_at: Union[Unset, datetime.datetime]
        if isinstance(_sent_at, Unset):
            sent_at = UNSET
        else:
            sent_at = isoparse(_sent_at)

        _expires_at = d.pop("expiresAt", UNSET)
        expires_at: Union[Unset, datetime.datetime]
        if isinstance(_expires_at, Unset):
            expires_at = UNSET
        else:
            expires_at = isoparse(_expires_at)

        _completed_at = d.pop("completedAt", UNSET)
        completed_at: Union[Unset, datetime.datetime]
        if isinstance(_completed_at, Unset):
            completed_at = UNSET
        else:
            completed_at = isoparse(_completed_at)

        downlink_message = cls(
            id=id,
            created_at=created_at,
            updated_at=updated_at,
            device_id=device_id,
            payload_type=payload_type,
            auth=auth,
            rpc_req=rpc_req,
            status=status,
            rpc_rsp=rpc_rsp,
            send_wait_timeout_ms=send_wait_timeout_ms,
            sent_at=sent_at,
            expires_at=expires_at,
            completed_at=completed_at,
        )

        downlink_message.additional_properties = d
        return downlink_message

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
