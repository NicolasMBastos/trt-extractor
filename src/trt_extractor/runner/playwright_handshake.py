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

## Segunda estratégia: hook de captura passiva (PDPJ nacional)

Para o PDPJ nacional, `criar_montador`/`criar_sonda` acima não bastam — medido em
2026-09-17 que o token vive só em memória do app (keycloak-js). A referência que
resolve isso é o projeto irmão **TaxMap** (mesma organização, mesmo portal PDPJ,
em produção): em vez de vasculhar estado interno do app (`window.*`, o que o Claude
Code corretamente recusou a fazer nesta rodada), o TaxMap injeta um hook ANTES do
app carregar que faz monkey-patch de `window.fetch`/`XMLHttpRequest.setRequestHeader`
— captura passivamente o header `Authorization` que **o próprio app** anexa quando
ele mesmo faz uma requisição real. É o equivalente a ler a aba Network do DevTools,
não a sondar variável interna. Ver `jusbr.py:_JUSBR_API_HOOK_JS` no TaxMap e
`docs/taxmap-stability/CERTIFICATE_BROWSER_DECISION.md` de lá.

**PROVADO ao vivo em 2026-09-17**: contra o Chrome real do titular (autenticado,
`connect_over_cdp` na porta de debug), o hook capturou um Bearer de 2118 caracteres
na primeira busca de processo disparada pelo próprio app — sem ler `window.*`, sem
storage_state, só observando a própria requisição do app. Isso fecha o gap descrito
acima: o nível E (pipeline completo) deixa de estar bloqueado por falta de token.

Duas diferenças em relação a `executar_handshake`:

1. **Não abre um browser novo** — anexa a um Chrome já aberto e autenticado pelo
   titular via `connect_over_cdp` (`--remote-debugging-port` no Chrome do titular).
   Nunca fecha esse Chrome (mesma regra do TaxMap: é o navegador do titular).
2. **Não lê `storage_state`** — lê o valor que o hook capturou, exposto via
   `_ContextoComHookDeToken`, que reaproveita o mesmo laço de espera/sondagem do
   `Handshake.capturar` sem duplicar essa lógica.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from ..core.contracts import Credencial, Session
from ..core.handshake import (
    Handshake,
    MontadorSessao,
    Sonda,
    Veredito,
    expira_em_do_jwt,
)
from ..core.inpage_transport import InPageFetchTransport
from ..core.ritmo import Ritmo
from ..core.session_store import SessionStore

#: Instalado via `BrowserContext.add_init_script`, roda antes de qualquer script da
#: página. Adaptado do TaxMap (`jusbr.py:_JUSBR_API_HOOK_JS`): guarda em
#: `window.__pdpjToken` o valor de `Authorization` que o próprio app anexar em
#: `fetch`/`XMLHttpRequest` — nunca lê nem adivinha onde o app guarda o token, só
#: observa o que ele mesmo manda numa requisição real.
HOOK_CAPTURA_BEARER_JS = r"""
(function(){
  if (window.__pdpjHook) return;
  window.__pdpjHook = true;
  window.__pdpjToken = null;
  function guarda(v){
    try{
      if (v && /^bearer\s+/i.test(v)) {
        window.__pdpjToken = String(v).replace(/^bearer\s+/i, '').trim();
      }
    }catch(e){}
  }
  var of = window.fetch;
  if (of) {
    window.fetch = function(input, init){
      try{
        var h = (init && init.headers) || (input && input.headers);
        if (h){
          if (h.get) guarda(h.get('authorization') || h.get('Authorization'));
          else guarda(h['authorization'] || h['Authorization']);
        }
      }catch(e){}
      return of.apply(this, arguments);
    };
  }
  var os = XMLHttpRequest.prototype.setRequestHeader;
  XMLHttpRequest.prototype.setRequestHeader = function(k, v){
    try{ if (String(k).toLowerCase() === 'authorization') guarda(v); }catch(e){}
    return os.apply(this, arguments);
  };
})();
"""

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


