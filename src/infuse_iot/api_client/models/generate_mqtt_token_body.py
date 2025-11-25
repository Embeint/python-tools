from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="GenerateMQTTTokenBody")


@_attrs_define
class GenerateMQTTTokenBody:
    """
    Attributes:
        organisation_id (UUID): ID of organisation to scope the token to
        ttl_seconds (int):  Default: 3600.
    """

    organisation_id: UUID
    ttl_seconds: int = 3600
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        organisation_id = str(self.organisation_id)

        ttl_seconds = self.ttl_seconds

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "organisationId": organisation_id,
                "ttlSeconds": ttl_seconds,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        organisation_id = UUID(d.pop("organisationId"))

        ttl_seconds = d.pop("ttlSeconds")

        generate_mqtt_token_body = cls(
            organisation_id=organisation_id,
            ttl_seconds=ttl_seconds,
        )

        generate_mqtt_token_body.additional_properties = d
        return generate_mqtt_token_body

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
