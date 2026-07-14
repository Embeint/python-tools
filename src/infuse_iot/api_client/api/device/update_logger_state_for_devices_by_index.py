from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error import Error
from ...models.logger_state_for_devices_by_index_update_body import LoggerStateForDevicesByIndexUpdateBody
from ...models.logger_state_for_devices_by_index_update_response import LoggerStateForDevicesByIndexUpdateResponse
from ...types import Response


def _get_kwargs(
    index: int,
    *,
    body: LoggerStateForDevicesByIndexUpdateBody,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/device/loggerState/{index}/".format(
            index=quote(str(index), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Error | LoggerStateForDevicesByIndexUpdateResponse | None:
    if response.status_code == 200:
        response_200 = LoggerStateForDevicesByIndexUpdateResponse.from_dict(response.json())

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
) -> Response[Error | LoggerStateForDevicesByIndexUpdateResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    index: int,
    *,
    client: AuthenticatedClient | Client,
    body: LoggerStateForDevicesByIndexUpdateBody,
) -> Response[Error | LoggerStateForDevicesByIndexUpdateResponse]:
    """Update logger state for a group of devices

    Args:
        index (int):
        body (LoggerStateForDevicesByIndexUpdateBody): Body for updating logger states for devices
            by index

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Error | LoggerStateForDevicesByIndexUpdateResponse]
    """

    kwargs = _get_kwargs(
        index=index,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    index: int,
    *,
    client: AuthenticatedClient | Client,
    body: LoggerStateForDevicesByIndexUpdateBody,
) -> Error | LoggerStateForDevicesByIndexUpdateResponse | None:
    """Update logger state for a group of devices

    Args:
        index (int):
        body (LoggerStateForDevicesByIndexUpdateBody): Body for updating logger states for devices
            by index

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Error | LoggerStateForDevicesByIndexUpdateResponse
    """

    return sync_detailed(
        index=index,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    index: int,
    *,
    client: AuthenticatedClient | Client,
    body: LoggerStateForDevicesByIndexUpdateBody,
) -> Response[Error | LoggerStateForDevicesByIndexUpdateResponse]:
    """Update logger state for a group of devices

    Args:
        index (int):
        body (LoggerStateForDevicesByIndexUpdateBody): Body for updating logger states for devices
            by index

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Error | LoggerStateForDevicesByIndexUpdateResponse]
    """

    kwargs = _get_kwargs(
        index=index,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    index: int,
    *,
    client: AuthenticatedClient | Client,
    body: LoggerStateForDevicesByIndexUpdateBody,
) -> Error | LoggerStateForDevicesByIndexUpdateResponse | None:
    """Update logger state for a group of devices

    Args:
        index (int):
        body (LoggerStateForDevicesByIndexUpdateBody): Body for updating logger states for devices
            by index

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Error | LoggerStateForDevicesByIndexUpdateResponse
    """

    return (
        await asyncio_detailed(
            index=index,
            client=client,
            body=body,
        )
    ).parsed
