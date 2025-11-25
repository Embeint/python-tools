from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.device_entry_update_status import DeviceEntryUpdateStatus
from ...models.device_kv_entry_update import DeviceKVEntryUpdate
from ...types import UNSET, Response, Unset


def _get_kwargs(
    device_id: str,
    key_id: int,
    *,
    status: Unset | DeviceEntryUpdateStatus = UNSET,
    limit: Unset | int = 100,
    offset: Unset | int = 0,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_status: Unset | str = UNSET
    if not isinstance(status, Unset):
        json_status = status.value

    params["status"] = json_status

    params["limit"] = limit

    params["offset"] = offset

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": f"/device/deviceId/{device_id}/kv/entries/{key_id}/updates",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> list["DeviceKVEntryUpdate"] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = DeviceKVEntryUpdate.from_dict(response_200_item_data)

            response_200.append(response_200_item)

        return response_200
    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[list["DeviceKVEntryUpdate"]]:
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
    status: Unset | DeviceEntryUpdateStatus = UNSET,
    limit: Unset | int = 100,
    offset: Unset | int = 0,
) -> Response[list["DeviceKVEntryUpdate"]]:
    """Get KV entry updates by DeviceID and Key ID

    Args:
        device_id (str):
        key_id (int):
        status (Union[Unset, DeviceEntryUpdateStatus]): Status of device KV entry update
        limit (Union[Unset, int]):  Default: 100.
        offset (Union[Unset, int]):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[list['DeviceKVEntryUpdate']]
    """

    kwargs = _get_kwargs(
        device_id=device_id,
        key_id=key_id,
        status=status,
        limit=limit,
        offset=offset,
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
    status: Unset | DeviceEntryUpdateStatus = UNSET,
    limit: Unset | int = 100,
    offset: Unset | int = 0,
) -> list["DeviceKVEntryUpdate"] | None:
    """Get KV entry updates by DeviceID and Key ID

    Args:
        device_id (str):
        key_id (int):
        status (Union[Unset, DeviceEntryUpdateStatus]): Status of device KV entry update
        limit (Union[Unset, int]):  Default: 100.
        offset (Union[Unset, int]):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        list['DeviceKVEntryUpdate']
    """

    return sync_detailed(
        device_id=device_id,
        key_id=key_id,
        client=client,
        status=status,
        limit=limit,
        offset=offset,
    ).parsed


async def asyncio_detailed(
    device_id: str,
    key_id: int,
    *,
    client: AuthenticatedClient | Client,
    status: Unset | DeviceEntryUpdateStatus = UNSET,
    limit: Unset | int = 100,
    offset: Unset | int = 0,
) -> Response[list["DeviceKVEntryUpdate"]]:
    """Get KV entry updates by DeviceID and Key ID

    Args:
        device_id (str):
        key_id (int):
        status (Union[Unset, DeviceEntryUpdateStatus]): Status of device KV entry update
        limit (Union[Unset, int]):  Default: 100.
        offset (Union[Unset, int]):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[list['DeviceKVEntryUpdate']]
    """

    kwargs = _get_kwargs(
        device_id=device_id,
        key_id=key_id,
        status=status,
        limit=limit,
        offset=offset,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    device_id: str,
    key_id: int,
    *,
    client: AuthenticatedClient | Client,
    status: Unset | DeviceEntryUpdateStatus = UNSET,
    limit: Unset | int = 100,
    offset: Unset | int = 0,
) -> list["DeviceKVEntryUpdate"] | None:
    """Get KV entry updates by DeviceID and Key ID

    Args:
        device_id (str):
        key_id (int):
        status (Union[Unset, DeviceEntryUpdateStatus]): Status of device KV entry update
        limit (Union[Unset, int]):  Default: 100.
        offset (Union[Unset, int]):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        list['DeviceKVEntryUpdate']
    """

    return (
        await asyncio_detailed(
            device_id=device_id,
            key_id=key_id,
            client=client,
            status=status,
            limit=limit,
            offset=offset,
        )
    ).parsed
