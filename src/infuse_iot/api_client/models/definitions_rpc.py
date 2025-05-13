from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.definitions_rpc_commands import DefinitionsRPCCommands
    from ..models.definitions_rpc_enums import DefinitionsRPCEnums
    from ..models.definitions_rpc_structs import DefinitionsRPCStructs


T = TypeVar("T", bound="DefinitionsRPC")


@_attrs_define
class DefinitionsRPC:
    """
    Attributes:
        commands (DefinitionsRPCCommands):
        structs (DefinitionsRPCStructs):
        enums (DefinitionsRPCEnums):
    """

    commands: "DefinitionsRPCCommands"
    structs: "DefinitionsRPCStructs"
    enums: "DefinitionsRPCEnums"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        commands = self.commands.to_dict()

        structs = self.structs.to_dict()

        enums = self.enums.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "commands": commands,
                "structs": structs,
                "enums": enums,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.definitions_rpc_commands import DefinitionsRPCCommands
        from ..models.definitions_rpc_enums import DefinitionsRPCEnums
        from ..models.definitions_rpc_structs import DefinitionsRPCStructs

        d = dict(src_dict)
        commands = DefinitionsRPCCommands.from_dict(d.pop("commands"))

        structs = DefinitionsRPCStructs.from_dict(d.pop("structs"))

        enums = DefinitionsRPCEnums.from_dict(d.pop("enums"))

        definitions_rpc = cls(
            commands=commands,
            structs=structs,
            enums=enums,
        )

        definitions_rpc.additional_properties = d
        return definitions_rpc

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
