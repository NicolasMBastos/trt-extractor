"""Testes do SessionStore. Sem rede e sem browser.

A cifra é injetada, porque o CI é `ubuntu-latest` e DPAPI só existe no Windows. Há
um teste do DPAPI de verdade, que se exclui fora do Windows — ele é o único que
prova a decisão de segredo; os outros provam o envelope em volta dela.

O foco: o estado não vaza no nome do arquivo, não vaza em exceção, não atravessa
credencial, não fica meio-escrito, e ilegível é resposta normal e não explosão.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trt_extractor.core.session_store import (
    DpapiCifra,
    SessionStore,
    SessionStoreError,
    raiz_padrao,
)

TRIBUNAL = "TRT4"
CRED = "cred-do-titular"
# Parecido com um storage_state do Playwright, incluindo o que é segredo.
ESTADO = {
    "cookies": [
        {"name": "access_token", "value": "jwt-secretissimo", "domain": "pdpj.jus.br"}
    ],
    "origins": [{"origin": "https://portaldeservicos.pdpj.jus.br", "localStorage": []}],
}


class CifraFake:
    """Marca a entropia no início do texto cifrado e a exige na volta.

    Não é criptografia — é o mínimo para que "entropia errada não abre" seja um
    comportamento testável sem DPAPI.
    """

    def proteger(self, claro: bytes, entropia: bytes) -> bytes:
        return hashlib.sha256(entropia).digest() + claro

    def desproteger(self, cifrado: bytes, entropia: bytes) -> bytes:
        marca = hashlib.sha256(entropia).digest()
        if not cifrado.startswith(marca):
            raise SessionStoreError("entropia divergente")
        return cifrado[len(marca) :]


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "sessions", cifra=CifraFake())


# -- ida e volta ------------------------------------------------------------


async def test_salva_e_recupera_o_estado_intacto(store: SessionStore) -> None:
    await store.salvar(TRIBUNAL, CRED, ESTADO)
    assert await store.carregar(TRIBUNAL, CRED) == ESTADO


async def test_estado_ausente_devolve_none(store: SessionStore) -> None:
    assert await store.carregar(TRIBUNAL, CRED) is None


async def test_sobrescrever_substitui_e_nao_mistura(store: SessionStore) -> None:
    await store.salvar(TRIBUNAL, CRED, ESTADO)
    novo = {"cookies": [{"name": "access_token", "value": "jwt-renovado"}]}
    await store.salvar(TRIBUNAL, CRED, novo)
    assert await store.carregar(TRIBUNAL, CRED) == novo


async def test_descartar_remove_e_e_idempotente(store: SessionStore) -> None:
    await store.salvar(TRIBUNAL, CRED, ESTADO)
    await store.descartar(TRIBUNAL, CRED)
    assert await store.carregar(TRIBUNAL, CRED) is None
    await store.descartar(TRIBUNAL, CRED)  # não levanta


# -- amarração à identidade -------------------------------------------------


async def test_estado_de_uma_credencial_nao_abre_como_outra(store: SessionStore) -> None:
    """A amarração é criptográfica, não uma checagem: a entropia do DPAPI é
    `(tribunal, credencial_id)`."""
    await store.salvar(TRIBUNAL, "cred-a", ESTADO)
    assert await store.carregar(TRIBUNAL, "cred-b") is None


async def test_estado_de_um_tribunal_nao_abre_como_outro(store: SessionStore) -> None:
    await store.salvar("TRT4", CRED, ESTADO)
    assert await store.carregar("TRT2", CRED) is None


async def test_arquivo_de_credencial_diferente_e_arquivo_diferente(
    store: SessionStore,
) -> None:
    assert store.caminho(TRIBUNAL, "cred-a") != store.caminho(TRIBUNAL, "cred-b")


@pytest.mark.parametrize(("tribunal", "cred"), [("", CRED), (TRIBUNAL, ""), ("", "")])
async def test_chave_logica_incompleta_e_rejeitada(
    store: SessionStore, tribunal: str, cred: str
) -> None:
    with pytest.raises(SessionStoreError):
        await store.salvar(tribunal, cred, ESTADO)


# -- o disco não conta a história -------------------------------------------


def test_nome_do_arquivo_nao_revela_tribunal_nem_credencial(store: SessionStore) -> None:
    """O diretório não deve dizer em quais tribunais o escritório atua, nem de quem
    é a credencial."""
    nome = store.caminho(TRIBUNAL, CRED).name
    assert TRIBUNAL.lower() not in nome.lower()
    assert CRED not in nome
    assert nome.endswith(".state")


async def test_a_cifra_fake_nao_protege_nada_por_isso_quem_prova_e_o_dpapi(
    store: SessionStore,
) -> None:
    """Deixa explícito o limite deste arquivo: com `CifraFake` o estado fica legível
    no disco. Quem prova proteção em repouso é `test_dpapi_real_...`, no fim."""
    await store.salvar(TRIBUNAL, CRED, ESTADO)
    assert b"jwt-secretissimo" in store.caminho(TRIBUNAL, CRED).read_bytes()


def test_repr_nao_revela_o_caminho_do_estado(store: SessionStore) -> None:
    assert "sessions" in repr(store)
    assert str(store.caminho(TRIBUNAL, CRED)) not in repr(store)


def test_raiz_dentro_de_repositorio_git_e_recusada(tmp_path: Path) -> None:
    """Estado de sessão em árvore git é um `git add -A` de virar segredo publicado."""
    (tmp_path / ".git").mkdir()
    with pytest.raises(SessionStoreError):
        SessionStore(tmp_path / "runtime" / "sessions", cifra=CifraFake())


def test_raiz_padrao_fica_fora_do_repositorio() -> None:
    assert "trt-extractor" in raiz_padrao().parts
    assert not (raiz_padrao() / ".git").exists()


# -- falha e corrupção ------------------------------------------------------


async def test_arquivo_corrompido_devolve_none_e_nao_e_apagado(
    store: SessionStore,
) -> None:
    """Ilegível é caso normal (outro usuário, outra máquina, truncado), não exceção.
    O arquivo fica: apagar destruiria evidência, e o próximo salvar sobrescreve."""
    await store.salvar(TRIBUNAL, CRED, ESTADO)
    caminho = store.caminho(TRIBUNAL, CRED)
    caminho.write_bytes(b"lixo que nao abre")
    assert await store.carregar(TRIBUNAL, CRED) is None
    assert caminho.is_file()
    await store.salvar(TRIBUNAL, CRED, ESTADO)
    assert await store.carregar(TRIBUNAL, CRED) == ESTADO


async def test_conteudo_que_abre_mas_nao_e_json_devolve_none(
    store: SessionStore,
) -> None:
    caminho = store.caminho(TRIBUNAL, CRED)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    entropia = SessionStore._entropia(TRIBUNAL, CRED)
    caminho.write_bytes(CifraFake().proteger(b"nao e json", entropia))
    assert await store.carregar(TRIBUNAL, CRED) is None


async def test_json_que_nao_e_objeto_devolve_none(store: SessionStore) -> None:
    caminho = store.caminho(TRIBUNAL, CRED)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    entropia = SessionStore._entropia(TRIBUNAL, CRED)
    caminho.write_bytes(CifraFake().proteger(b"[1, 2, 3]", entropia))
    assert await store.carregar(TRIBUNAL, CRED) is None


async def test_estado_nao_serializavel_falha_sem_ecoar_o_objeto(
    store: SessionStore,
) -> None:
    class Segredo:
        def __repr__(self) -> str:
            return "TOKEN-QUE-NAO-PODE-APARECER"

    with pytest.raises(SessionStoreError) as exc:
        await store.salvar(TRIBUNAL, CRED, {"cookies": Segredo()})
    assert "TOKEN-QUE-NAO-PODE-APARECER" not in str(exc.value)
    assert exc.value.__cause__ is None, "o traceback do json imprime o objeto"


async def test_nao_deixa_temporario_para_tras(store: SessionStore) -> None:
    await store.salvar(TRIBUNAL, CRED, ESTADO)
    raiz = store.caminho(TRIBUNAL, CRED).parent
    assert list(raiz.glob("*.tmp")) == []


async def test_falha_da_cifra_nao_deixa_arquivo_nem_temporario(tmp_path: Path) -> None:
    """Escrita atômica: ou o estado antigo continua íntegro, ou o novo está inteiro.
    Nunca um arquivo meio-escrito com nome válido."""

    class CifraQueFalha(CifraFake):
        def proteger(self, claro: bytes, entropia: bytes) -> bytes:
            raise SessionStoreError("cofre indisponível")

    store = SessionStore(tmp_path / "sessions", cifra=CifraQueFalha())
    with pytest.raises(SessionStoreError):
        await store.salvar(TRIBUNAL, CRED, ESTADO)
    assert not store.caminho(TRIBUNAL, CRED).exists()


# -- a decisão de segredo, de verdade ---------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI só existe no Windows")
async def test_dpapi_real_ida_e_volta_e_recusa_entropia_errada(tmp_path: Path) -> None:
    """O único teste que exercita a decisão de segredo aprovada (DPAPI, escopo de
    usuário). Roda na máquina do titular; excluído do CI, que é Linux."""
    store = SessionStore(tmp_path / "sessions", cifra=DpapiCifra())
    await store.salvar(TRIBUNAL, CRED, ESTADO)

    bruto = store.caminho(TRIBUNAL, CRED).read_bytes()
    assert b"jwt-secretissimo" not in bruto, "estado em claro no disco"

    assert await store.carregar(TRIBUNAL, CRED) == ESTADO
    assert await store.carregar(TRIBUNAL, "outra-cred") is None
    assert await store.carregar("TRT2", CRED) is None


@pytest.mark.skipif(sys.platform == "win32", reason="caminho de outra plataforma")
def test_dpapi_recusa_fora_do_windows() -> None:
    with pytest.raises(SessionStoreError):
        DpapiCifra()
