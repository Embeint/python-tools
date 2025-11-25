import datetime
from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

T = TypeVar("T", bound="GeneratedMQTTToken")


@_attrs_define
class GeneratedMQTTToken:
    """
    Attributes:
        token (str): Generated MQTT token
        issued_at (datetime.datetime): Issue time of token
        expires_at (datetime.datetime): Expiry time of token
    """

    token: str
    issued_at: datetime.datetime
    expires_at: datetime.datetime
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        token = self.token

        issued_at = self.issued_at.isoformat()

        expires_at = self.expires_at.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "token": token,
                "issuedAt": issued_at,
                "expiresAt": expires_at,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        token = d.pop("token")

        issued_at = isoparse(d.pop("issuedAt"))

        expires_at = isoparse(d.pop("expiresAt"))

        generated_mqtt_token = cls(
            token=token,
            issued_at=issued_at,
            expires_at=expires_at,
        )

        generated_mqtt_token.additional_properties = d
        return generated_mqtt_token

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
