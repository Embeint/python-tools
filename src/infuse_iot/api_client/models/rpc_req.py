from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.downlink_route import DownlinkRoute
    from ..models.rpc_params import RPCParams
    from ..models.rpc_req_data_header import RPCReqDataHeader


T = TypeVar("T", bound="RpcReq")


@_attrs_define
class RpcReq:
    """
    Attributes:
        request_id (int): The unique ID of the RPC request
        command_id (int): ID of RPC command
        params (RPCParams | Unset): RPC request or response params (must be a JSON object with string or embedded json
            values - numbers sent as decimal strings) Example: {'primitive_vaue': '1000', 'struct_value': {'field':
            'value'}}.
        params_encoded (str | Unset): Base64 encoded params (if provided, will be used instead of params)
        data_header (RPCReqDataHeader | Unset):
        route (DownlinkRoute | Unset):
    """

    request_id: int
    command_id: int
    params: RPCParams | Unset = UNSET
    params_encoded: str | Unset = UNSET
    data_header: RPCReqDataHeader | Unset = UNSET
    route: DownlinkRoute | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        request_id = self.request_id

        command_id = self.command_id

        params: dict[str, Any] | Unset = UNSET
        if not isinstance(self.params, Unset):
            params = self.params.to_dict()

        params_encoded = self.params_encoded

        data_header: dict[str, Any] | Unset = UNSET
        if not isinstance(self.data_header, Unset):
            data_header = self.data_header.to_dict()

        route: dict[str, Any] | Unset = UNSET
        if not isinstance(self.route, Unset):
            route = self.route.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "requestId": request_id,
                "commandId": command_id,
            }
        )
        if params is not UNSET:
            field_dict["params"] = params
        if params_encoded is not UNSET:
            field_dict["paramsEncoded"] = params_encoded
        if data_header is not UNSET:
            field_dict["dataHeader"] = data_header
        if route is not UNSET:
            field_dict["route"] = route

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.downlink_route import DownlinkRoute
        from ..models.rpc_params import RPCParams
        from ..models.rpc_req_data_header import RPCReqDataHeader

        d = dict(src_dict)
        request_id = d.pop("requestId")

        command_id = d.pop("commandId")

        _params = d.pop("params", UNSET)
        params: RPCParams | Unset
        if isinstance(_params, Unset):
            params = UNSET
        else:
            params = RPCParams.from_dict(_params)

        params_encoded = d.pop("paramsEncoded", UNSET)

        _data_header = d.pop("dataHeader", UNSET)
        data_header: RPCReqDataHeader | Unset
        if isinstance(_data_header, Unset):
            data_header = UNSET
        else:
            data_header = RPCReqDataHeader.from_dict(_data_header)

        _route = d.pop("route", UNSET)
        route: DownlinkRoute | Unset
        if isinstance(_route, Unset):
            route = UNSET
        else:
            route = DownlinkRoute.from_dict(_route)

        rpc_req = cls(
            request_id=request_id,
            command_id=command_id,
            params=params,
            params_encoded=params_encoded,
            data_header=data_header,
            route=route,
        )

        rpc_req.additional_properties = d
        return rpc_req

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
