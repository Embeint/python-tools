#!/usr/bin/env python3

"""Helpers for the generated cloud API client"""

from types import ModuleType
from typing import Any

_PAGE_SIZE = 100


def fetch_all(endpoint: ModuleType, **kwargs: Any) -> Any:
    """Fetch every page of a paginated list endpoint.

    The generated wrappers default to `limit=10`, so calling `sync` directly
    returns a silently truncated list. Pass the endpoint module rather than
    calling it, e.g. `fetch_all(get_boards, client=client, ...)`.

    Returns the accumulated list, or the `Error`/`None` from the first failing
    page so callers can keep their existing error handling.
    """
    items: list[Any] = []
    offset = 0

    while True:
        page = endpoint.sync(limit=_PAGE_SIZE, offset=offset, **kwargs)
        if not isinstance(page, list):
            # Propagate `Error`/`None` unless earlier pages already succeeded
            return items if items else page
        items.extend(page)
        if len(page) < _PAGE_SIZE:
            return items
        offset += len(page)
