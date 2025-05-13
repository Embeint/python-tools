from http import HTTPStatus
from typing import Any, Optional, Union

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.coap_files_list import COAPFilesList
from ...models.error import Error
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    regex: Union[Unset, str] = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["regex"] = regex

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/coap/files",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[COAPFilesList, Error]]:
    if response.status_code == 200:
        response_200 = COAPFilesList.from_dict(response.json())

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
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Response[Union[COAPFilesList, Error]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: Union[AuthenticatedClient, Client],
    regex: Union[Unset, str] = UNSET,
) -> Response[Union[COAPFilesList, Error]]:
    """Get a list of files on the COAP server

    Args:
        regex (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[COAPFilesList, Error]]
    """

    kwargs = _get_kwargs(
        regex=regex,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: Union[AuthenticatedClient, Client],
    regex: Union[Unset, str] = UNSET,
) -> Optional[Union[COAPFilesList, Error]]:
    """Get a list of files on the COAP server

    Args:
        regex (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[COAPFilesList, Error]
    """

    return sync_detailed(
        client=client,
        regex=regex,
    ).parsed


async def asyncio_detailed(
    *,
    client: Union[AuthenticatedClient, Client],
    regex: Union[Unset, str] = UNSET,
) -> Response[Union[COAPFilesList, Error]]:
    """Get a list of files on the COAP server

    Args:
        regex (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[COAPFilesList, Error]]
    """

    kwargs = _get_kwargs(
        regex=regex,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: Union[AuthenticatedClient, Client],
    regex: Union[Unset, str] = UNSET,
) -> Optional[Union[COAPFilesList, Error]]:
    """Get a list of files on the COAP server

    Args:
        regex (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[COAPFilesList, Error]
    """

    return (
        await asyncio_detailed(
            client=client,
            regex=regex,
        )
    ).parsed
