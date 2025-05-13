from http import HTTPStatus
from typing import Any, Optional, Union

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.definitions_kv_response import DefinitionsKVResponse
from ...models.error import Error
from ...types import Response


def _get_kwargs(
    version: int,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": f"/defs/kv/{version}",
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[DefinitionsKVResponse, Error]]:
    if response.status_code == 200:
        response_200 = DefinitionsKVResponse.from_dict(response.json())

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
) -> Response[Union[DefinitionsKVResponse, Error]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    version: int,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Response[Union[DefinitionsKVResponse, Error]]:
    """Get key-value definitions by version

    Args:
        version (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[DefinitionsKVResponse, Error]]
    """

    kwargs = _get_kwargs(
        version=version,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    version: int,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Optional[Union[DefinitionsKVResponse, Error]]:
    """Get key-value definitions by version

    Args:
        version (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[DefinitionsKVResponse, Error]
    """

    return sync_detailed(
        version=version,
        client=client,
    ).parsed


async def asyncio_detailed(
    version: int,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Response[Union[DefinitionsKVResponse, Error]]:
    """Get key-value definitions by version

    Args:
        version (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[DefinitionsKVResponse, Error]]
    """

    kwargs = _get_kwargs(
        version=version,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    version: int,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Optional[Union[DefinitionsKVResponse, Error]]:
    """Get key-value definitions by version

    Args:
        version (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[DefinitionsKVResponse, Error]
    """

    return (
        await asyncio_detailed(
            version=version,
            client=client,
        )
    ).parsed
