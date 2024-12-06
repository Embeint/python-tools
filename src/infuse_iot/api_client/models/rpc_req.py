from typing import TYPE_CHECKING, Any, Dict, List, Type, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.downlink_route import DownlinkRoute
    from ..models.rpc_params import RPCParams


T = TypeVar("T", bound="RpcReq")


@_attrs_define
class RpcReq:
    """
    Attributes:
        request_id (int): The unique ID of the RPC request
        command_id (int): ID of RPC command
        params (Union[Unset, RPCParams]): RPC request or response params (must be a JSON object with string or embedded
            json values - numbers sent as decimal strings) Example: {'primitive_vaue': '1000', 'struct_value': {'field':
            'value'}}.
        route (Union[Unset, DownlinkRoute]):
    """

    request_id: int
    command_id: int
    params: Union[Unset, "RPCParams"] = UNSET
    route: Union[Unset, "DownlinkRoute"] = UNSET
    additional_properties: Dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        request_id = self.request_id

        command_id = self.command_id

        params: Union[Unset, Dict[str, Any]] = UNSET
        if not isinstance(self.params, Unset):
            params = self.params.to_dict()

        route: Union[Unset, Dict[str, Any]] = UNSET
        if not isinstance(self.route, Unset):
            route = self.route.to_dict()

        field_dict: Dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "requestId": request_id,
                "commandId": command_id,
            }
        )
        if params is not UNSET:
            field_dict["params"] = params
        if route is not UNSET:
            field_dict["route"] = route

        return field_dict

    @classmethod
    def from_dict(cls: Type[T], src_dict: Dict[str, Any]) -> T:
        from ..models.downlink_route import DownlinkRoute
        from ..models.rpc_params import RPCParams

        d = src_dict.copy()
        request_id = d.pop("requestId")

        command_id = d.pop("commandId")

        _params = d.pop("params", UNSET)
        params: Union[Unset, RPCParams]
        if isinstance(_params, Unset):
            params = UNSET
        else:
            params = RPCParams.from_dict(_params)

        _route = d.pop("route", UNSET)
        route: Union[Unset, DownlinkRoute]
        if isinstance(_route, Unset):
            route = UNSET
        else:
            route = DownlinkRoute.from_dict(_route)

        rpc_req = cls(
            request_id=request_id,
            command_id=command_id,
            params=params,
            route=route,
        )

        rpc_req.additional_properties = d
        return rpc_req

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
