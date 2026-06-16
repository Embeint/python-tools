from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.device_application_state import DeviceApplicationState
from ...models.error import Error
from ...types import Response


def _get_kwargs(
    device_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/device/deviceId/{device_id}/application/state".format(
            device_id=quote(str(device_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> DeviceApplicationState | Error | None:
    if response.status_code == 200:
        response_200 = DeviceApplicationState.from_dict(response.json())

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
) -> Response[DeviceApplicationState | Error]:
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
) -> Response[DeviceApplicationState | Error]:
    """Get device application state by DeviceID

    Args:
        device_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DeviceApplicationState | Error]
    """

    kwargs = _get_kwargs(
        device_id=device_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    device_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> DeviceApplicationState | Error | None:
    """Get device application state by DeviceID

    Args:
        device_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DeviceApplicationState | Error
    """

    return sync_detailed(
        device_id=device_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    device_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[DeviceApplicationState | Error]:
    """Get device application state by DeviceID

    Args:
        device_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DeviceApplicationState | Error]
    """

    kwargs = _get_kwargs(
        device_id=device_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    device_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> DeviceApplicationState | Error | None:
    """Get device application state by DeviceID

    Args:
        device_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DeviceApplicationState | Error
    """

    return (
        await asyncio_detailed(
            device_id=device_id,
            client=client,
        )
    ).parsed
