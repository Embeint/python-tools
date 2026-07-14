from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error import Error
from ...models.logger_states_for_devices_by_index_body import LoggerStatesForDevicesByIndexBody
from ...models.logger_states_for_devices_by_index_response import LoggerStatesForDevicesByIndexResponse
from ...types import Response


def _get_kwargs(
    index: int,
    *,
    body: LoggerStatesForDevicesByIndexBody,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/device/loggerState/{index}/query".format(
            index=quote(str(index), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Error | LoggerStatesForDevicesByIndexResponse | None:
    if response.status_code == 200:
        response_200 = LoggerStatesForDevicesByIndexResponse.from_dict(response.json())

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
) -> Response[Error | LoggerStatesForDevicesByIndexResponse]:
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
    body: LoggerStatesForDevicesByIndexBody,
) -> Response[Error | LoggerStatesForDevicesByIndexResponse]:
    """Get logger states for a group of devices

    Args:
        index (int):
        body (LoggerStatesForDevicesByIndexBody): Body for getting logger states for devices by
            index

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Error | LoggerStatesForDevicesByIndexResponse]
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
    body: LoggerStatesForDevicesByIndexBody,
) -> Error | LoggerStatesForDevicesByIndexResponse | None:
    """Get logger states for a group of devices

    Args:
        index (int):
        body (LoggerStatesForDevicesByIndexBody): Body for getting logger states for devices by
            index

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Error | LoggerStatesForDevicesByIndexResponse
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
    body: LoggerStatesForDevicesByIndexBody,
) -> Response[Error | LoggerStatesForDevicesByIndexResponse]:
    """Get logger states for a group of devices

    Args:
        index (int):
        body (LoggerStatesForDevicesByIndexBody): Body for getting logger states for devices by
            index

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Error | LoggerStatesForDevicesByIndexResponse]
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
    body: LoggerStatesForDevicesByIndexBody,
) -> Error | LoggerStatesForDevicesByIndexResponse | None:
    """Get logger states for a group of devices

    Args:
        index (int):
        body (LoggerStatesForDevicesByIndexBody): Body for getting logger states for devices by
            index

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Error | LoggerStatesForDevicesByIndexResponse
    """

    return (
        await asyncio_detailed(
            index=index,
            client=client,
            body=body,
        )
    ).parsed
