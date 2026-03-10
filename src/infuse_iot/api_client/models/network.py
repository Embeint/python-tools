from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

T = TypeVar("T", bound="Network")


@_attrs_define
class Network:
    """
    Attributes:
        name (str): Unique name of network
        description (str): Description of network
        key (str): Key bytes as a base64 encoded string (must be 32 bytes long) Example:
            AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=.
        organisation_id (UUID): ID of organisation the network belongs to
        public (bool): Whether the network is public (visible to all infuse organisations) Default: False.
        network_id (int): Network ID
        id (UUID): UUID of network
        created_at (datetime.datetime):
        updated_at (datetime.datetime):
    """

    name: str
    description: str
    key: str
    organisation_id: UUID
    network_id: int
    id: UUID
    created_at: datetime.datetime
    updated_at: datetime.datetime
    public: bool = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        description = self.description

        key = self.key

        organisation_id = str(self.organisation_id)

        public = self.public

        network_id = self.network_id

        id = str(self.id)

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

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
                "id": id,
                "createdAt": created_at,
                "updatedAt": updated_at,
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

        id = UUID(d.pop("id"))

        created_at = isoparse(d.pop("createdAt"))

        updated_at = isoparse(d.pop("updatedAt"))

        network = cls(
            name=name,
            description=description,
            key=key,
            organisation_id=organisation_id,
            public=public,
            network_id=network_id,
            id=id,
            created_at=created_at,
            updated_at=updated_at,
        )

        network.additional_properties = d
        return network

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
