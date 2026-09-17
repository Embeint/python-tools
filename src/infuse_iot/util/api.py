#!/usr/bin/env python3

"""Helpers for the generated cloud API client"""

from types import ModuleType
from typing import Any

from infuse_iot.api_client.models.error import Error

_PAGE_SIZE = 100


def fetch_all(endpoint: ModuleType, **kwargs: Any) -> Any:
    """Fetch every page of a paginated list endpoint.

    The generated wrappers default to `limit=10`, so calling `sync` directly
    returns a silently truncated list. Pass the endpoint module rather than
    calling it, e.g. `fetch_all(get_boards, client=client, ...)`.

    Returns the accumulated list, or an `Error` from the first failing page so
    callers can provide the failure details to the user.
    """
    items: list[Any] = []
    offset = 0

    while True:
        response = endpoint.sync_detailed(limit=_PAGE_SIZE, offset=offset, **kwargs)
        page = response.parsed
        if not isinstance(page, list):
            if isinstance(page, Error):
                return page
            return Error(
                code=int(response.status_code),
                message=response.content.decode("utf-8", errors="replace"),
            )
        items.extend(page)
        if len(page) < _PAGE_SIZE:
            return items
        offset += len(page)
