from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.device_logger_state import DeviceLoggerState
from ...types import Response


def _get_kwargs(
    device_id: str,
    index: int,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": f"/device/deviceId/{device_id}/loggerState/{index}",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | DeviceLoggerState | None:
    if response.status_code == 200:
        response_200 = DeviceLoggerState.from_dict(response.json())

        return response_200
    if response.status_code == 404:
        response_404 = cast(Any, None)
        return response_404
    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Any | DeviceLoggerState]:
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
) -> Response[Any | DeviceLoggerState]:
    """Get logger state by DeviceID and index

    Args:
        device_id (str):
        index (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Any, DeviceLoggerState]]
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
) -> Any | DeviceLoggerState | None:
    """Get logger state by DeviceID and index

    Args:
        device_id (str):
        index (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Any, DeviceLoggerState]
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
) -> Response[Any | DeviceLoggerState]:
    """Get logger state by DeviceID and index

    Args:
        device_id (str):
        index (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Any, DeviceLoggerState]]
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
) -> Any | DeviceLoggerState | None:
    """Get logger state by DeviceID and index

    Args:
        device_id (str):
        index (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Any, DeviceLoggerState]
    """

    return (
        await asyncio_detailed(
            device_id=device_id,
            index=index,
            client=client,
        )
    ).parsed
