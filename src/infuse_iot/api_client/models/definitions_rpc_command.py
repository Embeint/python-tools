from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.definitions_rpc_command_default_auth import DefinitionsRPCCommandDefaultAuth
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.definitions_field_definition import DefinitionsFieldDefinition


T = TypeVar("T", bound="DefinitionsRPCCommand")


@_attrs_define
class DefinitionsRPCCommand:
    """
    Attributes:
        name (str):
        description (str):
        default (str):
        default_auth (DefinitionsRPCCommandDefaultAuth):
        request_params (list['DefinitionsFieldDefinition']):
        response_params (list['DefinitionsFieldDefinition']):
        depends_on (Union[Unset, str]):
        rpc_data (Union[Unset, bool]): Whether the command is an RPC data command
    """

    name: str
    description: str
    default: str
    default_auth: DefinitionsRPCCommandDefaultAuth
    request_params: list["DefinitionsFieldDefinition"]
    response_params: list["DefinitionsFieldDefinition"]
    depends_on: Union[Unset, str] = UNSET
    rpc_data: Union[Unset, bool] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        description = self.description

        default = self.default

        default_auth = self.default_auth.value

        request_params = []
        for request_params_item_data in self.request_params:
            request_params_item = request_params_item_data.to_dict()
            request_params.append(request_params_item)

        response_params = []
        for response_params_item_data in self.response_params:
            response_params_item = response_params_item_data.to_dict()
            response_params.append(response_params_item)

        depends_on = self.depends_on

        rpc_data = self.rpc_data

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "description": description,
                "default": default,
                "default_auth": default_auth,
                "request_params": request_params,
                "response_params": response_params,
            }
        )
        if depends_on is not UNSET:
            field_dict["depends_on"] = depends_on
        if rpc_data is not UNSET:
            field_dict["rpc_data"] = rpc_data

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.definitions_field_definition import DefinitionsFieldDefinition

        d = dict(src_dict)
        name = d.pop("name")

        description = d.pop("description")

        default = d.pop("default")

        default_auth = DefinitionsRPCCommandDefaultAuth(d.pop("default_auth"))

        request_params = []
        _request_params = d.pop("request_params")
        for request_params_item_data in _request_params:
            request_params_item = DefinitionsFieldDefinition.from_dict(request_params_item_data)

            request_params.append(request_params_item)

        response_params = []
        _response_params = d.pop("response_params")
        for response_params_item_data in _response_params:
            response_params_item = DefinitionsFieldDefinition.from_dict(response_params_item_data)

            response_params.append(response_params_item)

        depends_on = d.pop("depends_on", UNSET)

        rpc_data = d.pop("rpc_data", UNSET)

        definitions_rpc_command = cls(
            name=name,
            description=description,
            default=default,
            default_auth=default_auth,
            request_params=request_params,
            response_params=response_params,
            depends_on=depends_on,
            rpc_data=rpc_data,
        )

        definitions_rpc_command.additional_properties = d
        return definitions_rpc_command

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
