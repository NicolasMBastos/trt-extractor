"""Testes do HttpxTransport. Sem rede: tudo por `httpx.MockTransport`.

O foco não é "o httpx funciona" — é o que o transporte promete e que o httpx
sozinho não dá: identidade vinda só da `Session` de cada chamada, nenhum cookie
aprendido, nenhum redirect seguido, nenhuma origem estranha, nenhuma mensagem de
erro com segredo dentro.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trt_extractor.core.contracts import (
    Credencial,
    PermanenteError,
    SessaoExpiradaError,
    Session,
    SigiloError,
    TransienteError,
    Transport,
)
from trt_extractor.core.httpx_transport import (
    USER_AGENT,
    HttpxTransport,
)

ORIGEM = "https://portaldeservicos.pdpj.jus.br"
URL = f"{ORIGEM}/api/v2/processos/0020890-39.2024.5.04.0015"
OUTRA_ORIGEM = "https://evil.example.com/api/v2/processos/1"


def sessao(
    *,
    id_cred: str = "cred-a",
    token: str | None = "jwt-secretissimo-a",
    cookies: dict[str, str] | None = None,
) -> Session:
    return Session(
        credencial=Credencial(id=id_cred, cpf="00000000000"),
        tribunal="TRT4",
        token=token,
        cookies={"access_token": "cookie-a"} if cookies is None else cookies,
    )


class Espiao:
    """MockTransport que guarda as requisições e devolve o que o teste mandar."""

    def __init__(self, responder: Any = None) -> None:
        self.pedidos: list[httpx.Request] = []
        self._responder = responder or (lambda _req: httpx.Response(200, content=b"ok"))

    async def _handler(self, request: httpx.Request) -> httpx.Response:
        self.pedidos.append(request)
        await asyncio.sleep(0)  # deixa as tarefas concorrentes se intercalarem
        resultado = self._responder(request)
        return resultado

    @property
    def transporte(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handler)

    @property
    def unico(self) -> httpx.Request:
        assert len(self.pedidos) == 1, f"esperava 1 requisição, houve {len(self.pedidos)}"
        return self.pedidos[0]


def transporte(espiao: Espiao, **kwargs: Any) -> HttpxTransport:
    return HttpxTransport(ORIGEM, transporte=espiao.transporte, **kwargs)


# -- contrato ---------------------------------------------------------------


def test_satisfaz_o_protocol() -> None:
    assert isinstance(transporte(Espiao()), Transport)


async def test_status_de_erro_volta_como_resposta_nao_como_excecao() -> None:
    espiao = Espiao(lambda _r: httpx.Response(500, content=b"boom", headers={"X-A": "1"}))
    async with transporte(espiao) as t:
        resposta = await t.request(sessao(), "GET", URL)
    assert (resposta.status, resposta.corpo, resposta.ok) == (500, b"boom", False)
    assert resposta.headers["x-a"] == "1"


async def test_params_entram_na_url() -> None:
    espiao = Espiao()
    async with transporte(espiao) as t:
        await t.request(sessao(), "GET", URL, params={"pagina": 2})
    assert espiao.unico.url.params["pagina"] == "2"


# -- configuração exigida pela ADR 002 --------------------------------------


async def test_http2_e_ligado_no_client_real() -> None:
    # Sem transporte injetado: é o caminho de produção que precisa de http2.
    # Privado de propósito — se o httpx mudar isso, o teste quebra em vez de o
    # WAF do PDPJ passar a devolver 403 em produção (ADR 002, adendo 2).
    t = HttpxTransport(ORIGEM)
    try:
        assert t._client._transport._pool._http2 is True  # type: ignore[attr-defined]
    finally:
        await t.aclose()


async def test_user_agent_de_chrome_estavel() -> None:
    espiao = Espiao()
    async with transporte(espiao) as t:
        await t.request(sessao(), "GET", URL)
        await t.request(sessao(), "GET", URL)
    uas = {p.headers["user-agent"] for p in espiao.pedidos}
    assert uas == {USER_AGENT}
    assert "Chrome/" in USER_AGENT


def test_sem_env_e_sem_redirect_automatico() -> None:
    t = transporte(Espiao())
    assert t._client.trust_env is False
    assert t._client.follow_redirects is False


# -- timeout ----------------------------------------------------------------


@pytest.mark.parametrize("ruim", [0, -1, float("inf"), float("nan")])
def test_timeout_precisa_ser_finito_e_positivo(ruim: float) -> None:
    with pytest.raises(ValueError, match="finito e positivo"):
        HttpxTransport(ORIGEM, timeout=ruim)


@pytest.mark.parametrize("ruim", [0, -1, float("inf"), float("nan")])
async def test_timeout_por_chamada_tambem_e_validado(ruim: float) -> None:
    async with transporte(Espiao()) as t:
        with pytest.raises(ValueError, match="finito e positivo"):
            await t.request(sessao(), "GET", URL, timeout=ruim)


async def test_timeout_explicito_chega_na_requisicao() -> None:
    espiao = Espiao()
    async with transporte(espiao, timeout=7.0) as t:
        await t.request(sessao(), "GET", URL)
        await t.request(sessao(), "GET", URL, timeout=1.5)
    assert espiao.pedidos[0].extensions["timeout"]["read"] == 7.0
    assert espiao.pedidos[1].extensions["timeout"]["read"] == 1.5


# -- falha de rede ----------------------------------------------------------


def _explode(_request: httpx.Request) -> httpx.Response:
    # A mensagem do httpx costuma carregar a URL; aqui ela carrega o pior caso.
    raise httpx.ConnectTimeout(f"falhou em {URL}?Authorization=Bearer+jwt-secretissimo-a")


async def test_falha_de_rede_vira_transiente_sem_segredo_nem_encadeamento() -> None:
    async with transporte(Espiao(_explode)) as t:
        with pytest.raises(TransienteError) as info:
            await t.request(sessao(), "GET", URL)
    mensagem = str(info.value)
    assert "ConnectTimeout" in mensagem and "GET" in mensagem
    for segredo in ("jwt-secretissimo-a", "cookie-a", URL, "pdpj", "Authorization"):
        assert segredo not in mensagem
    assert info.value.__cause__ is None
    assert info.value.__suppress_context__ is True


async def test_falha_de_rede_nao_e_repetida() -> None:
    espiao = Espiao(_explode)
    async with transporte(espiao) as t:
        with pytest.raises(TransienteError):
            await t.request(sessao(), "GET", URL)
    assert len(espiao.pedidos) == 1


async def test_status_de_erro_nao_e_repetido() -> None:
    espiao = Espiao(lambda _r: httpx.Response(503))
    async with transporte(espiao) as t:
        with pytest.raises(TransienteError):
            await t.fetch_bytes(sessao(), URL)
    assert len(espiao.pedidos) == 1


# -- identidade: só da Session, e só da desta chamada -----------------------


async def test_credencial_com_token_e_cookies() -> None:
    espiao = Espiao()
    async with transporte(espiao) as t:
        await t.request(
            sessao(token="jwt-a", cookies={"access_token": "c1", "Xsrf-Token": "c2"}),
            "GET",
            URL,
        )
    pedido = espiao.unico
    assert pedido.headers["authorization"] == "Bearer jwt-a"
    assert pedido.headers["cookie"] == "access_token=c1; Xsrf-Token=c2"


async def test_credencial_sem_token_e_sem_cookies_nao_manda_nada() -> None:
    espiao = Espiao()
    async with transporte(espiao) as t:
        await t.request(sessao(token=None, cookies={}), "GET", URL)
    pedido = espiao.unico
    assert "authorization" not in pedido.headers
    assert "cookie" not in pedido.headers


async def test_header_do_chamador_nao_forja_identidade() -> None:
    """Sessão sem token: nem um `authorization` minúsculo do chamador passa."""
    espiao = Espiao()
    async with transporte(espiao) as t:
        await t.request(
            sessao(token=None, cookies={}),
            "GET",
            URL,
            headers={"authorization": "Bearer forjado", "cookie": "roubado=1"},
        )
        await t.request(
            sessao(token="jwt-a", cookies={"access_token": "c1"}),
            "GET",
            URL,
            headers={
                "Authorization": "Bearer forjado",
                "User-Agent": "agente-forjado",
            },
        )
    primeiro, segundo = espiao.pedidos
    assert "authorization" not in primeiro.headers
    assert "cookie" not in primeiro.headers
    assert segundo.headers["authorization"] == "Bearer jwt-a"
    assert "forjado" not in segundo.headers["authorization"]
    assert segundo.headers["user-agent"] == USER_AGENT


async def test_duas_credenciais_na_mesma_instancia_nao_se_misturam() -> None:
    espiao = Espiao()
    a = sessao(id_cred="cred-a", token="jwt-a", cookies={"access_token": "ca"})
    b = sessao(id_cred="cred-b", token=None, cookies={})
    async with transporte(espiao) as t:
        await t.request(a, "GET", URL)
        await t.request(b, "GET", URL)
        await t.request(a, "GET", URL)
    p_a1, p_b, p_a2 = espiao.pedidos
    assert p_a1.headers["authorization"] == "Bearer jwt-a"
    assert p_a2.headers["authorization"] == "Bearer jwt-a"
    assert "authorization" not in p_b.headers
    assert "cookie" not in p_b.headers


# -- Set-Cookie: nada é aprendido -------------------------------------------


def _semeia_cookie(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        content=b"ok",
        headers={"Set-Cookie": "access_token=VAZADO; Path=/"},
    )


async def test_set_cookie_nao_fica_no_client() -> None:
    espiao = Espiao(_semeia_cookie)
    async with transporte(espiao) as t:
        await t.request(sessao(), "GET", URL)
        assert list(t._client.cookies.jar) == []


async def test_set_cookie_de_uma_sessao_nao_sai_na_chamada_de_outra() -> None:
    espiao = Espiao(_semeia_cookie)
    a = sessao(id_cred="cred-a", token="jwt-a", cookies={"access_token": "ca"})
    b = sessao(id_cred="cred-b", token="jwt-b", cookies={})
    async with transporte(espiao) as t:
        await t.request(a, "GET", URL)
        await t.request(b, "GET", URL)
    _, p_b = espiao.pedidos
    assert "cookie" not in p_b.headers
    assert "VAZADO" not in str(p_b.headers)


async def test_set_cookie_concorrente_nao_contamina() -> None:
    """N sessões em paralelo, cada resposta semeando um cookie: cada requisição
    tem que sair com o cookie da sua própria Session e de nenhuma outra."""
    espiao = Espiao(_semeia_cookie)
    sessoes = [
        sessao(id_cred=f"cred-{i}", token=f"jwt-{i}", cookies={"access_token": f"c{i}"})
        for i in range(12)
    ]
    async with transporte(espiao) as t:
        await asyncio.gather(*(t.request(s, "GET", URL) for s in sessoes))
        assert list(t._client.cookies.jar) == []

    pares = {(p.headers["authorization"], p.headers["cookie"]) for p in espiao.pedidos}
    assert pares == {(f"Bearer jwt-{i}", f"access_token=c{i}") for i in range(12)}


# -- origem e URL -----------------------------------------------------------


async def test_redirect_para_fora_nao_e_seguido() -> None:
    espiao = Espiao(lambda _r: httpx.Response(302, headers={"Location": OUTRA_ORIGEM}))
    async with transporte(espiao) as t:
        resposta = await t.request(sessao(), "GET", URL)
    assert resposta.status == 302
    assert espiao.unico.url.host == "portaldeservicos.pdpj.jus.br"
    assert len(espiao.pedidos) == 1  # a Session não foi para evil.example.com


@pytest.mark.parametrize(
    "ruim",
    [
        OUTRA_ORIGEM,  # outra origem
        "https://portaldeservicos.pdpj.jus.br.evil.com/",  # sufixo colado
        "https://portaldeservicos.pdpj.jus.br:8443/api",  # mesma host, outra porta
        "http://portaldeservicos.pdpj.jus.br/api",  # sem TLS
        "file:///etc/passwd",  # nem http
        "https://user:senha@portaldeservicos.pdpj.jus.br/api",  # userinfo
        "https://portaldeservicos.pdpj.jus.br@evil.com/api",  # userinfo disfarçado
    ],
)
async def test_url_fora_da_politica_e_barrada_antes_de_sair(ruim: str) -> None:
    espiao = Espiao()
    async with transporte(espiao) as t:
        with pytest.raises(PermanenteError) as info:
            await t.request(sessao(), "GET", ruim)
        with pytest.raises(PermanenteError):
            await t.fetch_bytes(sessao(), ruim)
    assert espiao.pedidos == []  # nada saiu: a Session não vazou
    assert "senha" not in str(info.value)  # a URL rejeitada é o próprio segredo


async def test_params_nao_driblam_a_origem() -> None:
    espiao = Espiao()
    async with transporte(espiao) as t:
        with pytest.raises(PermanenteError):
            await t.request(sessao(), "GET", OUTRA_ORIGEM, params={"a": 1})
    assert espiao.pedidos == []


@pytest.mark.parametrize(
    "ruim",
    ["http://portaldeservicos.pdpj.jus.br", "https://u:p@x.jus.br", "https://"],
)
def test_origem_invalida_e_recusada_no_construtor(ruim: str) -> None:
    with pytest.raises(ValueError, match="origem"):
        HttpxTransport(ruim)


# -- fetch_bytes ------------------------------------------------------------


async def test_fetch_bytes_devolve_corpo_em_200() -> None:
    espiao = Espiao(lambda _r: httpx.Response(200, content=b"%PDF-1.4"))
    async with transporte(espiao) as t:
        assert await t.fetch_bytes(sessao(), URL) == b"%PDF-1.4"


@pytest.mark.parametrize(
    ("status", "esperado"),
    [
        (401, SessaoExpiradaError),
        (429, TransienteError),
        (500, TransienteError),
        (503, TransienteError),
        (403, PermanenteError),
        (404, PermanenteError),
        (302, PermanenteError),
    ],
)
async def test_fetch_bytes_confere_status_antes_dos_bytes(
    status: int, esperado: type[Exception]
) -> None:
    espiao = Espiao(lambda _r: httpx.Response(status, content=b"<html>WAF</html>"))
    async with transporte(espiao) as t:
        with pytest.raises(esperado) as info:
            await t.fetch_bytes(sessao(), URL)
    assert "WAF" not in str(info.value)  # corpo de erro não vira PDF nem mensagem


async def test_403_nao_vira_sigilo_sem_evidencia() -> None:
    """403 é ambíguo (sigilo, WAF, rate limit, permissão). Quem traduz é o
    adapter, que conhece o tribunal — nunca o transporte."""
    espiao = Espiao(lambda _r: httpx.Response(403))
    async with transporte(espiao) as t:
        with pytest.raises(PermanenteError) as info:
            await t.fetch_bytes(sessao(), URL)
    assert not isinstance(info.value, SigiloError)


# -- ciclo de vida ----------------------------------------------------------


async def test_client_e_reusado_entre_chamadas() -> None:
    espiao = Espiao()
    async with transporte(espiao) as t:
        cliente = t._client
        await t.request(sessao(), "GET", URL)
        await t.request(sessao(), "GET", URL)
        assert t._client is cliente


async def test_aclose_fecha_o_client() -> None:
    t = transporte(Espiao())
    await t.aclose()
    assert t._client.is_closed


async def test_context_manager_fecha_no_fim() -> None:
    espiao = Espiao()
    async with transporte(espiao) as t:
        await t.request(sessao(), "GET", URL)
        assert not t._client.is_closed
    assert t._client.is_closed
