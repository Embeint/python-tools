from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.device_kv_entry_update import DeviceKVEntryUpdate
from ...types import Response


def _get_kwargs(
    device_id: str,
    key_id: int,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": f"/device/deviceId/{device_id}/kv/entries/{key_id}/updates",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | DeviceKVEntryUpdate | None:
    if response.status_code == 200:
        response_200 = DeviceKVEntryUpdate.from_dict(response.json())

        return response_200
    if response.status_code == 204:
        response_204 = cast(Any, None)
        return response_204
    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Any | DeviceKVEntryUpdate]:
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
) -> Response[Any | DeviceKVEntryUpdate]:
    """Cancel pending KV entry update by DeviceID and Key ID

    Args:
        device_id (str):
        key_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Any, DeviceKVEntryUpdate]]
    """

    kwargs = _get_kwargs(
        device_id=device_id,
        key_id=key_id,
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
) -> Any | DeviceKVEntryUpdate | None:
    """Cancel pending KV entry update by DeviceID and Key ID

    Args:
        device_id (str):
        key_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Any, DeviceKVEntryUpdate]
    """

    return sync_detailed(
        device_id=device_id,
        key_id=key_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    device_id: str,
    key_id: int,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any | DeviceKVEntryUpdate]:
    """Cancel pending KV entry update by DeviceID and Key ID

    Args:
        device_id (str):
        key_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Any, DeviceKVEntryUpdate]]
    """

    kwargs = _get_kwargs(
        device_id=device_id,
        key_id=key_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    device_id: str,
    key_id: int,
    *,
    client: AuthenticatedClient | Client,
) -> Any | DeviceKVEntryUpdate | None:
    """Cancel pending KV entry update by DeviceID and Key ID

    Args:
        device_id (str):
        key_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Any, DeviceKVEntryUpdate]
    """

    return (
        await asyncio_detailed(
            device_id=device_id,
            key_id=key_id,
            client=client,
        )
    ).parsed
