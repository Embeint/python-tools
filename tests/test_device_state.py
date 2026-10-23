import json

import pytest

from infuse_iot.services.pagination import PaginationError, SnapshotPages
from infuse_iot.socket_comms import GatewayControlError


def test_pages_hold_an_immutable_view_and_check_filters():
    pages = SnapshotPages(0)
    original = [{"id": "first"}, {"id": "second"}]
    first = pages.page(lambda: (original, {}), {"filter": 1}, limit=1)
    original[1]["id"] = "changed"
    second = pages.page(None, {"filter": 1}, cursor=first["next_cursor"])
    assert second["items"] == [{"id": "second"}]
    # Returned rows are copies of the snapshot
    second["items"][0]["id"] = "mutated"
    assert pages.page(None, {"filter": 1}, cursor=first["next_cursor"])["items"] == [{"id": "second"}]
    with pytest.raises(PaginationError) as error:
        pages.page(None, {"filter": 2}, cursor=first["next_cursor"])
    assert error.value.code == "invalid_cursor"


@pytest.mark.parametrize(
    "cursor, code",
    [("deadbeef:1", "snapshot_expired"), ("nonsense", "invalid_cursor"), (5, "invalid_cursor")],
)
def test_page_errors_have_codes(cursor, code):
    pages = SnapshotPages(0)
    with pytest.raises(PaginationError) as error:
        pages.page(None, {}, cursor=cursor)
    assert (error.value.code, str(error.value)) == (code, code)
    assert error.value.message
    # Gateway control replies with the code
    assert isinstance(error.value, GatewayControlError)


def test_page_beyond_snapshot_is_invalid():
    pages = SnapshotPages(0)
    first = pages.page(lambda: ([{"id": 1}, {"id": 2}], {}), {}, limit=1)
    key = first["next_cursor"].split(":")[0]
    with pytest.raises(PaginationError, match="invalid_cursor"):
        pages.page(None, {}, cursor=f"{key}:3")


def test_oversized_row_reports_budget_error():
    pages = SnapshotPages(0)
    with pytest.raises(PaginationError) as error:
        pages.page(lambda: ([{"data": "x" * 1000}], {}), {}, max_bytes=500)
    assert error.value.code == "item_exceeds_response_budget"


def test_oversized_later_row_fails_before_a_cursor_is_issued():
    pages = SnapshotPages(0)
    rows: list[dict] = [{"id": 1}, {"data": "x" * 1000}]
    # The first page alone would fit, but its cursor could never advance past the second row
    with pytest.raises(PaginationError) as error:
        pages.page(lambda: (rows, {}), {}, limit=1, max_bytes=500)
    assert error.value.code == "item_exceeds_response_budget"


def test_cursor_is_bound_to_its_byte_budget():
    pages = SnapshotPages(0)
    first = pages.page(lambda: ([{"id": 1}, {"id": 2}], {}), {}, limit=1, max_bytes=500)
    with pytest.raises(PaginationError) as error:
        pages.page(None, {}, cursor=first["next_cursor"], max_bytes=400)
    assert error.value.code == "invalid_cursor"
    assert pages.page(None, {}, cursor=first["next_cursor"], max_bytes=500)["items"] == [{"id": 2}]


def test_pages_fit_the_byte_budget_exactly():
    pages = SnapshotPages(0)
    rows = [{"id": index, "padding": "x" * (index % 37)} for index in range(200)]
    cursor, received = None, []
    while True:
        result = pages.page(lambda: (rows, {"extra": "metadata"}), {}, cursor, limit=200, max_bytes=1000)
        assert len(json.dumps(result).encode()) <= 1000
        assert result["extra"] == "metadata"
        received.extend(result["items"])
        cursor = result["next_cursor"]
        if cursor is None:
            break
    assert received == rows
