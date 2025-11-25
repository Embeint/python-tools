from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.device import Device
from ...types import Response


def _get_kwargs(
    soc: str,
    mcu_id: str,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": f"/device/soc/{soc}/mcuId/{mcu_id}",
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Any | Device | None:
    if response.status_code == 200:
        response_200 = Device.from_dict(response.json())

        return response_200
    if response.status_code == 404:
        response_404 = cast(Any, None)
        return response_404
    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[Any | Device]:
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
) -> Response[Any | Device]:
    """Get a device by SoC and MCU ID

    Args:
        soc (str):
        mcu_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Any, Device]]
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
) -> Any | Device | None:
    """Get a device by SoC and MCU ID

    Args:
        soc (str):
        mcu_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Any, Device]
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
) -> Response[Any | Device]:
    """Get a device by SoC and MCU ID

    Args:
        soc (str):
        mcu_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Any, Device]]
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
) -> Any | Device | None:
    """Get a device by SoC and MCU ID

    Args:
        soc (str):
        mcu_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Any, Device]
    """

    return (
        await asyncio_detailed(
            soc=soc,
            mcu_id=mcu_id,
            client=client,
        )
    ).parsed
