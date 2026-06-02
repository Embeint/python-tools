from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.device_logger_state import DeviceLoggerState
from ...models.error import Error
from ...types import Response


def _get_kwargs(
    device_id: str,
    index: int,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/device/deviceId/{device_id}/loggerState/{index}".format(
            device_id=quote(str(device_id), safe=""),
            index=quote(str(index), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> DeviceLoggerState | Error | None:
    if response.status_code == 200:
        response_200 = DeviceLoggerState.from_dict(response.json())

        return response_200

    if response.status_code == 404:
        response_404 = Error.from_dict(response.json())

        return response_404

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[DeviceLoggerState | Error]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    device_id: str,
    index: int,
    *,
    client: AuthenticatedClient | Client,
) -> Response[DeviceLoggerState | Error]:
    """Get logger state by DeviceID and index

    Args:
        device_id (str):
        index (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DeviceLoggerState | Error]
    """

    kwargs = _get_kwargs(
        device_id=device_id,
        index=index,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    device_id: str,
    index: int,
    *,
    client: AuthenticatedClient | Client,
) -> DeviceLoggerState | Error | None:
    """Get logger state by DeviceID and index

    Args:
        device_id (str):
        index (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DeviceLoggerState | Error
    """

    return sync_detailed(
        device_id=device_id,
        index=index,
        client=client,
    ).parsed


async def asyncio_detailed(
    device_id: str,
    index: int,
    *,
    client: AuthenticatedClient | Client,
) -> Response[DeviceLoggerState | Error]:
    """Get logger state by DeviceID and index

    Args:
        device_id (str):
        index (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DeviceLoggerState | Error]
    """

    kwargs = _get_kwargs(
        device_id=device_id,
        index=index,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    device_id: str,
    index: int,
    *,
    client: AuthenticatedClient | Client,
) -> DeviceLoggerState | Error | None:
    """Get logger state by DeviceID and index

    Args:
        device_id (str):
        index (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DeviceLoggerState | Error
    """

    return (
        await asyncio_detailed(
            device_id=device_id,
            index=index,
            client=client,
        )
    ).parsed
