import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.metadata_field import MetadataField


T = TypeVar("T", bound="Board")


@_attrs_define
class Board:
    """
    Attributes:
        id (UUID): Generated UUID for board
        created_at (datetime.datetime):
        updated_at (datetime.datetime):
        name (str): Name of board Example: Board Name.
        description (str): Description of board Example: Extended description of board.
        soc (str): System on Chip (SoC) of board Example: nRF9151.
        organisation_id (UUID): ID of organisation for board to exist in
        metadata_fields (Union[Unset, list['MetadataField']]): Metadata fields for board Example: [{'name': 'Field
            Name', 'required': True, 'unique': False}].
    """

    id: UUID
    created_at: datetime.datetime
    updated_at: datetime.datetime
    name: str
    description: str
    soc: str
    organisation_id: UUID
    metadata_fields: Union[Unset, list["MetadataField"]] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        name = self.name

        description = self.description

        soc = self.soc

        organisation_id = str(self.organisation_id)

        metadata_fields: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.metadata_fields, Unset):
            metadata_fields = []
            for componentsschemas_board_metadata_fields_item_data in self.metadata_fields:
                componentsschemas_board_metadata_fields_item = (
                    componentsschemas_board_metadata_fields_item_data.to_dict()
                )
                metadata_fields.append(componentsschemas_board_metadata_fields_item)

        field_dict: dict[str, Any] = {}
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
        if metadata_fields is not UNSET:
            field_dict["metadataFields"] = metadata_fields

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.metadata_field import MetadataField

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        created_at = isoparse(d.pop("createdAt"))

        updated_at = isoparse(d.pop("updatedAt"))

        name = d.pop("name")

        description = d.pop("description")

        soc = d.pop("soc")

        organisation_id = UUID(d.pop("organisationId"))

        metadata_fields = []
        _metadata_fields = d.pop("metadataFields", UNSET)
        for componentsschemas_board_metadata_fields_item_data in _metadata_fields or []:
            componentsschemas_board_metadata_fields_item = MetadataField.from_dict(
                componentsschemas_board_metadata_fields_item_data
            )

            metadata_fields.append(componentsschemas_board_metadata_fields_item)

        board = cls(
            id=id,
            created_at=created_at,
            updated_at=updated_at,
            name=name,
            description=description,
            soc=soc,
            organisation_id=organisation_id,
            metadata_fields=metadata_fields,
        )

        board.additional_properties = d
        return board

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
