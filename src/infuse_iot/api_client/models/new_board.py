from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.metadata_field import MetadataField


T = TypeVar("T", bound="NewBoard")


@_attrs_define
class NewBoard:
    """
    Attributes:
        name (str): Name of board Example: Board Name.
        description (str): Description of board Example: Extended description of board.
        soc (str): System on Chip (SoC) of board Example: nRF9151.
        organisation_id (UUID): ID of organisation for board to exist in
        metadata_fields (Union[Unset, list['MetadataField']]): Metadata fields for board Example: [{'name': 'Field
            Name', 'required': True, 'unique': False}].
    """

    name: str
    description: str
    soc: str
    organisation_id: UUID
    metadata_fields: Union[Unset, list["MetadataField"]] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
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

        new_board = cls(
            name=name,
            description=description,
            soc=soc,
            organisation_id=organisation_id,
            metadata_fields=metadata_fields,
        )

        new_board.additional_properties = d
        return new_board

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
