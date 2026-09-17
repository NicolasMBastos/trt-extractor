"""Verify that the installed test guard rejects outbound connections."""

import socket

import pytest


def test_outbound_connection_is_blocked() -> None:
    # Check the guard before attempting even a reserved TEST-NET address.
    assert socket.socket.connect.__module__ == "pytest_recording.network"
    with (
        socket.socket() as connection,
        pytest.raises(RuntimeError, match="Network is disabled"),
    ):
        connection.connect(("192.0.2.1", 443))


async def test_async_loop_works_with_outbound_guard() -> None:
    test_outbound_connection_is_blocked()
