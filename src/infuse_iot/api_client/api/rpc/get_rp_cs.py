import datetime
from http import HTTPStatus
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.downlink_message_status import DownlinkMessageStatus
from ...models.error import Error
from ...models.rpc_message import RpcMessage
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    organisation_id: Union[Unset, UUID] = UNSET,
    device_id: Union[Unset, str] = UNSET,
    status: Union[Unset, DownlinkMessageStatus] = UNSET,
    start_time: Union[Unset, datetime.datetime] = UNSET,
    end_time: Union[Unset, datetime.datetime] = UNSET,
    limit: Union[Unset, int] = 10,
) -> Dict[str, Any]:
    params: Dict[str, Any] = {}

    json_organisation_id: Union[Unset, str] = UNSET
    if not isinstance(organisation_id, Unset):
        json_organisation_id = str(organisation_id)
    params["organisationId"] = json_organisation_id

    params["deviceId"] = device_id

    json_status: Union[Unset, str] = UNSET
    if not isinstance(status, Unset):
        json_status = status.value

    params["status"] = json_status

    json_start_time: Union[Unset, str] = UNSET
    if not isinstance(start_time, Unset):
        json_start_time = start_time.isoformat()
    params["startTime"] = json_start_time

    json_end_time: Union[Unset, str] = UNSET
    if not isinstance(end_time, Unset):
        json_end_time = end_time.isoformat()
    params["endTime"] = json_end_time

    params["limit"] = limit

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: Dict[str, Any] = {
        "method": "get",
        "url": "/rpc",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[Error, List["RpcMessage"]]]:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = RpcMessage.from_dict(response_200_item_data)

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
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Response[Union[Error, List["RpcMessage"]]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: Union[AuthenticatedClient, Client],
    organisation_id: Union[Unset, UUID] = UNSET,
    device_id: Union[Unset, str] = UNSET,
    status: Union[Unset, DownlinkMessageStatus] = UNSET,
    start_time: Union[Unset, datetime.datetime] = UNSET,
    end_time: Union[Unset, datetime.datetime] = UNSET,
    limit: Union[Unset, int] = 10,
) -> Response[Union[Error, List["RpcMessage"]]]:
    """Get RPC messages

    Args:
        organisation_id (Union[Unset, UUID]): ID of organisation
        device_id (Union[Unset, str]): 8 byte DeviceID as a hex string (if not provided will be
            auto-generated) Example: d291d4d66bf0a955.
        status (Union[Unset, DownlinkMessageStatus]): Status of downlink message
        start_time (Union[Unset, datetime.datetime]): The start time of the query (only return
            items on or after this time)
        end_time (Union[Unset, datetime.datetime]): The end time of the query (only return items
            on or before this time)
        limit (Union[Unset, int]): Maximum number of items to return Default: 10.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Error, List['RpcMessage']]]
    """

    kwargs = _get_kwargs(
        organisation_id=organisation_id,
        device_id=device_id,
        status=status,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: Union[AuthenticatedClient, Client],
    organisation_id: Union[Unset, UUID] = UNSET,
    device_id: Union[Unset, str] = UNSET,
    status: Union[Unset, DownlinkMessageStatus] = UNSET,
    start_time: Union[Unset, datetime.datetime] = UNSET,
    end_time: Union[Unset, datetime.datetime] = UNSET,
    limit: Union[Unset, int] = 10,
) -> Optional[Union[Error, List["RpcMessage"]]]:
    """Get RPC messages

    Args:
        organisation_id (Union[Unset, UUID]): ID of organisation
        device_id (Union[Unset, str]): 8 byte DeviceID as a hex string (if not provided will be
            auto-generated) Example: d291d4d66bf0a955.
        status (Union[Unset, DownlinkMessageStatus]): Status of downlink message
        start_time (Union[Unset, datetime.datetime]): The start time of the query (only return
            items on or after this time)
        end_time (Union[Unset, datetime.datetime]): The end time of the query (only return items
            on or before this time)
        limit (Union[Unset, int]): Maximum number of items to return Default: 10.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Error, List['RpcMessage']]
    """

    return sync_detailed(
        client=client,
        organisation_id=organisation_id,
        device_id=device_id,
        status=status,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    ).parsed


async def asyncio_detailed(
    *,
    client: Union[AuthenticatedClient, Client],
    organisation_id: Union[Unset, UUID] = UNSET,
    device_id: Union[Unset, str] = UNSET,
    status: Union[Unset, DownlinkMessageStatus] = UNSET,
    start_time: Union[Unset, datetime.datetime] = UNSET,
    end_time: Union[Unset, datetime.datetime] = UNSET,
    limit: Union[Unset, int] = 10,
) -> Response[Union[Error, List["RpcMessage"]]]:
    """Get RPC messages

    Args:
        organisation_id (Union[Unset, UUID]): ID of organisation
        device_id (Union[Unset, str]): 8 byte DeviceID as a hex string (if not provided will be
            auto-generated) Example: d291d4d66bf0a955.
        status (Union[Unset, DownlinkMessageStatus]): Status of downlink message
        start_time (Union[Unset, datetime.datetime]): The start time of the query (only return
            items on or after this time)
        end_time (Union[Unset, datetime.datetime]): The end time of the query (only return items
            on or before this time)
        limit (Union[Unset, int]): Maximum number of items to return Default: 10.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Error, List['RpcMessage']]]
    """

    kwargs = _get_kwargs(
        organisation_id=organisation_id,
        device_id=device_id,
        status=status,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: Union[AuthenticatedClient, Client],
    organisation_id: Union[Unset, UUID] = UNSET,
    device_id: Union[Unset, str] = UNSET,
    status: Union[Unset, DownlinkMessageStatus] = UNSET,
    start_time: Union[Unset, datetime.datetime] = UNSET,
    end_time: Union[Unset, datetime.datetime] = UNSET,
    limit: Union[Unset, int] = 10,
) -> Optional[Union[Error, List["RpcMessage"]]]:
    """Get RPC messages

    Args:
        organisation_id (Union[Unset, UUID]): ID of organisation
        device_id (Union[Unset, str]): 8 byte DeviceID as a hex string (if not provided will be
            auto-generated) Example: d291d4d66bf0a955.
        status (Union[Unset, DownlinkMessageStatus]): Status of downlink message
        start_time (Union[Unset, datetime.datetime]): The start time of the query (only return
            items on or after this time)
        end_time (Union[Unset, datetime.datetime]): The end time of the query (only return items
            on or before this time)
        limit (Union[Unset, int]): Maximum number of items to return Default: 10.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Error, List['RpcMessage']]
    """

    return (
        await asyncio_detailed(
            client=client,
            organisation_id=organisation_id,
            device_id=device_id,
            status=status,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
    ).parsed
