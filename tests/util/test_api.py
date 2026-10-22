#!/usr/bin/env python3

import os
from http import HTTPStatus
from types import ModuleType
from typing import Any, cast
from unittest.mock import Mock, call

import pytest

from infuse_iot.api_client.models.error import Error
from infuse_iot.api_client.types import Response
from infuse_iot.util.api import check_api_response, check_api_response_allow_errors, fetch_all, format_api_error

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

    assert result.status_code == HTTPStatus.OK
    assert result.parsed == list(range(101))
    assert endpoint.sync_detailed.call_args_list == [
        call(limit=100, offset=0, client="client"),
        call(limit=100, offset=100, client="client"),
    ]


def test_fetch_all_returns_failing_page_response():
    failure = _response(HTTPStatus.INTERNAL_SERVER_ERROR, Error(code=500, message="query failed"))
    endpoint = Mock(spec=["sync_detailed"])
    endpoint.sync_detailed.side_effect = [
        _response(HTTPStatus.OK, list(range(100))),
        failure,
    ]

    result = fetch_all(cast(ModuleType, endpoint))

    assert result is failure


def test_check_api_response_returns_parsed_success():
    assert check_api_response(_response(HTTPStatus.OK, [1, 2]), "Query") == [1, 2]


def test_check_api_response_exits_on_parsed_error():
    response = _response(HTTPStatus.FORBIDDEN, Error(code=403, message="denied"))

    with pytest.raises(SystemExit, match=r"^Query: <403 Forbidden> denied$"):
        check_api_response(response, "Query")


def test_check_api_response_exits_on_undocumented_status():
    response = _response(HTTPStatus.BAD_GATEWAY, None, b"upstream unavailable\n")

    with pytest.raises(SystemExit, match=r"^Query: <502 Bad Gateway> Unexpected response: upstream unavailable$"):
        check_api_response(response, "Query")


def test_check_api_response_returns_allowed_errors():
    error = Error(code=404, message="not found")

    result = check_api_response_allow_errors(
        _response(HTTPStatus.NOT_FOUND, error), "Query", allowed_errors=[HTTPStatus.NOT_FOUND]
    )

    assert result is error


def test_check_api_response_converts_allowed_undocumented_status():
    response = _response(HTTPStatus.UNAUTHORIZED, None, b"bad key")

    result = check_api_response_allow_errors(response, "Query", allowed_errors=[401])

    assert result == Error(code=401, message="bad key")


def test_check_api_response_uses_json_message_of_allowed_undocumented_status():
    response = _response(HTTPStatus.UNAUTHORIZED, None, b'{"code": 401, "message": "bad key"}')

    result = check_api_response_allow_errors(response, "Query", allowed_errors=[401])

    assert result == Error(code=401, message="bad key")


def test_check_api_response_truncates_allowed_undocumented_status():
    response = _response(HTTPStatus.BAD_GATEWAY, None, b"x" * 1000)

    result = check_api_response_allow_errors(response, "Query", allowed_errors=[502])

    assert isinstance(result, Error)
    assert result.message == "x" * 200 + "..."


def test_check_api_response_exits_on_unlisted_status():
    response = _response(HTTPStatus.FORBIDDEN, Error(code=403, message="denied"))

    with pytest.raises(SystemExit):
        check_api_response_allow_errors(response, "Query", allowed_errors=[HTTPStatus.NOT_FOUND])


def test_format_api_error_uses_json_message_of_undocumented_status():
    message = format_api_error(_response(HTTPStatus.UNAUTHORIZED, None, b'{"code": 401, "message": "bad key"}'))

    assert message == "<401 Unauthorized> bad key"


def test_format_api_error_truncates_long_bodies():
    message = format_api_error(_response(HTTPStatus.BAD_GATEWAY, None, b"x" * 1000))

    assert message.endswith("x" * 200 + "...")


def test_format_api_error_handles_empty_bodies():
    message = format_api_error(_response(HTTPStatus.SERVICE_UNAVAILABLE, None))

    assert message == "<503 Service Unavailable> Unexpected response: (empty body)"
