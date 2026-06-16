from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.device_application_update import DeviceApplicationUpdate
from ...models.device_application_update_status import DeviceApplicationUpdateStatus
from ...models.error import Error
from ...types import UNSET, Response, Unset


def _get_kwargs(
    device_id: str,
    *,
    status: DeviceApplicationUpdateStatus | Unset = UNSET,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_status: str | Unset = UNSET
    if not isinstance(status, Unset):
        json_status = status.value

    params["status"] = json_status

    params["limit"] = limit

    params["offset"] = offset

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/device/deviceId/{device_id}/application/updates".format(
            device_id=quote(str(device_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Error | list[DeviceApplicationUpdate] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = DeviceApplicationUpdate.from_dict(response_200_item_data)

            response_200.append(response_200_item)

        return response_200

    if response.status_code == 404:
        response_404 = Error.from_dict(response.json())

        return response_404

    if response.status_code == 500:
        response_500 = Error.from_dict(response.json())

        return response_500

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Error | list[DeviceApplicationUpdate]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    device_id: str,
    *,
    client: AuthenticatedClient | Client,
    status: DeviceApplicationUpdateStatus | Unset = UNSET,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
) -> Response[Error | list[DeviceApplicationUpdate]]:
    """Get device application updates by DeviceID

    Args:
        device_id (str):
        status (DeviceApplicationUpdateStatus | Unset): Status of device application update
        limit (int | Unset):  Default: 100.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Error | list[DeviceApplicationUpdate]]
    """

    kwargs = _get_kwargs(
        device_id=device_id,
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
    *,
    client: AuthenticatedClient | Client,
    status: DeviceApplicationUpdateStatus | Unset = UNSET,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
) -> Error | list[DeviceApplicationUpdate] | None:
    """Get device application updates by DeviceID

    Args:
        device_id (str):
        status (DeviceApplicationUpdateStatus | Unset): Status of device application update
        limit (int | Unset):  Default: 100.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Error | list[DeviceApplicationUpdate]
    """

    return sync_detailed(
        device_id=device_id,
        client=client,
        status=status,
        limit=limit,
        offset=offset,
    ).parsed


async def asyncio_detailed(
    device_id: str,
    *,
    client: AuthenticatedClient | Client,
    status: DeviceApplicationUpdateStatus | Unset = UNSET,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
) -> Response[Error | list[DeviceApplicationUpdate]]:
    """Get device application updates by DeviceID

    Args:
        device_id (str):
        status (DeviceApplicationUpdateStatus | Unset): Status of device application update
        limit (int | Unset):  Default: 100.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Error | list[DeviceApplicationUpdate]]
    """

    kwargs = _get_kwargs(
        device_id=device_id,
        status=status,
        limit=limit,
        offset=offset,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    device_id: str,
    *,
    client: AuthenticatedClient | Client,
    status: DeviceApplicationUpdateStatus | Unset = UNSET,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
) -> Error | list[DeviceApplicationUpdate] | None:
    """Get device application updates by DeviceID

    Args:
        device_id (str):
        status (DeviceApplicationUpdateStatus | Unset): Status of device application update
        limit (int | Unset):  Default: 100.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Error | list[DeviceApplicationUpdate]
    """

    return (
        await asyncio_detailed(
            device_id=device_id,
            client=client,
            status=status,
            limit=limit,
            offset=offset,
        )
    ).parsed
