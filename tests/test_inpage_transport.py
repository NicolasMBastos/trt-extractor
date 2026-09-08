"""Testes do InPageFetchTransport. Sem browser e sem rede: página é um duplo.

O foco não é "o fetch funciona" — é o que este transporte promete e que rodar
dentro de uma página não dá de graça: uma identidade só por página, cabeçalho
controlado pelo browser recusado em vez de ignorado, bytes íntegros no
round-trip de base64, e nenhuma mensagem de erro com URL ou token dentro.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trt_extractor.core.contracts import (
    Credencial,
    PermanenteError,
    SessaoExpiradaError,
    Session,
    TransienteError,
    Transport,
)
from trt_extractor.core.inpage_transport import InPageFetchTransport

ORIGEM = "https://portaldeservicos.pdpj.jus.br"
URL = f"{ORIGEM}/api/v2/processos/0020890-39.2024.5.04.0015"
OUTRA_ORIGEM = "https://evil.example.com/api/v2/processos/1"
CRED = "cred-a"


def sessao(
    *,
    id_cred: str = CRED,
    token: str | None = "jwt-secretissimo-a",
    cookies: dict[str, str] | None = None,
) -> Session:
    return Session(
        credencial=Credencial(id=id_cred, cpf="00000000000"),
        tribunal="TRT4",
        token=token,
        cookies=cookies or {},
    )


class PaginaFalsa:
    """Duplo de `Page`: guarda o argumento recebido e devolve o que o teste mandar."""

    def __init__(self, retorno: Any = None, erro: BaseException | None = None) -> None:
        self.args: list[dict[str, Any]] = []
        self._erro = erro
        self._retorno = retorno if retorno is not None else self.resposta(200, b"ok")

    @staticmethod
    def resposta(
        status: int, corpo: bytes, headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "status": status,
            "headers": headers or {"content-type": "application/json"},
            "corpoB64": base64.b64encode(corpo).decode("ascii"),
        }

    async def evaluate(self, expressao: str, arg: Any = None) -> Any:
        self.args.append(arg)
        if self._erro is not None:
            raise self._erro
        return self._retorno

    @property
    def ultimo(self) -> dict[str, Any]:
        return self.args[-1]


def transporte(pagina: PaginaFalsa, *, credencial_id: str = CRED) -> InPageFetchTransport:
    return InPageFetchTransport(ORIGEM, pagina, credencial_id=credencial_id)


# -- contrato ---------------------------------------------------------------


def test_satisfaz_o_protocol_transport() -> None:
    assert isinstance(transporte(PaginaFalsa()), Transport)


async def test_devolve_status_corpo_e_headers() -> None:
    pdf = b"%PDF-1.7\n" + bytes(range(256)) * 4  # bytes non-utf8 de propósito
    pagina = PaginaFalsa(
        PaginaFalsa.resposta(200, pdf, {"content-type": "application/pdf"})
    )
    r = await transporte(pagina).request(sessao(), "GET", URL)
    assert (r.status, r.ok) == (200, True)
    assert r.corpo == pdf, "round-trip de base64 tem que preservar byte a byte"
    assert r.headers["content-type"] == "application/pdf"


async def test_status_de_erro_volta_como_resposta_sem_levantar() -> None:
    """`request` não interpreta status. Quem traduz é o adapter."""
    pagina = PaginaFalsa(PaginaFalsa.resposta(403, b"forbidden"))
    r = await transporte(pagina).request(sessao(), "GET", URL)
    assert (r.status, r.ok) == (403, False)


# -- uma identidade por página ----------------------------------------------


async def test_session_de_outra_credencial_e_recusada() -> None:
    pagina = PaginaFalsa()
    with pytest.raises(PermanenteError):
        await transporte(pagina).request(sessao(id_cred="cred-b"), "GET", URL)
    assert pagina.args == [], "não pode ter chegado a avaliar nada na página"


async def test_session_com_cookies_proprios_e_recusada_em_vez_de_ignorada() -> None:
    """`fetch` não define Cookie. Descartar em silêncio faria a requisição sair com
    a identidade do browser fingindo ser a da Session."""
    pagina = PaginaFalsa()
    with pytest.raises(PermanenteError):
        await transporte(pagina).request(
            sessao(cookies={"access_token": "cookie-a"}), "GET", URL
        )
    assert pagina.args == []


def test_credencial_id_vazio_e_rejeitado_no_construtor() -> None:
    with pytest.raises(ValueError):
        InPageFetchTransport(ORIGEM, PaginaFalsa(), credencial_id="")


# -- cabeçalhos -------------------------------------------------------------


@pytest.mark.parametrize(
    "nome", ["User-Agent", "user-agent", "Cookie", "Referer", "Origin"]
)
async def test_cabecalho_controlado_pelo_browser_e_recusado(nome: str) -> None:
    pagina = PaginaFalsa()
    with pytest.raises(PermanenteError):
        await transporte(pagina).request(sessao(), "GET", URL, headers={nome: "x"})
    assert pagina.args == []


async def test_authorization_do_chamador_nao_sobrescreve_a_da_sessao() -> None:
    pagina = PaginaFalsa()
    await transporte(pagina).request(
        pagina_sessao := sessao(token="jwt-da-sessao"),
        "GET",
        URL,
        headers={"authorization": "Bearer jwt-do-chamador"},
    )
    enviados = pagina.ultimo["headers"]
    assert enviados["Authorization"] == f"Bearer {pagina_sessao.token}"
    assert "jwt-do-chamador" not in str(enviados)


async def test_sessao_sem_token_nao_manda_authorization() -> None:
    pagina = PaginaFalsa()
    await transporte(pagina).request(
        sessao(token=None), "GET", URL, headers={"Authorization": "Bearer sobra"}
    )
    assert not [k for k in pagina.ultimo["headers"] if k.lower() == "authorization"]


# -- origem -----------------------------------------------------------------


async def test_url_fora_da_origem_e_recusada_sem_ecoar_a_url() -> None:
    pagina = PaginaFalsa()
    with pytest.raises(PermanenteError) as exc:
        await transporte(pagina).request(sessao(), "GET", OUTRA_ORIGEM)
    assert "evil.example.com" not in str(exc.value)
    assert pagina.args == []


async def test_url_com_userinfo_e_recusada_sem_ecoar_o_segredo() -> None:
    pagina = PaginaFalsa()
    with pytest.raises(PermanenteError) as exc:
        await transporte(pagina).request(
            sessao(), "GET", "https://usuario:senha@portaldeservicos.pdpj.jus.br/api/v2/x"
        )
    assert "senha" not in str(exc.value)


def test_origem_http_e_rejeitada_no_construtor() -> None:
    with pytest.raises(ValueError):
        InPageFetchTransport("http://pdpj.jus.br", PaginaFalsa(), credencial_id=CRED)


# -- retorno malformado -----------------------------------------------------


async def test_resposta_opaca_de_redirect_nao_passa_por_sucesso_vazio() -> None:
    pagina = PaginaFalsa({"ok": True, "status": 0, "headers": {}, "corpoB64": ""})
    with pytest.raises(PermanenteError):
        await transporte(pagina).request(sessao(), "GET", URL)


@pytest.mark.parametrize(
    "retorno",
    [
        {"ok": False, "erro": "AbortError"},
        {"ok": True, "status": "200", "corpoB64": ""},
        {"ok": True, "status": 200, "corpoB64": "nao-e-base64!!"},
        "texto solto",
        None,
    ],
)
async def test_retorno_inesperado_e_transiente_nunca_corpo_vazio(retorno: Any) -> None:
    """Devolver `bytes` vazio como sucesso arquivaria PDF de zero byte."""
    pagina = PaginaFalsa(retorno if retorno is not None else {"ok": True})
    with pytest.raises(TransienteError):
        await transporte(pagina).request(sessao(), "GET", URL)


async def test_excecao_do_evaluate_nao_vaza_url_nem_token() -> None:
    """A mensagem do Playwright inclui o argumento avaliado, e o argumento carrega
    URL e Authorization."""
    pagina = PaginaFalsa(
        erro=RuntimeError(f"Error evaluating {URL} Bearer jwt-secretissimo-a")
    )
    with pytest.raises(TransienteError) as exc:
        await transporte(pagina).request(sessao(), "GET", URL)
    msg = str(exc.value)
    assert "jwt-secretissimo-a" not in msg
    assert "0020890" not in msg
    assert exc.value.__cause__ is None, "encadeamento reintroduziria a URL no traceback"


# -- fetch_bytes ------------------------------------------------------------


async def test_fetch_bytes_devolve_binario_em_200() -> None:
    pagina = PaginaFalsa(PaginaFalsa.resposta(200, b"%PDF-1.7 conteudo"))
    assert await transporte(pagina).fetch_bytes(sessao(), URL) == b"%PDF-1.7 conteudo"


@pytest.mark.parametrize(
    ("status", "esperado"),
    [
        (401, SessaoExpiradaError),
        (429, TransienteError),
        (500, TransienteError),
        (503, TransienteError),
        (403, PermanenteError),
        (404, PermanenteError),
    ],
)
async def test_fetch_bytes_traduz_status_igual_ao_httpx_transport(
    status: int, esperado: type[Exception]
) -> None:
    """Paridade deliberada: o adapter não deve mudar de comportamento ao trocar de
    transporte. 403 e 404 param como PermanenteError — só o adapter sabe se é
    sigilo ou inexistência."""
    pagina = PaginaFalsa(PaginaFalsa.resposta(status, b"pagina de erro do WAF"))
    with pytest.raises(esperado):
        await transporte(pagina).fetch_bytes(sessao(), URL)


async def test_fetch_bytes_nao_devolve_pagina_de_erro_como_binario() -> None:
    """Uma página de erro do WAF é `bytes` válido e viraria PDF corrompido."""
    pagina = PaginaFalsa(PaginaFalsa.resposta(403, b"<html>Forbidden</html>"))
    with pytest.raises(PermanenteError):
        await transporte(pagina).fetch_bytes(sessao(), URL)


# -- política: não tem ------------------------------------------------------


async def test_nao_repete_a_requisicao() -> None:
    """Sem retry, sem backoff: isso é do orquestrador (ADR 002)."""
    pagina = PaginaFalsa(PaginaFalsa.resposta(500, b"boom"))
    await transporte(pagina).request(sessao(), "GET", URL)
    assert len(pagina.args) == 1


async def test_timeout_invalido_e_rejeitado() -> None:
    pagina = PaginaFalsa()
    for ruim in (0, -1, float("inf"), float("nan")):
        with pytest.raises(ValueError):
            await transporte(pagina).request(sessao(), "GET", URL, timeout=ruim)
    assert pagina.args == []


async def test_corpo_vai_como_base64_e_metodo_normalizado() -> None:
    pagina = PaginaFalsa()
    await transporte(pagina).request(sessao(), "post", URL, corpo=b"\x00\x01byte cru")
    arg = pagina.ultimo
    assert arg["metodo"] == "POST"
    assert base64.b64decode(arg["corpoB64"]) == b"\x00\x01byte cru"
    assert arg["timeoutMs"] > 0
