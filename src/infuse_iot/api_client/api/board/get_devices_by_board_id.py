from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.device import Device
from ...models.error import Error
from ...types import UNSET, Response, Unset


def _get_kwargs(
    id: UUID,
    *,
    metadata_name: str | Unset = UNSET,
    metadata_value: str | Unset = UNSET,
    limit: int | Unset = 10,
    offset: int | Unset = 0,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["metadataName"] = metadata_name

    params["metadataValue"] = metadata_value

    params["limit"] = limit

    params["offset"] = offset

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/board/id/{id}/devices".format(
            id=quote(str(id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Error | list[Device] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = Device.from_dict(response_200_item_data)

            response_200.append(response_200_item)

        return response_200

    if response.status_code == 404:
        response_404 = Error.from_dict(response.json())

        return response_404

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Error | list[Device]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    id: UUID,
    *,
    client: AuthenticatedClient | Client,
    metadata_name: str | Unset = UNSET,
    metadata_value: str | Unset = UNSET,
    limit: int | Unset = 10,
    offset: int | Unset = 0,
) -> Response[Error | list[Device]]:
    """Get devices by board id and optional metadata field

    Args:
        id (UUID):
        metadata_name (str | Unset):
        metadata_value (str | Unset):
        limit (int | Unset): Maximum number of items to return Default: 10.
        offset (int | Unset): Number of items to skip before starting to return results (for
            pagination) Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Error | list[Device]]
    """

    kwargs = _get_kwargs(
        id=id,
        metadata_name=metadata_name,
        metadata_value=metadata_value,
        limit=limit,
        offset=offset,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: UUID,
    *,
    client: AuthenticatedClient | Client,
    metadata_name: str | Unset = UNSET,
    metadata_value: str | Unset = UNSET,
    limit: int | Unset = 10,
    offset: int | Unset = 0,
) -> Error | list[Device] | None:
    """Get devices by board id and optional metadata field

    Args:
        id (UUID):
        metadata_name (str | Unset):
        metadata_value (str | Unset):
        limit (int | Unset): Maximum number of items to return Default: 10.
        offset (int | Unset): Number of items to skip before starting to return results (for
            pagination) Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Error | list[Device]
    """

    return sync_detailed(
        id=id,
        client=client,
        metadata_name=metadata_name,
        metadata_value=metadata_value,
        limit=limit,
        offset=offset,
    ).parsed


async def asyncio_detailed(
    id: UUID,
    *,
    client: AuthenticatedClient | Client,
    metadata_name: str | Unset = UNSET,
    metadata_value: str | Unset = UNSET,
    limit: int | Unset = 10,
    offset: int | Unset = 0,
) -> Response[Error | list[Device]]:
    """Get devices by board id and optional metadata field

    Args:
        id (UUID):
        metadata_name (str | Unset):
        metadata_value (str | Unset):
        limit (int | Unset): Maximum number of items to return Default: 10.
        offset (int | Unset): Number of items to skip before starting to return results (for
            pagination) Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Error | list[Device]]
    """

    kwargs = _get_kwargs(
        id=id,
        metadata_name=metadata_name,
        metadata_value=metadata_value,
        limit=limit,
        offset=offset,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: UUID,
    *,
    client: AuthenticatedClient | Client,
    metadata_name: str | Unset = UNSET,
    metadata_value: str | Unset = UNSET,
    limit: int | Unset = 10,
    offset: int | Unset = 0,
) -> Error | list[Device] | None:
    """Get devices by board id and optional metadata field

    Args:
        id (UUID):
        metadata_name (str | Unset):
        metadata_value (str | Unset):
        limit (int | Unset): Maximum number of items to return Default: 10.
        offset (int | Unset): Number of items to skip before starting to return results (for
            pagination) Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Error | list[Device]
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
            metadata_name=metadata_name,
            metadata_value=metadata_value,
            limit=limit,
            offset=offset,
        )
    ).parsed
