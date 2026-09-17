"""Runner real de handshake: Playwright + Handshake + InPageFetchTransport.

Fecha a lacuna L9 do lado da execução: até aqui `Handshake.capturar` só rodava contra
duplos de teste (`ContextoFalso`, `SondaFalsa`). Este módulo é o primeiro lugar do
projeto que abre um Chromium de verdade, espera o titular logar e persiste a sessão.

## O que este módulo NÃO faz, de propósito

Não seleciona certificado, não digita PIN, não resolve MFA — mesma regra do
`handshake.py` (invariante 3, ADR 003/004/007). Também **não lê estado interno do
app** (variáveis JS, serviços Angular, `window.*`): o único canal de leitura é
`BrowserContext.storage_state()`, que é exatamente o que o Protocol
`ContextoAutenticado` expõe. Ler mais que isso seria extração de credencial de
sessão de terceiro, e uma tentativa nesse sentido foi bloqueada pelo próprio
Claude Code durante a rodada de 2026-09-17 (ver
`docs/execucao/validacao-24-trts-2026-09-17.md`) — corretamente.

## A lacuna que continua aberta

Medido em 2026-09-17: o portal PDPJ nacional **não guarda o token em cookie nem em
`localStorage`** desta origem — só em memória do app. `criar_montador` abaixo lê
cookie/localStorage por nome (`token`, `jwt`, `access_token`, `id_token`) e, quando
não encontra nada, devolve uma `Session` sem material de autenticação. Isso não é
bug: `Handshake._sessao` já trata esse caso como "ainda não logou"
(`SessaoExpiradaError`), o mesmo caminho de quem está no meio do login. Para o PDPJ
nacional especificamente, este runner hoje **espera até o prazo e desiste**
(`AguardandoOperadorError`) — o gap é genuíno, não fingido.

Este módulo serve tribunais/portais que guardem o token em cookie ou localStorage
(comum em apps que usam `oidc-client-js` com storage explícito) sem mudança nenhuma.
Para o PDPJ nacional, falta decidir — com o dono do projeto, não aqui — se vale a
pena negociar acesso documentado ao mecanismo de auth, ou se a via de aquisição
segue sendo cliques reais na UI (fora do Python) em vez de `fetch` programático.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from ..core.contracts import Credencial, Session
from ..core.handshake import Handshake, MontadorSessao, Sonda, Veredito
from ..core.inpage_transport import InPageFetchTransport
from ..core.ritmo import Ritmo
from ..core.session_store import SessionStore

_PADRAO_TOKEN = re.compile(r"token|jwt", re.IGNORECASE)


def _valor_de_token(nome: str, valor: Any) -> str | None:
    if isinstance(valor, str) and valor and _PADRAO_TOKEN.search(nome):
        return valor
    return None


def _token_de_cookies(estado: Mapping[str, Any]) -> str | None:
    for cookie in estado.get("cookies") or []:
        if not isinstance(cookie, Mapping):
            continue
        achado = _valor_de_token(str(cookie.get("name", "")), cookie.get("value"))
        if achado is not None:
            return achado
    return None


def _token_de_local_storage(estado: Mapping[str, Any], origem: str) -> str | None:
    for entrada in estado.get("origins") or []:
        if not isinstance(entrada, Mapping) or entrada.get("origin") != origem:
            continue
        for item in entrada.get("localStorage") or []:
            if not isinstance(item, Mapping):
                continue
            achado = _valor_de_token(str(item.get("name", "")), item.get("value"))
            if achado is not None:
                return achado
    return None


def criar_montador(tribunal: str, origem: str, pagina: Any) -> MontadorSessao:
    """Constrói o montador deste tribunal, amarrado à página que vai fazer as
    requisições (`Session.contexto_browser`, consumido pela sonda e pelo transporte).

    Procura o token em cookie ou `localStorage` cujo nome contenha "token"/"jwt".
    **Não inventa nada quando não encontra**: devolve `Session` sem token, e
    `Handshake._sessao` converte isso em `SessaoExpiradaError` — o comportamento
    correto de "ainda não logou" ou "este portal guarda o token em outro lugar".
    """

    def montar(estado: Mapping[str, Any], credencial: Credencial) -> Session:
        token = _token_de_cookies(estado) or _token_de_local_storage(estado, origem)
        return Session(
            credencial=credencial,
            tribunal=tribunal,
            token=token,
            contexto_browser=pagina,
        )

    return montar


def criar_sonda(
    origem: str,
    credencial_id: str,
    url_sonda: str,
    *,
    timeout: float = 30.0,
) -> Sonda:
    """Sonda genérica por status HTTP, via `InPageFetchTransport`.

    `url_sonda` é obrigatório e sem default: qual requisição barata prova
    autenticação **não foi medida** para nenhum tribunal ainda (mesma advertência da
    docstring de `handshake.py`) — um default aqui repetiria o erro que o projeto
    evita em `grau_mapper` e `Cifra`.
    """
    if not url_sonda:
        raise ValueError("url_sonda é obrigatório e não tem default")

    async def sonda(sessao: Session) -> Veredito:
        pagina = sessao.contexto_browser
        if pagina is None:
            return Veredito.INDETERMINADO
        transporte = InPageFetchTransport(
            origem, pagina, credencial_id=credencial_id, timeout=timeout
        )
        try:
            resposta = await transporte.request(sessao, "GET", url_sonda, timeout=timeout)
        except Exception:
            return Veredito.INDETERMINADO
        if resposta.status in (401, 403):
            return Veredito.NAO_AUTENTICADA
        if resposta.ok:
            return Veredito.AUTENTICADA
        return Veredito.INDETERMINADO

    return sonda


async def executar_handshake(
    *,
    tribunal: str,
    origem: str,
    credencial: Credencial,
    login_url: str,
    url_sonda: str,
    store: SessionStore,
    ritmo: Ritmo,
    intervalo: float = 5.0,
    prazo: float = 900.0,
    timeout_sonda: float = 30.0,
    headless: bool = False,
) -> tuple[Session, Any, Any]:
    """Abre um Chromium real, navega até o login e espera o titular autenticar.

    Devolve `(sessao, contexto, browser)`. Este runner **não fecha** o browser: quem
    chamou decide quando (a sessão pode ser reaproveitada em requisições seguintes
    via `InPageFetchTransport`, que usa a mesma página).

    Requer o extra `browser` instalado (`pip install trt-extractor[browser]` e
    `playwright install chromium`) — import tardio de propósito, para que o resto do
    projeto não dependa de Playwright.
    """
    from playwright.async_api import async_playwright

    antes_de_sondar: Callable[[], Awaitable[None]] = _fecha_ritmo(
        ritmo, tribunal, credencial.id
    )

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=headless)
    contexto = await browser.new_context()
    pagina = await contexto.new_page()
    await pagina.goto(login_url)

    handshake = Handshake(
        tribunal,
        store=store,
        sonda=criar_sonda(origem, credencial.id, url_sonda, timeout=timeout_sonda),
        montar_sessao=criar_montador(tribunal, origem, pagina),
        intervalo=intervalo,
        prazo=prazo,
        antes_de_sondar=antes_de_sondar,
        timeout_sonda=timeout_sonda,
    )
    sessao = await handshake.capturar(contexto, credencial)
    return sessao, contexto, browser


def _fecha_ritmo(
    ritmo: Ritmo, tribunal: str, credencial_id: str
) -> Callable[[], Awaitable[None]]:
    async def aguardar() -> None:
        await ritmo.aguardar(tribunal, credencial_id)

    return aguardar
