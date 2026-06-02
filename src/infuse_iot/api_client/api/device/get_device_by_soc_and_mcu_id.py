from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.device import Device
from ...models.error import Error
from ...types import Response


def _get_kwargs(
    soc: str,
    mcu_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/device/soc/{soc}/mcuId/{mcu_id}".format(
            soc=quote(str(soc), safe=""),
            mcu_id=quote(str(mcu_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Device | Error | None:
    if response.status_code == 200:
        response_200 = Device.from_dict(response.json())

        return response_200

    if response.status_code == 404:
        response_404 = Error.from_dict(response.json())

        return response_404

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[Device | Error]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    soc: str,
    mcu_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Device | Error]:
    """Get a device by SoC and MCU ID

    Args:
        soc (str):
        mcu_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Device | Error]
    """

    kwargs = _get_kwargs(
        soc=soc,
        mcu_id=mcu_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    soc: str,
    mcu_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Device | Error | None:
    """Get a device by SoC and MCU ID

    Args:
        soc (str):
        mcu_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Device | Error
    """

    return sync_detailed(
        soc=soc,
        mcu_id=mcu_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    soc: str,
    mcu_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Device | Error]:
    """Get a device by SoC and MCU ID

    Args:
        soc (str):
        mcu_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Device | Error]
    """

    kwargs = _get_kwargs(
        soc=soc,
        mcu_id=mcu_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    soc: str,
    mcu_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Device | Error | None:
    """Get a device by SoC and MCU ID

    Args:
        soc (str):
        mcu_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Device | Error
    """

    return (
        await asyncio_detailed(
            soc=soc,
            mcu_id=mcu_id,
            client=client,
        )
    ).parsed
