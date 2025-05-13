from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.rpc_params import RPCParams


T = TypeVar("T", bound="NewRPCReq")


@_attrs_define
class NewRPCReq:
    """
    Attributes:
        command_id (Union[Unset, int]): ID of RPC command (must provide either commandId or commandName) Example: 3.
        command_name (Union[Unset, str]): Name of RPC command (must provide either commandId or commandName) Example:
            time_get.
        params (Union[Unset, RPCParams]): RPC request or response params (must be a JSON object with string or embedded
            json values - numbers sent as decimal strings) Example: {'primitive_vaue': '1000', 'struct_value': {'field':
            'value'}}.
    """

    command_id: Union[Unset, int] = UNSET
    command_name: Union[Unset, str] = UNSET
    params: Union[Unset, "RPCParams"] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        command_id = self.command_id

        command_name = self.command_name

        params: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.params, Unset):
            params = self.params.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if command_id is not UNSET:
            field_dict["commandId"] = command_id
        if command_name is not UNSET:
            field_dict["commandName"] = command_name
        if params is not UNSET:
            field_dict["params"] = params

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.rpc_params import RPCParams

        d = dict(src_dict)
        command_id = d.pop("commandId", UNSET)

        command_name = d.pop("commandName", UNSET)

        _params = d.pop("params", UNSET)
        params: Union[Unset, RPCParams]
        if isinstance(_params, Unset):
            params = UNSET
        else:
            params = RPCParams.from_dict(_params)

        new_rpc_req = cls(
            command_id=command_id,
            command_name=command_name,
            params=params,
        )

        new_rpc_req.additional_properties = d
        return new_rpc_req

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
