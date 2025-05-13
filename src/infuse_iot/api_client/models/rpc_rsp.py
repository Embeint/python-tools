from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.rpc_params import RPCParams
    from ..models.uplink_route import UplinkRoute


T = TypeVar("T", bound="RpcRsp")


@_attrs_define
class RpcRsp:
    """
    Attributes:
        route (UplinkRoute):
        return_code (int): Return code of RPC
        params (Union[Unset, RPCParams]): RPC request or response params (must be a JSON object with string or embedded
            json values - numbers sent as decimal strings) Example: {'primitive_vaue': '1000', 'struct_value': {'field':
            'value'}}.
    """

    route: "UplinkRoute"
    return_code: int
    params: Union[Unset, "RPCParams"] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        route = self.route.to_dict()

        return_code = self.return_code

        params: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.params, Unset):
            params = self.params.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "route": route,
                "returnCode": return_code,
            }
        )
        if params is not UNSET:
            field_dict["params"] = params

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.rpc_params import RPCParams
        from ..models.uplink_route import UplinkRoute

        d = dict(src_dict)
        route = UplinkRoute.from_dict(d.pop("route"))

        return_code = d.pop("returnCode")

        _params = d.pop("params", UNSET)
        params: Union[Unset, RPCParams]
        if isinstance(_params, Unset):
            params = UNSET
        else:
            params = RPCParams.from_dict(_params)

        rpc_rsp = cls(
            route=route,
            return_code=return_code,
            params=params,
        )

        rpc_rsp.additional_properties = d
        return rpc_rsp

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
