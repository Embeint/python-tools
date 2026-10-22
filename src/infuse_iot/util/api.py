#!/usr/bin/env python3

"""Helpers for the generated cloud API client"""

import json
import sys
from collections.abc import Collection
from http import HTTPStatus
from types import ModuleType
from typing import Any, TypeVar

from infuse_iot.api_client.models.error import Error
from infuse_iot.api_client.types import Response

_PAGE_SIZE = 100
# Unexpected responses can be entire HTML pages from proxies
_MAX_BODY_LEN = 200

T = TypeVar("T")


def _json_message(response: Response[Any]) -> str | None:
    """`message` of a JSON response body, if present"""
    try:
        body_json = json.loads(response.content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if isinstance(body_json, dict) and "message" in body_json:
        return str(body_json["message"])
    return None


def _truncated_body(response: Response[Any]) -> str:
    body = response.content.decode("utf-8", errors="replace").strip()
    if len(body) > _MAX_BODY_LEN:
        body = body[:_MAX_BODY_LEN] + "..."
    return body


def format_api_error(response: Response[Any]) -> str:
    """Describe a failed cloud API response for display to the user.

    Uses the parsed `Error` message where available. Status codes that are not
    documented in the API specification are not parsed, so fall back to the
    `message` of a JSON body, otherwise the raw body of the response.
    """
    status = f"<{int(response.status_code)} {response.status_code.phrase}>"
    if isinstance(response.parsed, Error):
        return f"{status} {response.parsed.message}"
    message = _json_message(response)
    if message is not None:
        return f"{status} {message}"
    return f"{status} Unexpected response: {_truncated_body(response) or '(empty body)'}"


def check_api_response(response: Response[T | Error], context: str) -> T:
    """Terminate the tool on a failed cloud API request.

    Accepts the result of a generated `sync_detailed` call or `fetch_all`. Any
    failure exits with a message prefixed by `context`.
    """
    parsed = response.parsed
    if parsed is not None and not isinstance(parsed, Error):
        return parsed
    sys.exit(f"{context}: {format_api_error(response)}")


def check_api_response_allow_errors(
    response: Response[T | Error], context: str, allowed_errors: Collection[HTTPStatus | int]
) -> T | Error:
    """Terminate the tool on a failed cloud API request, except for expected failures.

    As `check_api_response`, but failures whose HTTP status is in
    `allowed_errors` are returned to the caller as an `Error` to handle, e.g.
    `allowed_errors=[HTTPStatus.NOT_FOUND]`.
    """
    parsed = response.parsed
    if parsed is not None and not isinstance(parsed, Error):
        return parsed
    if response.status_code in allowed_errors:
        if isinstance(parsed, Error):
            return parsed
        message = _json_message(response)
        if message is None:
            message = _truncated_body(response)
        return Error(code=int(response.status_code), message=message)
    sys.exit(f"{context}: {format_api_error(response)}")


def fetch_all(endpoint: ModuleType, **kwargs: Any) -> Response[Any]:
    """Fetch every page of a paginated list endpoint.

    The generated wrappers default to `limit=10`, so calling `sync_detailed`
    directly returns a silently truncated list. Pass the endpoint module rather
    than calling it, e.g. `fetch_all(get_boards, client=client, ...)`.

    Returns a response containing the accumulated list, or the response of the
    first failing page so callers can provide the failure details to the user.
    """
    items: list[Any] = []
    offset = 0

    while True:
        response = endpoint.sync_detailed(limit=_PAGE_SIZE, offset=offset, **kwargs)
        page = response.parsed
        if not isinstance(page, list):
            return response
        items.extend(page)
        if len(page) < _PAGE_SIZE:
            return Response(status_code=response.status_code, content=b"", headers=response.headers, parsed=items)
        offset += len(page)
