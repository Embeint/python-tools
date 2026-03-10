from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="NewNetwork")


@_attrs_define
class NewNetwork:
    """
    Attributes:
        name (str): Unique name of network
        description (str): Description of network
        key (str): Key bytes as a base64 encoded string (must be 32 bytes long) Example:
            AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=.
        organisation_id (UUID): ID of organisation the network belongs to
        public (bool): Whether the network is public (visible to all infuse organisations) Default: False.
        network_id (int): Network ID
    """

    name: str
    description: str
    key: str
    organisation_id: UUID
    network_id: int
    public: bool = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        description = self.description

        key = self.key

        organisation_id = str(self.organisation_id)

        public = self.public

        network_id = self.network_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "description": description,
                "key": key,
                "organisationId": organisation_id,
                "public": public,
                "networkId": network_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name")

        description = d.pop("description")

        key = d.pop("key")

        organisation_id = UUID(d.pop("organisationId"))

        public = d.pop("public")

        network_id = d.pop("networkId")

        new_network = cls(
            name=name,
            description=description,
            key=key,
            organisation_id=organisation_id,
            public=public,
            network_id=network_id,
        )

        new_network.additional_properties = d
        return new_network

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
