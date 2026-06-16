from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.device_application_update import DeviceApplicationUpdate
from ...models.error import Error
from ...types import Response


def _get_kwargs(
    device_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/device/deviceId/{device_id}/application/updates".format(
            device_id=quote(str(device_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | DeviceApplicationUpdate | Error | None:
    if response.status_code == 200:
        response_200 = DeviceApplicationUpdate.from_dict(response.json())

        return response_200

    if response.status_code == 204:
        response_204 = cast(Any, None)
        return response_204

    if response.status_code == 403:
        response_403 = Error.from_dict(response.json())

        return response_403

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
) -> Response[Any | DeviceApplicationUpdate | Error]:
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
) -> Response[Any | DeviceApplicationUpdate | Error]:
    """Cancel pending device application update by DeviceID.

     Cancel a pending device application update by DeviceID. If an RPC has already been sent to the
    device for the pending update, this will not cancel the update on the device, but it will prevent
    any further attempts to update the device application until a new update is created.

    Args:
        device_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | DeviceApplicationUpdate | Error]
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
) -> Any | DeviceApplicationUpdate | Error | None:
    """Cancel pending device application update by DeviceID.

     Cancel a pending device application update by DeviceID. If an RPC has already been sent to the
    device for the pending update, this will not cancel the update on the device, but it will prevent
    any further attempts to update the device application until a new update is created.

    Args:
        device_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | DeviceApplicationUpdate | Error
    """

    return sync_detailed(
        device_id=device_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    device_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any | DeviceApplicationUpdate | Error]:
    """Cancel pending device application update by DeviceID.

     Cancel a pending device application update by DeviceID. If an RPC has already been sent to the
    device for the pending update, this will not cancel the update on the device, but it will prevent
    any further attempts to update the device application until a new update is created.

    Args:
        device_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | DeviceApplicationUpdate | Error]
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
) -> Any | DeviceApplicationUpdate | Error | None:
    """Cancel pending device application update by DeviceID.

     Cancel a pending device application update by DeviceID. If an RPC has already been sent to the
    device for the pending update, this will not cancel the update on the device, but it will prevent
    any further attempts to update the device application until a new update is created.

    Args:
        device_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | DeviceApplicationUpdate | Error
    """

    return (
        await asyncio_detailed(
            device_id=device_id,
            client=client,
        )
    ).parsed
