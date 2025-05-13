from http import HTTPStatus
from typing import Any, Optional, Union, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.device_state import DeviceState
from ...types import Response


def _get_kwargs(
    device_id: str,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": f"/device/deviceId/{device_id}/state",
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[Any, DeviceState]]:
    if response.status_code == 200:
        response_200 = DeviceState.from_dict(response.json())

        return response_200
    if response.status_code == 404:
        response_404 = cast(Any, None)
        return response_404
    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Response[Union[Any, DeviceState]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    device_id: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Response[Union[Any, DeviceState]]:
    """Get device state by DeviceID

    Args:
        device_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Any, DeviceState]]
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
    client: Union[AuthenticatedClient, Client],
) -> Optional[Union[Any, DeviceState]]:
    """Get device state by DeviceID

    Args:
        device_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Any, DeviceState]
    """

    return sync_detailed(
        device_id=device_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    device_id: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Response[Union[Any, DeviceState]]:
    """Get device state by DeviceID

    Args:
        device_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Any, DeviceState]]
    """

    kwargs = _get_kwargs(
        device_id=device_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    device_id: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Optional[Union[Any, DeviceState]]:
    """Get device state by DeviceID

    Args:
        device_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Any, DeviceState]
    """

    return (
        await asyncio_detailed(
            device_id=device_id,
            client=client,
        )
    ).parsed
