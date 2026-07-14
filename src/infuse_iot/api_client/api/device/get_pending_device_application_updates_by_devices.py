from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error import Error
from ...models.pending_device_application_updates_by_devices_body import PendingDeviceApplicationUpdatesByDevicesBody
from ...models.pending_device_application_updates_by_devices_response import (
    PendingDeviceApplicationUpdatesByDevicesResponse,
)
from ...types import Response


def _get_kwargs(
    *,
    body: PendingDeviceApplicationUpdatesByDevicesBody,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/device/application/updates/pending/query",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Error | PendingDeviceApplicationUpdatesByDevicesResponse | None:
    if response.status_code == 200:
        response_200 = PendingDeviceApplicationUpdatesByDevicesResponse.from_dict(response.json())

        return response_200

    if response.status_code == 400:
        response_400 = Error.from_dict(response.json())

        return response_400

    if response.status_code == 500:
        response_500 = Error.from_dict(response.json())

        return response_500

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Error | PendingDeviceApplicationUpdatesByDevicesResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: PendingDeviceApplicationUpdatesByDevicesBody,
) -> Response[Error | PendingDeviceApplicationUpdatesByDevicesResponse]:
    """Get pending device application update with downlink messages for a group of devices

    Args:
        body (PendingDeviceApplicationUpdatesByDevicesBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Error | PendingDeviceApplicationUpdatesByDevicesResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    body: PendingDeviceApplicationUpdatesByDevicesBody,
) -> Error | PendingDeviceApplicationUpdatesByDevicesResponse | None:
    """Get pending device application update with downlink messages for a group of devices

    Args:
        body (PendingDeviceApplicationUpdatesByDevicesBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Error | PendingDeviceApplicationUpdatesByDevicesResponse
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: PendingDeviceApplicationUpdatesByDevicesBody,
) -> Response[Error | PendingDeviceApplicationUpdatesByDevicesResponse]:
    """Get pending device application update with downlink messages for a group of devices

    Args:
        body (PendingDeviceApplicationUpdatesByDevicesBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Error | PendingDeviceApplicationUpdatesByDevicesResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: PendingDeviceApplicationUpdatesByDevicesBody,
) -> Error | PendingDeviceApplicationUpdatesByDevicesResponse | None:
    """Get pending device application update with downlink messages for a group of devices

    Args:
        body (PendingDeviceApplicationUpdatesByDevicesBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Error | PendingDeviceApplicationUpdatesByDevicesResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
