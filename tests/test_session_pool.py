"""Deterministic offline tests for session pooling; no handshake or browser."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest

from trt_extractor.core.contracts import Credencial, Session
from trt_extractor.core.session_pool import (
    RenovacaoSubstituidaError,
    SessaoPausadaError,
    SessionPool,
)

NOW = datetime(2026, 9, 8, 12, tzinfo=UTC)


def credential(name: str = "a") -> Credencial:
    return Credencial(f"cred-{name}", "")


def session(
    tribunal: str = "TRT4", cred: Credencial | None = None, expires_in: int = 60
) -> Session:
    return Session(
        cred or credential(),
        tribunal,
        "synthetic",
        expira_em=NOW + timedelta(minutes=expires_in),
    )


def pool(renew: Callable[[str, Credencial], Awaitable[Session]]) -> SessionPool:
    return SessionPool(renew, clock=lambda: NOW)


async def test_fifty_consumers_share_one_renewal() -> None:
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def renew(tribunal: str, cred: Credencial) -> Session:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return session(tribunal, cred)

    subject = pool(renew)
    workers = [asyncio.create_task(subject.get("TRT4", credential())) for _ in range(50)]
    await started.wait()
    assert calls == 1
    release.set()
    sessions = await asyncio.gather(*workers)
    assert calls == 1
    assert len({id(value) for value in sessions}) == 1


async def test_distinct_credentials_do_not_share_session_or_renewal() -> None:
    calls: list[tuple[str, str]] = []

    async def renew(tribunal: str, cred: Credencial) -> Session:
        calls.append((tribunal, cred.id))
        return session(tribunal, cred)

    subject = pool(renew)
    a, b = await asyncio.gather(
        subject.get("TRT4", credential("a")), subject.get("TRT4", credential("b"))
    )
    assert a.credencial != b.credencial
    assert calls == [("TRT4", "cred-a"), ("TRT4", "cred-b")]


async def test_expiring_session_renews_before_use() -> None:
    old = session(expires_in=10)
    replacement = session(expires_in=60)

    async def renew(_tribunal: str, _cred: Credencial) -> Session:
        return replacement

    subject = pool(renew)
    await subject.put(old)
    assert await subject.get("TRT4", credential()) == replacement


async def test_failed_renewal_pauses_all_consumers_until_manual_put() -> None:
    async def renew(_tribunal: str, _cred: Credencial) -> Session:
        raise RuntimeError("token must not reach state")

    subject = pool(renew)
    with pytest.raises(SessaoPausadaError) as error:
        await subject.get("TRT4", credential())
    assert "token" not in str(error.value)
    with pytest.raises(SessaoPausadaError):
        await subject.get("TRT4", credential())
    fresh = session(expires_in=60)
    await subject.put(fresh)
    assert await subject.get("TRT4", credential()) == fresh


async def test_cancelled_waiter_does_not_cancel_shared_renewal() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def renew(tribunal: str, cred: Credencial) -> Session:
        started.set()
        await release.wait()
        return session(tribunal, cred)

    subject = pool(renew)
    cancelled = asyncio.create_task(subject.get("TRT4", credential()))
    await started.wait()
    survivor = asyncio.create_task(subject.get("TRT4", credential()))
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    release.set()
    assert (await survivor).credencial == credential()


async def test_invalidation_prevents_stale_renewal_from_overwriting_manual_session() -> (
    None
):
    started = asyncio.Event()
    release = asyncio.Event()

    async def renew(tribunal: str, cred: Credencial) -> Session:
        started.set()
        await release.wait()
        return session(tribunal, cred, expires_in=90)

    subject = pool(renew)
    stale = asyncio.create_task(subject.get("TRT4", credential()))
    await started.wait()
    await subject.invalidate("TRT4", credential())
    fresh = session(expires_in=60)
    await subject.put(fresh)
    release.set()
    with pytest.raises(RenovacaoSubstituidaError):
        await stale
    assert await subject.get("TRT4", credential()) == fresh


async def test_wrong_identity_from_renewer_pauses_key() -> None:
    async def renew(_tribunal: str, _cred: Credencial) -> Session:
        return session("TRT2", credential("other"))

    with pytest.raises(SessaoPausadaError):
        await pool(renew).get("TRT4", credential())


def test_rejects_negative_renewal_margin() -> None:
    async def renew(tribunal: str, cred: Credencial) -> Session:
        return session(tribunal, cred)

    with pytest.raises(ValueError):
        SessionPool(renew, renew_before=timedelta(seconds=-1))
