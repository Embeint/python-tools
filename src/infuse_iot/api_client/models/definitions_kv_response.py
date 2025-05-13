import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

if TYPE_CHECKING:
    from ..models.definitions_kv import DefinitionsKV


T = TypeVar("T", bound="DefinitionsKVResponse")


@_attrs_define
class DefinitionsKVResponse:
    """
    Attributes:
        created_at (datetime.datetime):
        version (int):
        definitions (DefinitionsKV):
    """

    created_at: datetime.datetime
    version: int
    definitions: "DefinitionsKV"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        created_at = self.created_at.isoformat()

        version = self.version

        definitions = self.definitions.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "createdAt": created_at,
                "version": version,
                "definitions": definitions,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.definitions_kv import DefinitionsKV

        d = dict(src_dict)
        created_at = isoparse(d.pop("createdAt"))

        version = d.pop("version")

        definitions = DefinitionsKV.from_dict(d.pop("definitions"))

        definitions_kv_response = cls(
            created_at=created_at,
            version=version,
            definitions=definitions,
        )

        definitions_kv_response.additional_properties = d
        return definitions_kv_response

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
