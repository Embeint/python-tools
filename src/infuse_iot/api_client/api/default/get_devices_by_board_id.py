from http import HTTPStatus
from typing import Any, Dict, List, Optional, Union, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.device import Device
from ...types import UNSET, Response, Unset


def _get_kwargs(
    id: str,
    *,
    metadata_name: Union[Unset, str] = UNSET,
    metadata_value: Union[Unset, str] = UNSET,
) -> Dict[str, Any]:
    params: Dict[str, Any] = {}

    params["metadataName"] = metadata_name

    params["metadataValue"] = metadata_value

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: Dict[str, Any] = {
        "method": "get",
        "url": f"/board/id/{id}/devices",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[Any, List["Device"]]]:
    if response.status_code == HTTPStatus.OK:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = Device.from_dict(response_200_item_data)

            response_200.append(response_200_item)

        return response_200
    if response.status_code == HTTPStatus.NOT_FOUND:
        response_404 = cast(Any, None)
        return response_404
    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Response[Union[Any, List["Device"]]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    id: str,
    *,
    client: Union[AuthenticatedClient, Client],
    metadata_name: Union[Unset, str] = UNSET,
    metadata_value: Union[Unset, str] = UNSET,
) -> Response[Union[Any, List["Device"]]]:
    """Get devices by board id and optional metadata field

    Args:
        id (str):
        metadata_name (Union[Unset, str]):
        metadata_value (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Any, List['Device']]]
    """

    kwargs = _get_kwargs(
        id=id,
        metadata_name=metadata_name,
        metadata_value=metadata_value,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    *,
    client: Union[AuthenticatedClient, Client],
    metadata_name: Union[Unset, str] = UNSET,
    metadata_value: Union[Unset, str] = UNSET,
) -> Optional[Union[Any, List["Device"]]]:
    """Get devices by board id and optional metadata field

    Args:
        id (str):
        metadata_name (Union[Unset, str]):
        metadata_value (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Any, List['Device']]
    """

    return sync_detailed(
        id=id,
        client=client,
        metadata_name=metadata_name,
        metadata_value=metadata_value,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: Union[AuthenticatedClient, Client],
    metadata_name: Union[Unset, str] = UNSET,
    metadata_value: Union[Unset, str] = UNSET,
) -> Response[Union[Any, List["Device"]]]:
    """Get devices by board id and optional metadata field

    Args:
        id (str):
        metadata_name (Union[Unset, str]):
        metadata_value (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Any, List['Device']]]
    """

    kwargs = _get_kwargs(
        id=id,
        metadata_name=metadata_name,
        metadata_value=metadata_value,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    *,
    client: Union[AuthenticatedClient, Client],
    metadata_name: Union[Unset, str] = UNSET,
    metadata_value: Union[Unset, str] = UNSET,
) -> Optional[Union[Any, List["Device"]]]:
    """Get devices by board id and optional metadata field

    Args:
        id (str):
        metadata_name (Union[Unset, str]):
        metadata_value (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Any, List['Device']]
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
            metadata_name=metadata_name,
            metadata_value=metadata_value,
        )
    ).parsed
