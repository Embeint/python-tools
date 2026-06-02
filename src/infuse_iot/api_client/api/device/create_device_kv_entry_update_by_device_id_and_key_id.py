from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.device_kv_entry import DeviceKVEntry
from ...models.device_kv_entry_update import DeviceKVEntryUpdate
from ...models.error import Error
from ...models.new_device_kv_entry_update import NewDeviceKVEntryUpdate
from ...types import Response


def _get_kwargs(
    device_id: str,
    key_id: int,
    *,
    body: NewDeviceKVEntryUpdate,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/device/deviceId/{device_id}/kv/entries/{key_id}/updates".format(
            device_id=quote(str(device_id), safe=""),
            key_id=quote(str(key_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> DeviceKVEntry | DeviceKVEntryUpdate | Error | None:
    if response.status_code == 200:
        response_200 = DeviceKVEntry.from_dict(response.json())

        return response_200

    if response.status_code == 201:
        response_201 = DeviceKVEntryUpdate.from_dict(response.json())

        return response_201

    if response.status_code == 400:
        response_400 = Error.from_dict(response.json())

        return response_400

    if response.status_code == 403:
        response_403 = Error.from_dict(response.json())

        return response_403

    if response.status_code == 404:
        response_404 = Error.from_dict(response.json())

        return response_404

    if response.status_code == 409:
        response_409 = Error.from_dict(response.json())

        return response_409

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[DeviceKVEntry | DeviceKVEntryUpdate | Error]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    device_id: str,
    key_id: int,
    *,
    client: AuthenticatedClient | Client,
    body: NewDeviceKVEntryUpdate,
) -> Response[DeviceKVEntry | DeviceKVEntryUpdate | Error]:
    """Create a KV entry update by DeviceID and Key ID

    Args:
        device_id (str):
        key_id (int):
        body (NewDeviceKVEntryUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DeviceKVEntry | DeviceKVEntryUpdate | Error]
    """

    kwargs = _get_kwargs(
        device_id=device_id,
        key_id=key_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    device_id: str,
    key_id: int,
    *,
    client: AuthenticatedClient | Client,
    body: NewDeviceKVEntryUpdate,
) -> DeviceKVEntry | DeviceKVEntryUpdate | Error | None:
    """Create a KV entry update by DeviceID and Key ID

    Args:
        device_id (str):
        key_id (int):
        body (NewDeviceKVEntryUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DeviceKVEntry | DeviceKVEntryUpdate | Error
    """

    return sync_detailed(
        device_id=device_id,
        key_id=key_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    device_id: str,
    key_id: int,
    *,
    client: AuthenticatedClient | Client,
    body: NewDeviceKVEntryUpdate,
) -> Response[DeviceKVEntry | DeviceKVEntryUpdate | Error]:
    """Create a KV entry update by DeviceID and Key ID

    Args:
        device_id (str):
        key_id (int):
        body (NewDeviceKVEntryUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DeviceKVEntry | DeviceKVEntryUpdate | Error]
    """

    kwargs = _get_kwargs(
        device_id=device_id,
        key_id=key_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    device_id: str,
    key_id: int,
    *,
    client: AuthenticatedClient | Client,
    body: NewDeviceKVEntryUpdate,
) -> DeviceKVEntry | DeviceKVEntryUpdate | Error | None:
    """Create a KV entry update by DeviceID and Key ID

    Args:
        device_id (str):
        key_id (int):
        body (NewDeviceKVEntryUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DeviceKVEntry | DeviceKVEntryUpdate | Error
    """

    return (
        await asyncio_detailed(
            device_id=device_id,
            key_id=key_id,
            client=client,
            body=body,
        )
    ).parsed
