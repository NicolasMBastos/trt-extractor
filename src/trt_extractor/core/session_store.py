"""Persistência do `storage_state` da sessão autenticada. Fase 1, ADR 006.

O handshake por certificado é ato do titular e é raro (MFA é por dispositivo). Sem
persistir a sessão, todo reinício de worker exige um humano — o que contraria a
estratégia de "autentica quando precisa e mantém a sessão". Persistir, por outro
lado, põe material de sessão em repouso no disco. Este módulo é o meio-termo
aprovado.

**Decisão de segredo (2026-09-08, tomada pelo dono do projeto):** DPAPI do Windows,
escopo de usuário. Motivos:

- **Não há chave para gerenciar.** A chave é derivada do perfil da conta Windows pelo
  próprio SO. Chave que não existe não vaza e não expira mal.
- **O arquivo só abre pela conta do titular, naquela máquina.** Copiá-lo para outro
  lugar não serve de nada. Isso espelha a ADR 007: o acesso continua sendo ato do
  titular, agora imposto pelo SO e não por convenção.
- **Zero dependência nova.** `crypt32.dll` por `ctypes`.

A amarração à credencial é **criptográfica, não uma checagem**: `(tribunal,
credencial_id)` entra como entropia secundária do DPAPI. Um estado salvo para a
credencial A **não descriptografa** como B — não há caminho de código para confundir
identidade, porque o SO recusa antes.

O que este módulo nunca faz: registrar o estado, ecoá-lo em exceção, ou tocar em
chave privada de certificado (que jamais sai do repositório do SO — ADR 003/007).
"""

from __future__ import annotations

import asyncio
import ctypes
import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

# Nunca solicitar UI: um prompt do DPAPI num worker sem console pendura o processo.
CRYPTPROTECT_UI_FORBIDDEN = 0x01


class SessionStoreError(Exception):
    """Falha ao guardar ou recuperar material de sessão. Mensagem sem conteúdo."""


class Cifra(Protocol):
    """Proteção do estado em repouso. Injetável para que o teste rode sem DPAPI —
    o CI é Linux (`ubuntu-latest`) e não tem `crypt32`."""

    def proteger(self, claro: bytes, entropia: bytes) -> bytes: ...

    def desproteger(self, cifrado: bytes, entropia: bytes) -> bytes: ...


if sys.platform == "win32":
    # `ctypes.wintypes` levanta na importação fora do Windows, e o CI é ubuntu.
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]


class DpapiCifra:
    """DPAPI com escopo de usuário. Só existe no Windows, por desenho."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise SessionStoreError(
                "DPAPI existe só no Windows; injete outra Cifra nesta plataforma"
            )

    @staticmethod
    def _chama(nome: str, entrada: bytes, entropia: bytes) -> bytes:
        fn = getattr(ctypes.windll.crypt32, nome)
        # Os buffers ficam em variáveis locais de propósito: um `_Blob` guarda só um
        # ponteiro, e se o buffer for coletado antes da chamada o ponteiro fica solto.
        buf_entrada = ctypes.create_string_buffer(entrada, len(entrada))
        buf_entropia = ctypes.create_string_buffer(entropia, len(entropia))
        ponteiro = ctypes.POINTER(ctypes.c_char)
        dentro = _Blob(len(entrada), ctypes.cast(buf_entrada, ponteiro))
        extra = _Blob(len(entropia), ctypes.cast(buf_entropia, ponteiro))
        fora = _Blob()
        ok = fn(
            ctypes.byref(dentro),
            None,
            ctypes.byref(extra),
            None,
            None,
            CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(fora),
        )
        if not ok:
            # Só o código do SO. A mensagem do Windows pode citar o descritor, e o
            # descritor não é lugar de identificar credencial em log.
            raise SessionStoreError(f"{nome} falhou (erro {ctypes.GetLastError()})")
        try:
            return ctypes.string_at(fora.pbData, fora.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(fora.pbData)

    def proteger(self, claro: bytes, entropia: bytes) -> bytes:
        return self._chama("CryptProtectData", claro, entropia)

    def desproteger(self, cifrado: bytes, entropia: bytes) -> bytes:
        return self._chama("CryptUnprotectData", cifrado, entropia)


def raiz_padrao() -> Path:
    """Fora do repositório, por padrão. O guarda do CI barra `storage_state` no
    índice do git justamente porque um estado versionado é vazamento de sessão."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_STATE_HOME")
    if not base:
        base = str(Path.home() / ".local" / "state")
    return Path(base) / "trt-extractor" / "sessions"


