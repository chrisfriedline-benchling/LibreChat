from datetime import datetime

from benchling_mcp_server.utils import _datetime_handler


def test_datetime_handler() -> None:
    # Test with datetime object
    dt = datetime(2024, 1, 1, 12, 0, 0)
    assert _datetime_handler(dt) == "2024-01-01T12:00:00"

    # Test with string
    assert _datetime_handler("test") == "test"
