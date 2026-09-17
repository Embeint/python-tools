#!/usr/bin/env python3

import os
from http import HTTPStatus
from types import ModuleType
from typing import Any, cast
from unittest.mock import Mock, call

from infuse_iot.api_client.models.error import Error
from infuse_iot.api_client.types import Response
from infuse_iot.util.api import fetch_all

assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"


def _response(status: HTTPStatus, parsed: Any, content: bytes = b"") -> Response[Any]:
    return Response(status_code=status, content=content, headers={}, parsed=parsed)


def test_fetch_all_uses_detailed_responses_and_fetches_every_page():
    endpoint = Mock(spec=["sync_detailed"])
    endpoint.sync_detailed.side_effect = [
        _response(HTTPStatus.OK, list(range(100))),
        _response(HTTPStatus.OK, [100]),
    ]

    result = fetch_all(cast(ModuleType, endpoint), client="client")

    assert result == list(range(101))
    assert endpoint.sync_detailed.call_args_list == [
        call(limit=100, offset=0, client="client"),
        call(limit=100, offset=100, client="client"),
    ]


def test_fetch_all_returns_parsed_error_from_later_page():
    error = Error(code=500, message="query failed")
    endpoint = Mock(spec=["sync_detailed"])
    endpoint.sync_detailed.side_effect = [
        _response(HTTPStatus.OK, list(range(100))),
        _response(HTTPStatus.INTERNAL_SERVER_ERROR, error),
    ]

    result = fetch_all(cast(ModuleType, endpoint))

    assert result is error


def test_fetch_all_converts_unparsed_failure_to_error():
    endpoint = Mock(spec=["sync_detailed"])
    endpoint.sync_detailed.return_value = _response(
        HTTPStatus.BAD_GATEWAY,
        None,
        b"upstream unavailable",
    )

    result = fetch_all(cast(ModuleType, endpoint))

    assert result == Error(code=502, message="upstream unavailable")
