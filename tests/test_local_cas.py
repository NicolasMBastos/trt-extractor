"""Testes do storage content-addressed local. Sem rede, sem banco."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trt_extractor.core.contracts import Artefato, Storage
from trt_extractor.storage.local_cas import (
    LocalCASStorage,
    ShaDivergenteError,
    sha256_de,
)

CONTEUDO = b"%PDF-1.4 peticao inicial falsa para teste"
SHA = hashlib.sha256(CONTEUDO).hexdigest()


def artefato(conteudo: bytes = CONTEUDO, *, sha: str | None = None) -> Artefato:
    return Artefato(
        conteudo=conteudo,
        sha256=sha if sha is not None else sha256_de(conteudo),
        content_type="application/pdf",
    )


@pytest.fixture
def storage(tmp_path: Path) -> LocalCASStorage:
    return LocalCASStorage(tmp_path)


def test_satisfaz_o_protocol(storage: LocalCASStorage) -> None:
    """Se isto quebrar, o contrato e a implementação divergiram."""
    assert isinstance(storage, Storage)


async def test_put_devolve_sha_e_get_recupera(storage: LocalCASStorage) -> None:
    assert await storage.put(artefato()) == SHA
    assert await storage.get(SHA) == CONTEUDO


async def test_exists(storage: LocalCASStorage) -> None:
    assert await storage.exists(SHA) is False
    await storage.put(artefato())
    assert await storage.exists(SHA) is True


async def test_layout_com_fanout(storage: LocalCASStorage) -> None:
    await storage.put(artefato())
    esperado = storage.raiz / SHA[0:2] / SHA[2:4] / SHA
    assert esperado.is_file()


async def test_put_e_idempotente_e_nao_reescreve(storage: LocalCASStorage) -> None:
    """Reprocessar um job não pode duplicar nem tocar o arquivo já gravado."""
    await storage.put(artefato())
    caminho = storage.caminho(SHA)
    mtime = caminho.stat().st_mtime_ns

    assert await storage.put(artefato()) == SHA

    assert caminho.stat().st_mtime_ns == mtime
    folha = caminho.parent
    assert [p.name for p in folha.iterdir()] == [SHA]


async def test_conteudos_diferentes_enderecos_diferentes(
    storage: LocalCASStorage,
) -> None:
    a = await storage.put(artefato(b"documento A"))
    b = await storage.put(artefato(b"documento B"))
    assert a != b
    assert await storage.get(a) == b"documento A"


async def test_dedup_entre_graus(storage: LocalCASStorage) -> None:
    """A mesma peça em 1º e 2º grau: uma cópia física, N referências lógicas."""
    grau1 = await storage.put(artefato())
    grau2 = await storage.put(artefato())
    assert grau1 == grau2
    assert sum(1 for _ in storage.raiz.rglob("*") if _.is_file()) == 1


async def test_put_recusa_sha_divergente(storage: LocalCASStorage) -> None:
    errado = "0" * 64
    with pytest.raises(ShaDivergenteError):
        await storage.put(artefato(sha=errado))


async def test_get_detecta_corrupcao(storage: LocalCASStorage) -> None:
    """Um blob adulterado no disco não pode passar por bom."""
    await storage.put(artefato())
    storage.caminho(SHA).write_bytes(b"conteudo trocado")
    with pytest.raises(ShaDivergenteError):
        await storage.get(SHA)


async def test_get_ausente(storage: LocalCASStorage) -> None:
    with pytest.raises(FileNotFoundError):
        await storage.get(SHA)


def test_sha_invalido_e_rejeitado(storage: LocalCASStorage) -> None:
    for ruim in ("abc", "z" * 64, ""):
        with pytest.raises(ValueError):
            storage.caminho(ruim)


async def test_nao_deixa_tmp_para_tras(storage: LocalCASStorage) -> None:
    await storage.put(artefato())
    assert not list(storage.raiz.rglob("*.tmp"))