# ---------------------------------------------------------------------------
# Hook de captura passiva (ver docstring do módulo, seção "PDPJ nacional")
# ---------------------------------------------------------------------------


class _ContextoComHookDeToken:
    """`ContextoAutenticado` cujo "estado" é o valor capturado pelo hook, não o
    storage_state real do browser. Existe só para reaproveitar o laço de
    espera/prazo/sondagem de `Handshake.capturar` sem duplicá-lo aqui."""

    def __init__(self, pagina: Any) -> None:
        self._pagina = pagina

    async def storage_state(self) -> Mapping[str, Any]:
        token = await self._pagina.evaluate("() => window.__pdpjToken")
        return {"token_capturado": token}


def criar_montador_via_hook(tribunal: str, pagina: Any) -> MontadorSessao:
    """Monta a `Session` a partir do token que o hook capturou (não de cookie nem
    `localStorage` — ver `criar_montador` para essa outra estratégia).

    `expira_em` vem do próprio JWT (`exp`), como o resto do projeto já faz —
    agendamento de renovação, nunca prova de legitimidade (a prova é a sonda).
    """

    def montar(estado: Mapping[str, Any], credencial: Credencial) -> Session:
        bruto = estado.get("token_capturado")
        token = bruto if isinstance(bruto, str) and bruto else None
        return Session(
            credencial=credencial,
            tribunal=tribunal,
            token=token,
            contexto_browser=pagina,
            expira_em=expira_em_do_jwt(token) if token else None,
        )

    return montar


async def conectar_chrome_existente(cdp_url: str) -> tuple[Any, Any]:
    """Anexa a um Chrome já aberto e autenticado pelo titular
    (`chrome --remote-debugging-port=9222`, aberto e logado por fora deste processo).

    Devolve `(playwright, browser)`. **Nunca** chamar `browser.close()` no valor
    devolvido — é o Chrome do titular, não um browser descartável do projeto; só
    `playwright.stop()` é seguro (encerra o driver do Playwright, não o Chrome).
    Mesma regra do TaxMap (`jusbr.py`: "del driver # NÃO fecha o Chrome do usuário").
    """
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp(cdp_url)
    return pw, browser


async def executar_handshake_com_hook(
    *,
    tribunal: str,
    origem: str,
    credencial: Credencial,
    cdp_url: str,
    url_navegacao: str,
    url_sonda: str,
    store: SessionStore,
    ritmo: Ritmo,
    intervalo: float = 2.0,
    prazo: float = 60.0,
    timeout_sonda: float = 30.0,
) -> tuple[Session, Any, Any, Any]:
    """Anexa ao Chrome real do titular, instala o hook de captura e espera o
    próprio app revelar o Bearer numa requisição real dele.

    Devolve `(sessao, contexto, browser, playwright)`. `browser` é o Chrome do
    titular (ver `conectar_chrome_existente` sobre nunca fechá-lo); `playwright` é
    só o driver, seguro de parar quando terminar.

    Pré-condição: o titular já autenticou nesse Chrome antes de rodar isto (login é
    ato do titular, ADR 003/004/007 — este runner não abre tela de login nenhuma).
    """
    pw, browser = await conectar_chrome_existente(cdp_url)
    contexto = browser.contexts[0] if browser.contexts else await browser.new_context()
    await contexto.add_init_script(HOOK_CAPTURA_BEARER_JS)
    pagina = contexto.pages[0] if contexto.pages else await contexto.new_page()
    await pagina.goto(url_navegacao)

    handshake = Handshake(
        tribunal,
        store=store,
        sonda=criar_sonda(origem, credencial.id, url_sonda, timeout=timeout_sonda),
        montar_sessao=criar_montador_via_hook(tribunal, pagina),
        intervalo=intervalo,
        prazo=prazo,
        antes_de_sondar=_fecha_ritmo(ritmo, tribunal, credencial.id),
        timeout_sonda=timeout_sonda,
    )
    sessao = await handshake.capturar(_ContextoComHookDeToken(pagina), credencial)
    return sessao, contexto, browser, pw
