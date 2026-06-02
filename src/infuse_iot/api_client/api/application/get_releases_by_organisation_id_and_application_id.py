from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.application_release import ApplicationRelease
from ...models.error import Error
from ...types import UNSET, Response, Unset


def _get_kwargs(
    id: UUID,
    application_id: int,
    *,
    version_major: int | Unset = UNSET,
    version_minor: int | Unset = UNSET,
    version_revision: int | Unset = UNSET,
    version_build_num: int | Unset = UNSET,
    board_id: UUID | Unset = UNSET,
    board_target: str | Unset = UNSET,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["versionMajor"] = version_major

    params["versionMinor"] = version_minor

    params["versionRevision"] = version_revision

    params["versionBuildNum"] = version_build_num

    json_board_id: str | Unset = UNSET
    if not isinstance(board_id, Unset):
        json_board_id = str(board_id)
    params["boardId"] = json_board_id

    params["boardTarget"] = board_target

    params["limit"] = limit

    params["offset"] = offset

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/organisation/id/{id}/applications/{application_id}/releases".format(
            id=quote(str(id), safe=""),
            application_id=quote(str(application_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Error | list[ApplicationRelease] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = ApplicationRelease.from_dict(response_200_item_data)

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
) -> Response[Error | list[ApplicationRelease]]:
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
    version_major: int | Unset = UNSET,
    version_minor: int | Unset = UNSET,
    version_revision: int | Unset = UNSET,
    version_build_num: int | Unset = UNSET,
    board_id: UUID | Unset = UNSET,
    board_target: str | Unset = UNSET,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
) -> Response[Error | list[ApplicationRelease]]:
    """Get all releases for an application

    Args:
        id (UUID):
        application_id (int):
        version_major (int | Unset): Major version number of application release
        version_minor (int | Unset): Minor version number of application release
        version_revision (int | Unset): Revision version number of application release
        version_build_num (int | Unset): Build version number of application release
        board_id (UUID | Unset):
        board_target (str | Unset):
        limit (int | Unset):  Default: 100.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Error | list[ApplicationRelease]]
    """

    kwargs = _get_kwargs(
        id=id,
        application_id=application_id,
        version_major=version_major,
        version_minor=version_minor,
        version_revision=version_revision,
        version_build_num=version_build_num,
        board_id=board_id,
        board_target=board_target,
        limit=limit,
        offset=offset,
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
    version_major: int | Unset = UNSET,
    version_minor: int | Unset = UNSET,
    version_revision: int | Unset = UNSET,
    version_build_num: int | Unset = UNSET,
    board_id: UUID | Unset = UNSET,
    board_target: str | Unset = UNSET,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
) -> Error | list[ApplicationRelease] | None:
    """Get all releases for an application

    Args:
        id (UUID):
        application_id (int):
        version_major (int | Unset): Major version number of application release
        version_minor (int | Unset): Minor version number of application release
        version_revision (int | Unset): Revision version number of application release
        version_build_num (int | Unset): Build version number of application release
        board_id (UUID | Unset):
        board_target (str | Unset):
        limit (int | Unset):  Default: 100.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Error | list[ApplicationRelease]
    """

    return sync_detailed(
        id=id,
        application_id=application_id,
        client=client,
        version_major=version_major,
        version_minor=version_minor,
        version_revision=version_revision,
        version_build_num=version_build_num,
        board_id=board_id,
        board_target=board_target,
        limit=limit,
        offset=offset,
    ).parsed


async def asyncio_detailed(
    id: UUID,
    application_id: int,
    *,
    client: AuthenticatedClient | Client,
    version_major: int | Unset = UNSET,
    version_minor: int | Unset = UNSET,
    version_revision: int | Unset = UNSET,
    version_build_num: int | Unset = UNSET,
    board_id: UUID | Unset = UNSET,
    board_target: str | Unset = UNSET,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
) -> Response[Error | list[ApplicationRelease]]:
    """Get all releases for an application

    Args:
        id (UUID):
        application_id (int):
        version_major (int | Unset): Major version number of application release
        version_minor (int | Unset): Minor version number of application release
        version_revision (int | Unset): Revision version number of application release
        version_build_num (int | Unset): Build version number of application release
        board_id (UUID | Unset):
        board_target (str | Unset):
        limit (int | Unset):  Default: 100.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Error | list[ApplicationRelease]]
    """

    kwargs = _get_kwargs(
        id=id,
        application_id=application_id,
        version_major=version_major,
        version_minor=version_minor,
        version_revision=version_revision,
        version_build_num=version_build_num,
        board_id=board_id,
        board_target=board_target,
        limit=limit,
        offset=offset,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: UUID,
    application_id: int,
    *,
    client: AuthenticatedClient | Client,
    version_major: int | Unset = UNSET,
    version_minor: int | Unset = UNSET,
    version_revision: int | Unset = UNSET,
    version_build_num: int | Unset = UNSET,
    board_id: UUID | Unset = UNSET,
    board_target: str | Unset = UNSET,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
) -> Error | list[ApplicationRelease] | None:
    """Get all releases for an application

    Args:
        id (UUID):
        application_id (int):
        version_major (int | Unset): Major version number of application release
        version_minor (int | Unset): Minor version number of application release
        version_revision (int | Unset): Revision version number of application release
        version_build_num (int | Unset): Build version number of application release
        board_id (UUID | Unset):
        board_target (str | Unset):
        limit (int | Unset):  Default: 100.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Error | list[ApplicationRelease]
    """

    return (
        await asyncio_detailed(
            id=id,
            application_id=application_id,
            client=client,
            version_major=version_major,
            version_minor=version_minor,
            version_revision=version_revision,
            version_build_num=version_build_num,
            board_id=board_id,
            board_target=board_target,
            limit=limit,
            offset=offset,
        )
    ).parsed
