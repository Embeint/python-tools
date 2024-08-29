import datetime
from typing import Any, Dict, List, Type, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

T = TypeVar("T", bound="Board")


@_attrs_define
class Board:
    """
    Attributes:
        id (str): Generated UUID for board
        created_at (datetime.datetime):
        updated_at (datetime.datetime):
        name (str): Name of board Example: Board Name.
        description (str): Description of board Example: Extended description of board.
        soc (str): System on Chip (SoC) of board Example: nRF9151.
        organisation_id (str): ID of organisation for board to exist in
    """

    id: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    name: str
    description: str
    soc: str
    organisation_id: str
    additional_properties: Dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        id = self.id

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        name = self.name

        description = self.description

        soc = self.soc

        organisation_id = self.organisation_id

        field_dict: Dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "createdAt": created_at,
                "updatedAt": updated_at,
                "name": name,
                "description": description,
                "soc": soc,
                "organisationId": organisation_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: Type[T], src_dict: Dict[str, Any]) -> T:
        d = src_dict.copy()
        id = d.pop("id")

        created_at = isoparse(d.pop("createdAt"))

        updated_at = isoparse(d.pop("updatedAt"))

        name = d.pop("name")

        description = d.pop("description")

        soc = d.pop("soc")

        organisation_id = d.pop("organisationId")

        board = cls(
            id=id,
            created_at=created_at,
            updated_at=updated_at,
            name=name,
            description=description,
            soc=soc,
            organisation_id=organisation_id,
        )

        board.additional_properties = d
        return board

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
