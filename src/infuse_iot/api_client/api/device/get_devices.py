from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.device import Device
from ...models.get_devices_order_by import GetDevicesOrderBy
from ...models.get_devices_order_dir import GetDevicesOrderDir
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    organisation_id: UUID,
    board_ids: list[UUID] | Unset = UNSET,
    metadata_name: str | Unset = UNSET,
    metadata_value: str | Unset = UNSET,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
    order_dir: GetDevicesOrderDir | Unset = GetDevicesOrderDir.ASC,
    order_by: GetDevicesOrderBy | Unset = GetDevicesOrderBy.CREATEDAT,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_organisation_id = str(organisation_id)
    params["organisationId"] = json_organisation_id

    json_board_ids: list[str] | Unset = UNSET
    if not isinstance(board_ids, Unset):
        json_board_ids = []
        for board_ids_item_data in board_ids:
            board_ids_item = str(board_ids_item_data)
            json_board_ids.append(board_ids_item)

    params["boardIds"] = json_board_ids

    params["metadataName"] = metadata_name

    params["metadataValue"] = metadata_value

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
        "url": "/device",
        "params": params,
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> list[Device] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = Device.from_dict(response_200_item_data)

            response_200.append(response_200_item)

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[list[Device]]:
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
    board_ids: list[UUID] | Unset = UNSET,
    metadata_name: str | Unset = UNSET,
    metadata_value: str | Unset = UNSET,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
    order_dir: GetDevicesOrderDir | Unset = GetDevicesOrderDir.ASC,
    order_by: GetDevicesOrderBy | Unset = GetDevicesOrderBy.CREATEDAT,
) -> Response[list[Device]]:
    """Get all devices in an organisation

    Args:
        organisation_id (UUID):
        board_ids (list[UUID] | Unset):
        metadata_name (str | Unset):
        metadata_value (str | Unset):
        limit (int | Unset): Maximum number of items to return Default: 100.
        offset (int | Unset): Number of items to skip before starting to return results (for
            pagination) Default: 0.
        order_dir (GetDevicesOrderDir | Unset):  Default: GetDevicesOrderDir.ASC.
        order_by (GetDevicesOrderBy | Unset):  Default: GetDevicesOrderBy.CREATEDAT.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[list[Device]]
    """

    kwargs = _get_kwargs(
        organisation_id=organisation_id,
        board_ids=board_ids,
        metadata_name=metadata_name,
        metadata_value=metadata_value,
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
    board_ids: list[UUID] | Unset = UNSET,
    metadata_name: str | Unset = UNSET,
    metadata_value: str | Unset = UNSET,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
    order_dir: GetDevicesOrderDir | Unset = GetDevicesOrderDir.ASC,
    order_by: GetDevicesOrderBy | Unset = GetDevicesOrderBy.CREATEDAT,
) -> list[Device] | None:
    """Get all devices in an organisation

    Args:
        organisation_id (UUID):
        board_ids (list[UUID] | Unset):
        metadata_name (str | Unset):
        metadata_value (str | Unset):
        limit (int | Unset): Maximum number of items to return Default: 100.
        offset (int | Unset): Number of items to skip before starting to return results (for
            pagination) Default: 0.
        order_dir (GetDevicesOrderDir | Unset):  Default: GetDevicesOrderDir.ASC.
        order_by (GetDevicesOrderBy | Unset):  Default: GetDevicesOrderBy.CREATEDAT.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        list[Device]
    """

    return sync_detailed(
        client=client,
        organisation_id=organisation_id,
        board_ids=board_ids,
        metadata_name=metadata_name,
        metadata_value=metadata_value,
        limit=limit,
        offset=offset,
        order_dir=order_dir,
        order_by=order_by,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    organisation_id: UUID,
    board_ids: list[UUID] | Unset = UNSET,
    metadata_name: str | Unset = UNSET,
    metadata_value: str | Unset = UNSET,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
    order_dir: GetDevicesOrderDir | Unset = GetDevicesOrderDir.ASC,
    order_by: GetDevicesOrderBy | Unset = GetDevicesOrderBy.CREATEDAT,
) -> Response[list[Device]]:
    """Get all devices in an organisation

    Args:
        organisation_id (UUID):
        board_ids (list[UUID] | Unset):
        metadata_name (str | Unset):
        metadata_value (str | Unset):
        limit (int | Unset): Maximum number of items to return Default: 100.
        offset (int | Unset): Number of items to skip before starting to return results (for
            pagination) Default: 0.
        order_dir (GetDevicesOrderDir | Unset):  Default: GetDevicesOrderDir.ASC.
        order_by (GetDevicesOrderBy | Unset):  Default: GetDevicesOrderBy.CREATEDAT.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[list[Device]]
    """

    kwargs = _get_kwargs(
        organisation_id=organisation_id,
        board_ids=board_ids,
        metadata_name=metadata_name,
        metadata_value=metadata_value,
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
    board_ids: list[UUID] | Unset = UNSET,
    metadata_name: str | Unset = UNSET,
    metadata_value: str | Unset = UNSET,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
    order_dir: GetDevicesOrderDir | Unset = GetDevicesOrderDir.ASC,
    order_by: GetDevicesOrderBy | Unset = GetDevicesOrderBy.CREATEDAT,
) -> list[Device] | None:
    """Get all devices in an organisation

    Args:
        organisation_id (UUID):
        board_ids (list[UUID] | Unset):
        metadata_name (str | Unset):
        metadata_value (str | Unset):
        limit (int | Unset): Maximum number of items to return Default: 100.
        offset (int | Unset): Number of items to skip before starting to return results (for
            pagination) Default: 0.
        order_dir (GetDevicesOrderDir | Unset):  Default: GetDevicesOrderDir.ASC.
        order_by (GetDevicesOrderBy | Unset):  Default: GetDevicesOrderBy.CREATEDAT.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        list[Device]
    """

    return (
        await asyncio_detailed(
            client=client,
            organisation_id=organisation_id,
            board_ids=board_ids,
            metadata_name=metadata_name,
            metadata_value=metadata_value,
            limit=limit,
            offset=offset,
            order_dir=order_dir,
            order_by=order_by,
        )
    ).parsed
