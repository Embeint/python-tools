from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error import Error
from ...models.get_all_organisations_order_by import GetAllOrganisationsOrderBy
from ...models.get_all_organisations_order_dir import GetAllOrganisationsOrderDir
from ...models.organisation import Organisation
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
    order_by: GetAllOrganisationsOrderBy | Unset = GetAllOrganisationsOrderBy.CREATEDAT,
    order_dir: GetAllOrganisationsOrderDir | Unset = GetAllOrganisationsOrderDir.ASC,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["limit"] = limit

    params["offset"] = offset

    json_order_by: str | Unset = UNSET
    if not isinstance(order_by, Unset):
        json_order_by = order_by.value

    params["orderBy"] = json_order_by

    json_order_dir: str | Unset = UNSET
    if not isinstance(order_dir, Unset):
        json_order_dir = order_dir.value

    params["orderDir"] = json_order_dir

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/organisation",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Error | list[Organisation] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = Organisation.from_dict(response_200_item_data)

            response_200.append(response_200_item)

        return response_200

    if response.status_code == 500:
        response_500 = Error.from_dict(response.json())

        return response_500

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Error | list[Organisation]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
    order_by: GetAllOrganisationsOrderBy | Unset = GetAllOrganisationsOrderBy.CREATEDAT,
    order_dir: GetAllOrganisationsOrderDir | Unset = GetAllOrganisationsOrderDir.ASC,
) -> Response[Error | list[Organisation]]:
    """Get all organisations that user has access to

    Args:
        limit (int | Unset): Maximum number of items to return Default: 100.
        offset (int | Unset): Number of items to skip before starting to return results (for
            pagination) Default: 0.
        order_by (GetAllOrganisationsOrderBy | Unset):  Default:
            GetAllOrganisationsOrderBy.CREATEDAT.
        order_dir (GetAllOrganisationsOrderDir | Unset):  Default:
            GetAllOrganisationsOrderDir.ASC.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Error | list[Organisation]]
    """

    kwargs = _get_kwargs(
        limit=limit,
        offset=offset,
        order_by=order_by,
        order_dir=order_dir,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
    order_by: GetAllOrganisationsOrderBy | Unset = GetAllOrganisationsOrderBy.CREATEDAT,
    order_dir: GetAllOrganisationsOrderDir | Unset = GetAllOrganisationsOrderDir.ASC,
) -> Error | list[Organisation] | None:
    """Get all organisations that user has access to

    Args:
        limit (int | Unset): Maximum number of items to return Default: 100.
        offset (int | Unset): Number of items to skip before starting to return results (for
            pagination) Default: 0.
        order_by (GetAllOrganisationsOrderBy | Unset):  Default:
            GetAllOrganisationsOrderBy.CREATEDAT.
        order_dir (GetAllOrganisationsOrderDir | Unset):  Default:
            GetAllOrganisationsOrderDir.ASC.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Error | list[Organisation]
    """

    return sync_detailed(
        client=client,
        limit=limit,
        offset=offset,
        order_by=order_by,
        order_dir=order_dir,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
    order_by: GetAllOrganisationsOrderBy | Unset = GetAllOrganisationsOrderBy.CREATEDAT,
    order_dir: GetAllOrganisationsOrderDir | Unset = GetAllOrganisationsOrderDir.ASC,
) -> Response[Error | list[Organisation]]:
    """Get all organisations that user has access to

    Args:
        limit (int | Unset): Maximum number of items to return Default: 100.
        offset (int | Unset): Number of items to skip before starting to return results (for
            pagination) Default: 0.
        order_by (GetAllOrganisationsOrderBy | Unset):  Default:
            GetAllOrganisationsOrderBy.CREATEDAT.
        order_dir (GetAllOrganisationsOrderDir | Unset):  Default:
            GetAllOrganisationsOrderDir.ASC.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Error | list[Organisation]]
    """

    kwargs = _get_kwargs(
        limit=limit,
        offset=offset,
        order_by=order_by,
        order_dir=order_dir,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
    order_by: GetAllOrganisationsOrderBy | Unset = GetAllOrganisationsOrderBy.CREATEDAT,
    order_dir: GetAllOrganisationsOrderDir | Unset = GetAllOrganisationsOrderDir.ASC,
) -> Error | list[Organisation] | None:
    """Get all organisations that user has access to

    Args:
        limit (int | Unset): Maximum number of items to return Default: 100.
        offset (int | Unset): Number of items to skip before starting to return results (for
            pagination) Default: 0.
        order_by (GetAllOrganisationsOrderBy | Unset):  Default:
            GetAllOrganisationsOrderBy.CREATEDAT.
        order_dir (GetAllOrganisationsOrderDir | Unset):  Default:
            GetAllOrganisationsOrderDir.ASC.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Error | list[Organisation]
    """

    return (
        await asyncio_detailed(
            client=client,
            limit=limit,
            offset=offset,
            order_by=order_by,
            order_dir=order_dir,
        )
    ).parsed
