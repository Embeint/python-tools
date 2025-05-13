from http import HTTPStatus
from typing import Any, Optional, Union

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.coap_file_stats import COAPFileStats
from ...models.error import Error
from ...types import Response


def _get_kwargs(
    filename: str,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": f"/coap/file/{filename}/stats",
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[COAPFileStats, Error]]:
    if response.status_code == 200:
        response_200 = COAPFileStats.from_dict(response.json())

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
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Response[Union[COAPFileStats, Error]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    filename: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Response[Union[COAPFileStats, Error]]:
    """Get statistics for a file on the COAP server

    Args:
        filename (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[COAPFileStats, Error]]
    """

    kwargs = _get_kwargs(
        filename=filename,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    filename: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Optional[Union[COAPFileStats, Error]]:
    """Get statistics for a file on the COAP server

    Args:
        filename (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[COAPFileStats, Error]
    """

    return sync_detailed(
        filename=filename,
        client=client,
    ).parsed


async def asyncio_detailed(
    filename: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Response[Union[COAPFileStats, Error]]:
    """Get statistics for a file on the COAP server

    Args:
        filename (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[COAPFileStats, Error]]
    """

    kwargs = _get_kwargs(
        filename=filename,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    filename: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Optional[Union[COAPFileStats, Error]]:
    """Get statistics for a file on the COAP server

    Args:
        filename (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[COAPFileStats, Error]
    """

    return (
        await asyncio_detailed(
            filename=filename,
            client=client,
        )
    ).parsed
