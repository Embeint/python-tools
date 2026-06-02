from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.application_release_diff import ApplicationReleaseDiff
from ...models.error import Error
from ...types import Response


def _get_kwargs(
    id: UUID,
    application_id: int,
    release_id: str,
    diff_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/organisation/id/{id}/applications/{application_id}/releases/{release_id}/diffs/{diff_id}".format(
            id=quote(str(id), safe=""),
            application_id=quote(str(application_id), safe=""),
            release_id=quote(str(release_id), safe=""),
            diff_id=quote(str(diff_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ApplicationReleaseDiff | Error | None:
    if response.status_code == 200:
        response_200 = ApplicationReleaseDiff.from_dict(response.json())

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
) -> Response[ApplicationReleaseDiff | Error]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    id: UUID,
    application_id: int,
    release_id: str,
    diff_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[ApplicationReleaseDiff | Error]:
    """Get a diff by organisation ID, application ID, release ID and diff ID

    Args:
        id (UUID):
        application_id (int):
        release_id (str):
        diff_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApplicationReleaseDiff | Error]
    """

    kwargs = _get_kwargs(
        id=id,
        application_id=application_id,
        release_id=release_id,
        diff_id=diff_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: UUID,
    application_id: int,
    release_id: str,
    diff_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> ApplicationReleaseDiff | Error | None:
    """Get a diff by organisation ID, application ID, release ID and diff ID

    Args:
        id (UUID):
        application_id (int):
        release_id (str):
        diff_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApplicationReleaseDiff | Error
    """

    return sync_detailed(
        id=id,
        application_id=application_id,
        release_id=release_id,
        diff_id=diff_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    id: UUID,
    application_id: int,
    release_id: str,
    diff_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[ApplicationReleaseDiff | Error]:
    """Get a diff by organisation ID, application ID, release ID and diff ID

    Args:
        id (UUID):
        application_id (int):
        release_id (str):
        diff_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApplicationReleaseDiff | Error]
    """

    kwargs = _get_kwargs(
        id=id,
        application_id=application_id,
        release_id=release_id,
        diff_id=diff_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: UUID,
    application_id: int,
    release_id: str,
    diff_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> ApplicationReleaseDiff | Error | None:
    """Get a diff by organisation ID, application ID, release ID and diff ID

    Args:
        id (UUID):
        application_id (int):
        release_id (str):
        diff_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApplicationReleaseDiff | Error
    """

    return (
        await asyncio_detailed(
            id=id,
            application_id=application_id,
            release_id=release_id,
            diff_id=diff_id,
            client=client,
        )
    ).parsed
