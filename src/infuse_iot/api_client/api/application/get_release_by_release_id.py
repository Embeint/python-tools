from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.application_release import ApplicationRelease
from ...models.error import Error
from ...types import Response


def _get_kwargs(
    release_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/release/{release_id}".format(
            release_id=quote(str(release_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ApplicationRelease | Error | None:
    if response.status_code == 200:
        response_200 = ApplicationRelease.from_dict(response.json())

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

    if response.status_code == 500:
        response_500 = Error.from_dict(response.json())

        return response_500

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[ApplicationRelease | Error]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    release_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[ApplicationRelease | Error]:
    """Get a release by release ID

    Args:
        release_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApplicationRelease | Error]
    """

    kwargs = _get_kwargs(
        release_id=release_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    release_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> ApplicationRelease | Error | None:
    """Get a release by release ID

    Args:
        release_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApplicationRelease | Error
    """

    return sync_detailed(
        release_id=release_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    release_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[ApplicationRelease | Error]:
    """Get a release by release ID

    Args:
        release_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApplicationRelease | Error]
    """

    kwargs = _get_kwargs(
        release_id=release_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    release_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> ApplicationRelease | Error | None:
    """Get a release by release ID

    Args:
        release_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApplicationRelease | Error
    """

    return (
        await asyncio_detailed(
            release_id=release_id,
            client=client,
        )
    ).parsed
