from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.application_release_diff import ApplicationReleaseDiff
from ...models.error import Error
from ...models.get_diffs_by_organisation_id_and_application_id_order_by import (
    GetDiffsByOrganisationIdAndApplicationIdOrderBy,
)
from ...models.get_diffs_by_organisation_id_and_application_id_order_dir import (
    GetDiffsByOrganisationIdAndApplicationIdOrderDir,
)
from ...types import UNSET, Response, Unset


def _get_kwargs(
    id: UUID,
    application_id: int,
    *,
    from_release_id: str | Unset = UNSET,
    to_release_id: str | Unset = UNSET,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
    order_dir: GetDiffsByOrganisationIdAndApplicationIdOrderDir
    | Unset = GetDiffsByOrganisationIdAndApplicationIdOrderDir.DESC,
    order_by: GetDiffsByOrganisationIdAndApplicationIdOrderBy
    | Unset = GetDiffsByOrganisationIdAndApplicationIdOrderBy.CREATEDAT,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["fromReleaseId"] = from_release_id

    params["toReleaseId"] = to_release_id

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
        "url": "/organisation/id/{id}/applications/{application_id}/diffs".format(
            id=quote(str(id), safe=""),
            application_id=quote(str(application_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Error | list[ApplicationReleaseDiff] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = ApplicationReleaseDiff.from_dict(response_200_item_data)

            response_200.append(response_200_item)

        return response_200

    if response.status_code == 400:
        response_400 = Error.from_dict(response.json())

        return response_400

    if response.status_code == 403:
        response_403 = Error.from_dict(response.json())

        return response_403

    if response.status_code == 404:
        response_404 = Error.from_dict(response.json())

        return response_404

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Error | list[ApplicationReleaseDiff]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    id: UUID,
    application_id: int,
    *,
    client: AuthenticatedClient | Client,
    from_release_id: str | Unset = UNSET,
    to_release_id: str | Unset = UNSET,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
    order_dir: GetDiffsByOrganisationIdAndApplicationIdOrderDir
    | Unset = GetDiffsByOrganisationIdAndApplicationIdOrderDir.DESC,
    order_by: GetDiffsByOrganisationIdAndApplicationIdOrderBy
    | Unset = GetDiffsByOrganisationIdAndApplicationIdOrderBy.CREATEDAT,
) -> Response[Error | list[ApplicationReleaseDiff]]:
    """Get release diffs for an application

     Get release diffs for an application. Filter by fromReleaseId, toReleaseId, or both. If both are
    provided, returns the matching diff between those releases.

    Args:
        id (UUID):
        application_id (int):
        from_release_id (str | Unset):
        to_release_id (str | Unset):
        limit (int | Unset): Maximum number of items to return Default: 100.
        offset (int | Unset):  Default: 0.
        order_dir (GetDiffsByOrganisationIdAndApplicationIdOrderDir | Unset):  Default:
            GetDiffsByOrganisationIdAndApplicationIdOrderDir.DESC.
        order_by (GetDiffsByOrganisationIdAndApplicationIdOrderBy | Unset):  Default:
            GetDiffsByOrganisationIdAndApplicationIdOrderBy.CREATEDAT.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Error | list[ApplicationReleaseDiff]]
    """

    kwargs = _get_kwargs(
        id=id,
        application_id=application_id,
        from_release_id=from_release_id,
        to_release_id=to_release_id,
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
    id: UUID,
    application_id: int,
    *,
    client: AuthenticatedClient | Client,
    from_release_id: str | Unset = UNSET,
    to_release_id: str | Unset = UNSET,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
    order_dir: GetDiffsByOrganisationIdAndApplicationIdOrderDir
    | Unset = GetDiffsByOrganisationIdAndApplicationIdOrderDir.DESC,
    order_by: GetDiffsByOrganisationIdAndApplicationIdOrderBy
    | Unset = GetDiffsByOrganisationIdAndApplicationIdOrderBy.CREATEDAT,
) -> Error | list[ApplicationReleaseDiff] | None:
    """Get release diffs for an application

     Get release diffs for an application. Filter by fromReleaseId, toReleaseId, or both. If both are
    provided, returns the matching diff between those releases.

    Args:
        id (UUID):
        application_id (int):
        from_release_id (str | Unset):
        to_release_id (str | Unset):
        limit (int | Unset): Maximum number of items to return Default: 100.
        offset (int | Unset):  Default: 0.
        order_dir (GetDiffsByOrganisationIdAndApplicationIdOrderDir | Unset):  Default:
            GetDiffsByOrganisationIdAndApplicationIdOrderDir.DESC.
        order_by (GetDiffsByOrganisationIdAndApplicationIdOrderBy | Unset):  Default:
            GetDiffsByOrganisationIdAndApplicationIdOrderBy.CREATEDAT.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Error | list[ApplicationReleaseDiff]
    """

    return sync_detailed(
        id=id,
        application_id=application_id,
        client=client,
        from_release_id=from_release_id,
        to_release_id=to_release_id,
        limit=limit,
        offset=offset,
        order_dir=order_dir,
        order_by=order_by,
    ).parsed


async def asyncio_detailed(
    id: UUID,
    application_id: int,
    *,
    client: AuthenticatedClient | Client,
    from_release_id: str | Unset = UNSET,
    to_release_id: str | Unset = UNSET,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
    order_dir: GetDiffsByOrganisationIdAndApplicationIdOrderDir
    | Unset = GetDiffsByOrganisationIdAndApplicationIdOrderDir.DESC,
    order_by: GetDiffsByOrganisationIdAndApplicationIdOrderBy
    | Unset = GetDiffsByOrganisationIdAndApplicationIdOrderBy.CREATEDAT,
) -> Response[Error | list[ApplicationReleaseDiff]]:
    """Get release diffs for an application

     Get release diffs for an application. Filter by fromReleaseId, toReleaseId, or both. If both are
    provided, returns the matching diff between those releases.

    Args:
        id (UUID):
        application_id (int):
        from_release_id (str | Unset):
        to_release_id (str | Unset):
        limit (int | Unset): Maximum number of items to return Default: 100.
        offset (int | Unset):  Default: 0.
        order_dir (GetDiffsByOrganisationIdAndApplicationIdOrderDir | Unset):  Default:
            GetDiffsByOrganisationIdAndApplicationIdOrderDir.DESC.
        order_by (GetDiffsByOrganisationIdAndApplicationIdOrderBy | Unset):  Default:
            GetDiffsByOrganisationIdAndApplicationIdOrderBy.CREATEDAT.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Error | list[ApplicationReleaseDiff]]
    """

    kwargs = _get_kwargs(
        id=id,
        application_id=application_id,
        from_release_id=from_release_id,
        to_release_id=to_release_id,
        limit=limit,
        offset=offset,
        order_dir=order_dir,
        order_by=order_by,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: UUID,
    application_id: int,
    *,
    client: AuthenticatedClient | Client,
    from_release_id: str | Unset = UNSET,
    to_release_id: str | Unset = UNSET,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
    order_dir: GetDiffsByOrganisationIdAndApplicationIdOrderDir
    | Unset = GetDiffsByOrganisationIdAndApplicationIdOrderDir.DESC,
    order_by: GetDiffsByOrganisationIdAndApplicationIdOrderBy
    | Unset = GetDiffsByOrganisationIdAndApplicationIdOrderBy.CREATEDAT,
) -> Error | list[ApplicationReleaseDiff] | None:
    """Get release diffs for an application

     Get release diffs for an application. Filter by fromReleaseId, toReleaseId, or both. If both are
    provided, returns the matching diff between those releases.

    Args:
        id (UUID):
        application_id (int):
        from_release_id (str | Unset):
        to_release_id (str | Unset):
        limit (int | Unset): Maximum number of items to return Default: 100.
        offset (int | Unset):  Default: 0.
        order_dir (GetDiffsByOrganisationIdAndApplicationIdOrderDir | Unset):  Default:
            GetDiffsByOrganisationIdAndApplicationIdOrderDir.DESC.
        order_by (GetDiffsByOrganisationIdAndApplicationIdOrderBy | Unset):  Default:
            GetDiffsByOrganisationIdAndApplicationIdOrderBy.CREATEDAT.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Error | list[ApplicationReleaseDiff]
    """

    return (
        await asyncio_detailed(
            id=id,
            application_id=application_id,
            client=client,
            from_release_id=from_release_id,
            to_release_id=to_release_id,
            limit=limit,
            offset=offset,
            order_dir=order_dir,
            order_by=order_by,
        )
    ).parsed
