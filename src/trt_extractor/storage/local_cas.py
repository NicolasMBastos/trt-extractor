"""Storage content-addressed em disco local.

Implementa o Protocol `Storage` de `core.contracts`. Cobre as fases 0-4; `S3Storage`
entra na fase 5, atrás da mesma interface (ver arquitetura §2, D5).

Duas propriedades que o resto do pipeline depende:

1. **Dedup de graça.** O mesmo documento aparece em 1º e 2º grau; endereçado por
   sha256, vira uma cópia física e N referências lógicas. Sem código de dedup.
2. **Sobrevive a kill -9.** A escrita é `tmp` + `os.replace` no mesmo diretório,
   atômico no mesmo volume. A fase 3 exige matar o processo no meio e retomar sem
   corromper — um arquivo meio-escrito com nome de hash válido seria corrupção
   silenciosa, o pior modo de falha aqui.

A interface do Protocol é assíncrona (o pipeline é async/httpx). O I/O de disco roda
em thread para não bloquear o loop.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from pathlib import Path

from ..core.contracts import Artefato

# Dois níveis de 2 hex = 65.536 diretórios folha. Sem isso, 100k arquivos num
# diretório só degrada listagem e backup em qualquer filesystem.
NIVEIS_FANOUT = 2
LARGURA_NIVEL = 2


def sha256_de(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


class ShaDivergenteError(ValueError):
    """O conteúdo não bate com o endereço. Storage corrompido ou artefato mal-formado."""


class LocalCASStorage:
    """Storage content-addressed sob `raiz`."""

    def __init__(self, raiz: Path | str) -> None:
        self.raiz = Path(raiz)

    # -- endereçamento ------------------------------------------------------

    def caminho(self, sha256: str) -> Path:
        """`ab/cd/abcdef…` — o nome do arquivo é o hash inteiro, para o caminho
        continuar autoexplicativo fora de contexto."""
        sha = sha256.lower()
        if len(sha) != 64 or not all(c in "0123456789abcdef" for c in sha):
            raise ValueError(f"sha256 inválido: {sha256!r}")
        partes = [
            sha[i * LARGURA_NIVEL : (i + 1) * LARGURA_NIVEL] for i in range(NIVEIS_FANOUT)
        ]
        return self.raiz.joinpath(*partes, sha)

    def uri(self, sha256: str) -> str:
        return self.caminho(sha256).resolve().as_uri()

    # -- miolo síncrono (o Protocol é async; estes fazem o trabalho) --------

    def _put_sync(self, artefato: Artefato) -> str:
        sha = sha256_de(artefato.conteudo)
        if artefato.sha256 and artefato.sha256.lower() != sha:
            raise ShaDivergenteError(
                f"Artefato.sha256={artefato.sha256!r} não corresponde ao conteúdo ({sha})"
            )

        destino = self.caminho(sha)
        if destino.exists():
            return sha  # idempotente: mesmo conteúdo, mesmo endereço, no-op

        destino.parent.mkdir(parents=True, exist_ok=True)

        # tmp no MESMO diretório: os.replace só é atômico dentro do volume.
        fd, tmp_nome = tempfile.mkstemp(dir=destino.parent, suffix=".tmp")
        tmp = Path(tmp_nome)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(artefato.conteudo)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, destino)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return sha

    def _get_sync(self, sha256: str) -> bytes:
        caminho = self.caminho(sha256)
        if not caminho.is_file():
            raise FileNotFoundError(f"blob ausente: {sha256}")
        conteudo = caminho.read_bytes()
        real = sha256_de(conteudo)
        if real != sha256.lower():
            raise ShaDivergenteError(
                f"blob corrompido: endereço {sha256}, conteúdo {real}"
            )
        return conteudo

    # -- Protocol Storage ---------------------------------------------------

    async def put(self, artefato: Artefato) -> str:
        return await asyncio.to_thread(self._put_sync, artefato)

    async def get(self, sha256: str) -> bytes:
        return await asyncio.to_thread(self._get_sync, sha256)

    async def exists(self, sha256: str) -> bool:
        return await asyncio.to_thread(lambda: self.caminho(sha256).is_file())
