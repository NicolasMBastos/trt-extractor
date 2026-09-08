"""In-memory session lifecycle with single-flight renewal.

This module never authenticates with a certificate. Its renewer receives the
credential reference and returns a Session issued by an authorized, external
handshake flow. Durable encrypted storage deliberately remains a separate task.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .contracts import Credencial, PermanenteError, SessaoExpiradaError, Session

Clock = Callable[[], datetime]
Renewer = Callable[[str, Credencial], Awaitable[Session]]


@dataclass(frozen=True, slots=True)
class SessionKey:
    tribunal: str
    credencial_id: str


class SessaoPausadaError(SessaoExpiradaError):
    """Silent renewal failed; only a new authorized session may resume the key."""


class RenovacaoSubstituidaError(SessaoExpiradaError):
    """An explicit invalidate or put superseded this renewal without pausing it."""


class SessionPool:
    """Caches sessions by `(tribunal, credencial)` without sharing identities.

    `get` renews once for concurrent consumers. A cancelled consumer does not
    cancel that renewal, because other consumers may still need its result.
    `invalidate` increments a generation so a stale renewal cannot overwrite a
    session supplied after an explicit invalidation or manual reauthentication.
    """

    def __init__(
        self,
        renew: Renewer,
        *,
        renew_before: timedelta = timedelta(minutes=10),
        clock: Clock = lambda: datetime.now(UTC),
    ) -> None:
        if renew_before < timedelta():
            raise ValueError("renew_before nao pode ser negativo")
        self._renew = renew
        self._renew_before = renew_before
        self._clock = clock
        self._sessions: dict[SessionKey, Session] = {}
        self._generations: dict[SessionKey, int] = {}
        self._paused: dict[SessionKey, str] = {}
        self._inflight: dict[SessionKey, asyncio.Task[Session]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _key(tribunal: str, credencial: Credencial) -> SessionKey:
        return SessionKey(tribunal, credencial.id)

    def _usable(self, session: Session) -> bool:
        now = self._clock()
        return (
            session.expira_em is not None
            and session.expira_em.utcoffset() is not None
            and now.utcoffset() is not None
            and session.expira_em > now + self._renew_before
        )

    @staticmethod
    def _validate(key: SessionKey, credencial: Credencial, session: Session) -> None:
        if session.tribunal != key.tribunal or session.credencial != credencial:
            raise PermanenteError("Renovador retornou sessao para outra identidade")
        if session.expira_em is None or session.expira_em.utcoffset() is None:
            raise SessaoExpiradaError("Renovador retornou sessao sem validade")

    async def put(self, session: Session) -> None:
        """Install a newly captured session and clear a prior renewal pause."""
        key = self._key(session.tribunal, session.credencial)
        self._validate(key, session.credencial, session)
        async with self._lock:
            self._generations[key] = self._generations.get(key, 0) + 1
            self._sessions[key] = session
            self._paused.pop(key, None)

    async def invalidate(self, tribunal: str, credencial: Credencial) -> None:
        """Reject cached material. A currently running renewal becomes stale."""
        key = self._key(tribunal, credencial)
        async with self._lock:
            self._generations[key] = self._generations.get(key, 0) + 1
            self._sessions.pop(key, None)

    async def pause(self, tribunal: str, credencial: Credencial, reason: str) -> None:
        """Pause after failed silent renewal; never retain the underlying error text."""
        key = self._key(tribunal, credencial)
        async with self._lock:
            self._generations[key] = self._generations.get(key, 0) + 1
            self._sessions.pop(key, None)
            self._paused[key] = "renovacao silenciosa indisponivel"

    async def get(self, tribunal: str, credencial: Credencial) -> Session:
        key = self._key(tribunal, credencial)
        async with self._lock:
            if key in self._paused:
                raise SessaoPausadaError(self._paused[key])
            cached = self._sessions.get(key)
            if cached is not None and self._usable(cached):
                return cached
            task = self._inflight.get(key)
            if task is None:
                generation = self._generations.get(key, 0)
                task = asyncio.create_task(self._refresh(key, credencial, generation))
                self._inflight[key] = task
        # Shield preserves the shared operation if an individual worker is cancelled.
        return await asyncio.shield(task)

    async def _refresh(
        self, key: SessionKey, credencial: Credencial, generation: int
    ) -> Session:
        try:
            session = await self._renew(key.tribunal, credencial)
            self._validate(key, credencial, session)
            if not self._usable(session):
                raise SessaoExpiradaError("Renovador retornou sessao perto de expirar")
            async with self._lock:
                if self._generations.get(key, 0) != generation:
                    raise RenovacaoSubstituidaError("Renovacao ficou obsoleta")
                self._sessions[key] = session
            return session
        except asyncio.CancelledError:
            raise
        except RenovacaoSubstituidaError:
            raise
        except SessaoExpiradaError:
            await self.pause(key.tribunal, credencial, "renovacao silenciosa falhou")
            raise SessaoPausadaError("renovacao silenciosa indisponivel") from None
        except Exception:
            await self.pause(key.tribunal, credencial, "renovacao silenciosa falhou")
            raise SessaoPausadaError("renovacao silenciosa indisponivel") from None
        finally:
            async with self._lock:
                if self._inflight.get(key) is asyncio.current_task():
                    self._inflight.pop(key, None)
