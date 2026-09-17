from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.board import Board
from ...models.get_boards_order_by import GetBoardsOrderBy
from ...models.get_boards_order_dir import GetBoardsOrderDir
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    organisation_id: UUID,
    include_public: bool | Unset = False,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
    order_dir: GetBoardsOrderDir | Unset = GetBoardsOrderDir.ASC,
    order_by: GetBoardsOrderBy | Unset = GetBoardsOrderBy.CREATEDAT,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_organisation_id = str(organisation_id)
    params["organisationId"] = json_organisation_id

    params["includePublic"] = include_public

    params["limit"] = limit

    params["offset"] = offset

    json_order_dir: str | Unset = UNSET
    if not isinstance(order_dir, Unset):
        json_order_dir = order_dir.value

    params["orderDir"] = json_order_dir

    json_order_by: str | Unset = UNSET
    if not isinstance(order_by, Unset):
        json_order_by = order_by.value

    params["orderBy"] = json_order_by

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/board",
        "params": params,
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> list[Board] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = Board.from_dict(response_200_item_data)

            response_200.append(response_200_item)

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[list[Board]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    organisation_id: UUID,
    include_public: bool | Unset = False,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
    order_dir: GetBoardsOrderDir | Unset = GetBoardsOrderDir.ASC,
    order_by: GetBoardsOrderBy | Unset = GetBoardsOrderBy.CREATEDAT,
) -> Response[list[Board]]:
    """Get all boards in an organisation

    Args:
        organisation_id (UUID):
        include_public (bool | Unset):  Default: False.
        limit (int | Unset): Maximum number of items to return Default: 100.
        offset (int | Unset): Number of items to skip before starting to return results (for
            pagination) Default: 0.
        order_dir (GetBoardsOrderDir | Unset):  Default: GetBoardsOrderDir.ASC.
        order_by (GetBoardsOrderBy | Unset):  Default: GetBoardsOrderBy.CREATEDAT.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[list[Board]]
    """

    kwargs = _get_kwargs(
        organisation_id=organisation_id,
        include_public=include_public,
        limit=limit,
        offset=offset,
        order_dir=order_dir,
        order_by=order_by,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    organisation_id: UUID,
    include_public: bool | Unset = False,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
    order_dir: GetBoardsOrderDir | Unset = GetBoardsOrderDir.ASC,
    order_by: GetBoardsOrderBy | Unset = GetBoardsOrderBy.CREATEDAT,
) -> list[Board] | None:
    """Get all boards in an organisation

    Args:
        organisation_id (UUID):
        include_public (bool | Unset):  Default: False.
        limit (int | Unset): Maximum number of items to return Default: 100.
        offset (int | Unset): Number of items to skip before starting to return results (for
            pagination) Default: 0.
        order_dir (GetBoardsOrderDir | Unset):  Default: GetBoardsOrderDir.ASC.
        order_by (GetBoardsOrderBy | Unset):  Default: GetBoardsOrderBy.CREATEDAT.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        list[Board]
    """

    return sync_detailed(
        client=client,
        organisation_id=organisation_id,
        include_public=include_public,
        limit=limit,
        offset=offset,
        order_dir=order_dir,
        order_by=order_by,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    organisation_id: UUID,
    include_public: bool | Unset = False,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
    order_dir: GetBoardsOrderDir | Unset = GetBoardsOrderDir.ASC,
    order_by: GetBoardsOrderBy | Unset = GetBoardsOrderBy.CREATEDAT,
) -> Response[list[Board]]:
    """Get all boards in an organisation

    Args:
        organisation_id (UUID):
        include_public (bool | Unset):  Default: False.
        limit (int | Unset): Maximum number of items to return Default: 100.
        offset (int | Unset): Number of items to skip before starting to return results (for
            pagination) Default: 0.
        order_dir (GetBoardsOrderDir | Unset):  Default: GetBoardsOrderDir.ASC.
        order_by (GetBoardsOrderBy | Unset):  Default: GetBoardsOrderBy.CREATEDAT.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[list[Board]]
    """

    kwargs = _get_kwargs(
        organisation_id=organisation_id,
        include_public=include_public,
        limit=limit,
        offset=offset,
        order_dir=order_dir,
        order_by=order_by,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    organisation_id: UUID,
    include_public: bool | Unset = False,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
    order_dir: GetBoardsOrderDir | Unset = GetBoardsOrderDir.ASC,
    order_by: GetBoardsOrderBy | Unset = GetBoardsOrderBy.CREATEDAT,
) -> list[Board] | None:
    """Get all boards in an organisation

    Args:
        organisation_id (UUID):
        include_public (bool | Unset):  Default: False.
        limit (int | Unset): Maximum number of items to return Default: 100.
        offset (int | Unset): Number of items to skip before starting to return results (for
            pagination) Default: 0.
        order_dir (GetBoardsOrderDir | Unset):  Default: GetBoardsOrderDir.ASC.
        order_by (GetBoardsOrderBy | Unset):  Default: GetBoardsOrderBy.CREATEDAT.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        list[Board]
    """

    return (
        await asyncio_detailed(
            client=client,
            organisation_id=organisation_id,
            include_public=include_public,
            limit=limit,
            offset=offset,
            order_dir=order_dir,
            order_by=order_by,
        )
    ).parsed
