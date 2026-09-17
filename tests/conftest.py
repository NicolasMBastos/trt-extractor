"""Only loopback connections are allowed in the offline suite."""

import pytest


@pytest.fixture
def vcr_config() -> dict[str, object]:
    # Windows asyncio implements socketpair through loopback TCP.
    return {"allowed_hosts": [r"^127\.0\.0\.1$", r"^::1$"]}