class SessionStore:
    """Guarda um `storage_state` por `(tribunal, credencial_id)`.

    O nome do arquivo é o sha256 da chave lógica: o diretório não revela CPF, id de
    credencial nem em quais tribunais o escritório atua.
    """

    def __init__(self, raiz: Path | None = None, *, cifra: Cifra | None = None) -> None:
        self._raiz = Path(raiz) if raiz is not None else raiz_padrao()
        self._recusa_repositorio(self._raiz)
        self._cifra = cifra if cifra is not None else DpapiCifra()

    @staticmethod
    def _recusa_repositorio(raiz: Path) -> None:
        """Estado de sessão dentro de árvore git é um `git add -A` de distância de
        virar segredo publicado. Barrado aqui, não só no CI."""
        for pasta in [raiz, *raiz.parents]:
            if (pasta / ".git").exists():
                raise SessionStoreError(
                    "raiz de sessão não pode ficar dentro de um repositório git"
                )

    # -- chave e caminho ----------------------------------------------------

    @staticmethod
    def _entropia(tribunal: str, credencial_id: str) -> bytes:
        if not tribunal or not credencial_id:
            raise SessionStoreError("tribunal e credencial_id são obrigatórios")
        # `\x00` como separador: nenhum dos dois pode contê-lo, então não há par
        # distinto que produza a mesma entropia.
        return f"trt-extractor\x00{tribunal}\x00{credencial_id}".encode()

    def caminho(self, tribunal: str, credencial_id: str) -> Path:
        digest = hashlib.sha256(self._entropia(tribunal, credencial_id)).hexdigest()
        return self._raiz / f"{digest}.state"

    # -- síncrono -----------------------------------------------------------

    def _salvar_sync(
        self, tribunal: str, credencial_id: str, estado: Mapping[str, Any]
    ) -> None:
        if not isinstance(estado, Mapping):
            raise SessionStoreError("storage_state deve ser um mapeamento")
        try:
            claro = json.dumps(dict(estado), separators=(",", ":")).encode()
        except (TypeError, ValueError):
            # Sem `from`: o traceback do json imprime o objeto, e o objeto é o segredo.
            raise SessionStoreError("storage_state não é serializável em JSON") from None

        cifrado = self._cifra.proteger(claro, self._entropia(tribunal, credencial_id))
        destino = self.caminho(tribunal, credencial_id)
        # 0o700: no Windows quem protege é o DPAPI, mas o modo restritivo é correto
        # e é o que vale se algum dia isto rodar em POSIX.
        destino.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        # ponytail: mesmo padrão de escrita atômica de storage/local_cas.py.
        # Duplicado em vez de extraído: são duas ocorrências, e refatorar código
        # já provado na fase 2 por um chamador novo custa mais do que 8 linhas.
        # tmp no MESMO diretório: os.replace só é atômico dentro do volume.
        # mkstemp cria com 0o600 — o arquivo nunca existe legível por outros.
        fd, tmp_nome = tempfile.mkstemp(dir=destino.parent, suffix=".tmp")
        tmp = Path(tmp_nome)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(cifrado)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, destino)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    def _carregar_sync(self, tribunal: str, credencial_id: str) -> dict[str, Any] | None:
        """`None` para ausente **e** para ilegível.

        Ilegível é o caso normal, não excepcional: DPAPI de outro usuário, outra
        máquina, arquivo truncado, ou estado de outra credencial. Em todos, a resposta
        certa é a mesma — não há sessão utilizável, refaça o handshake. O arquivo é
        deixado no lugar de propósito: apagar destruiria evidência de um problema, e o
        próximo `salvar` sobrescreve de forma atômica.
        """
        caminho = self.caminho(tribunal, credencial_id)
        if not caminho.is_file():
            return None
        try:
            claro = self._cifra.desproteger(
                caminho.read_bytes(), self._entropia(tribunal, credencial_id)
            )
            estado = json.loads(claro)
        except (SessionStoreError, OSError, ValueError):
            return None
        return estado if isinstance(estado, dict) else None

    def _descartar_sync(self, tribunal: str, credencial_id: str) -> None:
        self.caminho(tribunal, credencial_id).unlink(missing_ok=True)

    # -- assíncrono ---------------------------------------------------------
    # I/O de disco em thread, igual ao LocalCASStorage: o pipeline é async.

    async def salvar(
        self, tribunal: str, credencial_id: str, estado: Mapping[str, Any]
    ) -> None:
        await asyncio.to_thread(self._salvar_sync, tribunal, credencial_id, estado)

    async def carregar(self, tribunal: str, credencial_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._carregar_sync, tribunal, credencial_id)

    async def descartar(self, tribunal: str, credencial_id: str) -> None:
        """Chamar quando a sessão for invalidada. Sessão morta em disco é só risco."""
        await asyncio.to_thread(self._descartar_sync, tribunal, credencial_id)

    def __repr__(self) -> str:  # nunca revelar caminho de estado nem cifra
        return f"SessionStore(raiz={self._raiz.name!r})"
