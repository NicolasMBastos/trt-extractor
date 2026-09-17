"""Testes do runner de handshake Playwright. Sem browser, sem rede.

Playwright não entra aqui: `criar_montador` e `criar_sonda` só dependem do Protocol
`PaginaFetch` (o mesmo duplo de `test_inpage_transport.py`), e `executar_handshake`
importa `playwright.async_api` só dentro da função — o resto do módulo é testável
sem o pacote instalado.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trt_extractor.core.contracts import Credencial, Session
from trt_extractor.core.handshake import Veredito
from trt_extractor.runner.playwright_handshake import (
    HOOK_CAPTURA_BEARER_JS,
    _ContextoComHookDeToken,
    criar_montador,
    criar_montador_via_hook,
    criar_sonda,
)

ORIGEM = "https://portaldeservicos.pdpj.jus.br"
TRIBUNAL = "TRT4"
CRED = Credencial("cred-do-titular", "00000000000")

ESTADO_SEM_TOKEN: dict[str, Any] = {
    "cookies": [{"name": "tour-primeira-notificacao", "value": "true"}],
    "origins": [],
}
ESTADO_COM_TOKEN_EM_COOKIE: dict[str, Any] = {
    "cookies": [{"name": "access_token", "value": "jwt-do-cookie"}],
    "origins": [],
}
ESTADO_COM_TOKEN_EM_LOCAL_STORAGE: dict[str, Any] = {
    "cookies": [],
    "origins": [
        {
            "origin": ORIGEM,
            "localStorage": [{"name": "kc-token", "value": "jwt-do-local-storage"}],
        }
    ],
}
ESTADO_LOCAL_STORAGE_DE_OUTRA_ORIGEM: dict[str, Any] = {
    "cookies": [],
    "origins": [
        {
            "origin": "https://outra.origem.example",
            "localStorage": [{"name": "access_token", "value": "nao-deve-ser-lido"}],
        }
    ],
}


class PaginaFalsa:
    """Mesmo duplo de `test_inpage_transport.py`: guarda o arg, devolve o programado."""

    def __init__(self, retorno: Any = None, erro: BaseException | None = None) -> None:
        self.args: list[dict[str, Any]] = []
        self._erro = erro
        self._retorno = retorno if retorno is not None else self.resposta(200, b"ok")

    @staticmethod
    def resposta(status: int, corpo: bytes) -> dict[str, Any]:
        return {
            "ok": True,
            "status": status,
            "headers": {"content-type": "application/json"},
            "corpoB64": base64.b64encode(corpo).decode("ascii"),
        }

    async def evaluate(self, expressao: str, arg: Any = None) -> Any:
        self.args.append(arg)
        if self._erro is not None:
            raise self._erro
        return self._retorno


# -- criar_montador -----------------------------------------------------------


def test_montador_sem_token_devolve_sessao_sem_material() -> None:
    """Nada de placeholder inventado: sem token achado, `Session.token` é `None`."""
    montar = criar_montador(TRIBUNAL, ORIGEM, PaginaFalsa())
    sessao = montar(ESTADO_SEM_TOKEN, CRED)
    assert sessao.token is None
    assert sessao.tribunal == TRIBUNAL
    assert sessao.credencial == CRED


def test_montador_le_token_de_cookie_por_nome() -> None:
    montar = criar_montador(TRIBUNAL, ORIGEM, PaginaFalsa())
    sessao = montar(ESTADO_COM_TOKEN_EM_COOKIE, CRED)
    assert sessao.token == "jwt-do-cookie"


def test_montador_le_token_de_local_storage_da_origem_certa() -> None:
    montar = criar_montador(TRIBUNAL, ORIGEM, PaginaFalsa())
    sessao = montar(ESTADO_COM_TOKEN_EM_LOCAL_STORAGE, CRED)
    assert sessao.token == "jwt-do-local-storage"


def test_montador_ignora_local_storage_de_outra_origem() -> None:
    """Token de outra origem não é deste tribunal — ler ele seria montar identidade
    errada, o mesmo risco que `InPageFetchTransport._confere_sessao` já veda."""
    montar = criar_montador(TRIBUNAL, ORIGEM, PaginaFalsa())
    sessao = montar(ESTADO_LOCAL_STORAGE_DE_OUTRA_ORIGEM, CRED)
    assert sessao.token is None


def test_montador_amarra_a_pagina_recebida() -> None:
    pagina = PaginaFalsa()
    montar = criar_montador(TRIBUNAL, ORIGEM, pagina)
    sessao = montar(ESTADO_SEM_TOKEN, CRED)
    assert sessao.contexto_browser is pagina


# -- criar_sonda ---------------------------------------------------------------


def test_sonda_exige_url_sem_default() -> None:
    with pytest.raises(ValueError, match="url_sonda"):
        criar_sonda(ORIGEM, CRED.id, "")


async def test_sonda_200_e_autenticada() -> None:
    pagina = PaginaFalsa(PaginaFalsa.resposta(200, b"{}"))
    sonda = criar_sonda(ORIGEM, CRED.id, f"{ORIGEM}/api/v2/sonda")
    sessao = Session(CRED, TRIBUNAL, token="t", contexto_browser=pagina)
    assert await sonda(sessao) is Veredito.AUTENTICADA


@pytest.mark.parametrize("status", [401, 403])
async def test_sonda_401_403_e_nao_autenticada(status: int) -> None:
    pagina = PaginaFalsa(PaginaFalsa.resposta(status, b"{}"))
    sonda = criar_sonda(ORIGEM, CRED.id, f"{ORIGEM}/api/v2/sonda")
    sessao = Session(CRED, TRIBUNAL, token="t", contexto_browser=pagina)
    assert await sonda(sessao) is Veredito.NAO_AUTENTICADA


async def test_sonda_outro_status_e_indeterminado() -> None:
    pagina = PaginaFalsa(PaginaFalsa.resposta(500, b"{}"))
    sonda = criar_sonda(ORIGEM, CRED.id, f"{ORIGEM}/api/v2/sonda")
    sessao = Session(CRED, TRIBUNAL, token="t", contexto_browser=pagina)
    assert await sonda(sessao) is Veredito.INDETERMINADO


async def test_sonda_erro_de_avaliacao_e_indeterminado() -> None:
    pagina = PaginaFalsa(erro=RuntimeError("página fechada"))
    sonda = criar_sonda(ORIGEM, CRED.id, f"{ORIGEM}/api/v2/sonda")
    sessao = Session(CRED, TRIBUNAL, token="t", contexto_browser=pagina)
    assert await sonda(sessao) is Veredito.INDETERMINADO


async def test_sonda_sem_pagina_na_sessao_e_indeterminado() -> None:
    """Sessão sem `contexto_browser` (ex.: montada por outro runner) não pode
    disparar `fetch` nenhum — indeterminado, nunca uma exceção subindo pro chamador."""
    sonda = criar_sonda(ORIGEM, CRED.id, f"{ORIGEM}/api/v2/sonda")
    sessao = Session(CRED, TRIBUNAL, token="t", contexto_browser=None)
    assert await sonda(sessao) is Veredito.INDETERMINADO


# -- hook de captura passiva (estratégia TaxMap) -------------------------------


def _jwt(carga: dict[str, Any]) -> str:
    corpo = base64.urlsafe_b64encode(json.dumps(carga).encode()).rstrip(b"=").decode()
    return f"cabecalho.{corpo}.assinatura"


class PaginaComToken:
    """Duplo mínimo: `evaluate` devolve o token que o teste programar, como se o
    hook JS já tivesse capturado. Não executa JS de verdade."""

    def __init__(self, token: str | None) -> None:
        self._token = token
        self.avaliado: list[str] = []

    async def evaluate(self, expressao: str, arg: Any = None) -> Any:
        self.avaliado.append(expressao)
        return self._token


def test_hook_js_captura_authorization_de_fetch_e_xhr() -> None:
    """Não roda num browser real (fora de escopo de teste sem rede), mas prova que
    o hook tem as duas pontas: intercepta `fetch` E `XMLHttpRequest`, e só guarda
    valor com prefixo Bearer — não guarda um header Authorization qualquer."""
    assert "window.fetch = function" in HOOK_CAPTURA_BEARER_JS
    assert "XMLHttpRequest.prototype.setRequestHeader" in HOOK_CAPTURA_BEARER_JS
    assert "bearer" in HOOK_CAPTURA_BEARER_JS.lower()


async def test_contexto_com_hook_le_o_token_capturado() -> None:
    pagina = PaginaComToken("jwt-capturado")
    contexto = _ContextoComHookDeToken(pagina)
    estado = await contexto.storage_state()
    assert estado == {"token_capturado": "jwt-capturado"}
    assert pagina.avaliado == ["() => window.__pdpjToken"]


async def test_montador_via_hook_sem_token_capturado_ainda() -> None:
    """Hook instalado mas nenhuma requisição real do app disparou ainda — `None`,
    nunca um placeholder inventado (o mesmo princípio de `criar_montador`)."""
    montar = criar_montador_via_hook(TRIBUNAL, PaginaComToken(None))
    sessao = montar({"token_capturado": None}, CRED)
    assert sessao.token is None
    assert sessao.expira_em is None


def test_montador_via_hook_calcula_expira_em_do_proprio_jwt() -> None:
    momento = 1_800_000_000
    token = _jwt({"exp": momento})
    montar = criar_montador_via_hook(TRIBUNAL, PaginaComToken(token))
    sessao = montar({"token_capturado": token}, CRED)
    assert sessao.token == token
    assert sessao.expira_em is not None
    assert sessao.expira_em.timestamp() == momento
    assert sessao.contexto_browser is not None
