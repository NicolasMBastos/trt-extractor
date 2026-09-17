"""Transporte por `fetch` de dentro da página. Implementa o Protocol `Transport`.

Existe porque a ADR 002 **não generaliza**: o transporte é propriedade do canal,
não do projeto. Medido em 2026-09-08:

| Canal | `httpx` http2+UA | `fetch` in-page |
|---|---|---|
| PDPJ nacional (`api/v2`) | **200** em listagem e binário | não necessário |
| FALCÃO (`no-auth/pesquisa`) | **403** "tentativa inválida de acesso" | **responde** |

Ou seja: `HttpxTransport` segue sendo o substrato de volume da Via 0, e este módulo
é para os canais que rejeitam cliente HTTP puro. Qual usar por canal vem de
`capabilities.yaml`, medido, nunca presumido.

Herda do browser o que um cliente HTTP não tem: cookies de load balancer, a
impressão TLS/HTTP2 real e a sessão que o humano abriu. **Isso não é evasão** — é o
oposto: em vez de forjar um browser, usa o browser de verdade, como o TaxMap já faz
(ADR 004, invariante 4).

Três consequências duras de rodar dentro da página, e como este módulo as trata:

1. **A identidade é a da PÁGINA, não a do parâmetro.** A página carrega uma sessão
   só. Por isso a instância é vinculada a um `credencial_id` no construtor e recusa
   `Session` de outra credencial — senão a chamada de uma credencial sairia com a
   identidade de outra, silenciosamente.
2. **`fetch` proíbe definir `User-Agent` e `Cookie`.** O browser impõe os seus. Uma
   `Session` que traga cookies próprios **não pode** ser aplicada aqui, e o módulo
   levanta erro em vez de descartar em silêncio — cookie descartado sem aviso é
   requisição saindo com a identidade errada.
3. **Bytes voltam por base64.** É o que a docstring do Protocol já previa: JS não
   devolve `bytes`, e é por isso que `fetch_bytes` existe separado de `request`.

Zero política, igual ao `HttpxTransport`: sem retry, sem backoff, sem circuit
breaker, sem seguir redirect. Isso é do orquestrador. E a mensagem de erro não
carrega URL, header nem token.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping
from typing import Any, Protocol

import httpx

from .contracts import (
    PermanenteError,
    Resposta,
    SessaoExpiradaError,
    Session,
    TransienteError,
)

TIMEOUT_PADRAO = 30.0

# Cabeçalhos que o browser controla e `fetch` recusa definir. Aceitar um deles do
# chamador seria prometer algo que a requisição não cumpre.
PROIBIDOS = frozenset({"user-agent", "cookie", "host", "referer", "origin"})

# Executado na página. Devolve sempre um objeto — inclusive em status de erro, para
# o chamador decidir. `credentials: 'include'` é o ponto do transporte: usa a sessão
# real do browser. `redirect: 'manual'` mantém a paridade com o HttpxTransport, que
# não segue redirect.
_JS = """
async (a) => {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), a.timeoutMs);
  try {
    const r = await fetch(a.url, {
      method: a.metodo,
      headers: a.headers,
      body: a.corpoB64
        ? Uint8Array.from(atob(a.corpoB64), c => c.charCodeAt(0))
        : undefined,
      credentials: 'include',
      redirect: 'manual',
      signal: ctl.signal,
    });
    const buf = new Uint8Array(await r.arrayBuffer());
    let bin = '';
    for (let i = 0; i < buf.length; i += 0x8000) {
      bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
    }
    const h = {};
    r.headers.forEach((v, k) => { h[k] = v; });
    return { ok: true, status: r.status, headers: h, corpoB64: btoa(bin) };
  } catch (e) {
    return { ok: false, erro: (e && e.name) || 'Error' };
  } finally {
    clearTimeout(t);
  }
}
"""


class PaginaFetch(Protocol):
    """O mínimo que este transporte usa de uma página de browser.

    É `playwright.async_api.Page.evaluate`, reduzido ao que importa — para o teste
    poder injetar um duplo sem subir browser, e para o módulo não depender do
    Playwright em tempo de import.
    """

    async def evaluate(self, expressao: str, arg: Any = None) -> Any: ...


def _timeout_valido(valor: float) -> float:
    """Timeout finito e positivo. `None` não é opção: um `fetch` pendurado segura a
    página e, com ela, o worker e o slot do pool."""
    if not 0 < valor < float("inf"):  # NaN cai aqui também
        raise ValueError(f"timeout deve ser finito e positivo, recebido {valor!r}")
    return float(valor)


class InPageFetchTransport:
    """`Transport` que executa `fetch` dentro de uma página já autenticada.

    `origem` é a única origem HTTPS que esta instância aceita. `credencial_id` é a
    identidade que a página carrega — e a única que esta instância serve.

    Não abre, não fecha e não navega a página: quem a controla é o dono da sessão.
    O handshake é ato do titular (invariante 3) e não acontece aqui.
    """

    def __init__(
        self,
        origem: str,
        pagina: PaginaFetch,
        *,
        credencial_id: str,
        timeout: float = TIMEOUT_PADRAO,
    ) -> None:
        self._origem = httpx.URL(origem)
        if (
            self._origem.scheme != "https"
            or not self._origem.host
            or self._origem.userinfo
        ):
            raise ValueError("origem deve ser https, com host e sem userinfo")
        if not credencial_id:
            raise ValueError("credencial_id é obrigatório: a página carrega uma só")
        self._pagina = pagina
        self._credencial_id = credencial_id
        self._timeout = _timeout_valido(timeout)

    # -- montagem -----------------------------------------------------------

    def _alvo(self, url: str, params: Mapping[str, Any] | None) -> httpx.URL:
        """URL final validada contra a origem permitida.

        A mensagem nunca ecoa a URL: `https://usuario:senha@host/` é justamente o
        caso em que a URL rejeitada *é* o segredo.
        """
        alvo = httpx.URL(url, params=params) if params else httpx.URL(url)
        if alvo.scheme != "https":
            raise PermanenteError("URL insegura: só https é aceito")
        if alvo.userinfo:
            raise PermanenteError("URL com userinfo não é aceita")
        if (alvo.host, alvo.port) != (self._origem.host, self._origem.port):
            raise PermanenteError("URL fora da origem permitida para este transporte")
        return alvo

    def _confere_sessao(self, session: Session) -> None:
        """A página tem uma identidade só. Servir outra seria atribuir o acesso ao
        advogado errado — o oposto do que a ADR 007 exige."""
        if session.credencial.id != self._credencial_id:
            raise PermanenteError(
                "Session de outra credencial: a página carrega uma identidade só"
            )
        if session.cookies:
            # Descartar em silêncio faria a requisição sair com a identidade do
            # browser fingindo ser a da Session. Erro alto é o comportamento certo.
            raise PermanenteError(
                "Session com cookies próprios não é aplicável in-page: "
                "`fetch` não define Cookie; use HttpxTransport"
            )

    def _headers(
        self, session: Session, extras: Mapping[str, str] | None
    ) -> dict[str, str]:
        """Identidade só da `Session`, aplicada por último. Cabeçalho que o browser
        controla é recusado, nunca silenciosamente ignorado."""
        headers: dict[str, str] = {}
        if extras:
            for nome, valor in extras.items():
                if nome.lower() in PROIBIDOS:
                    raise PermanenteError(
                        f"cabeçalho {nome.lower()!r} é controlado pelo browser "
                        "e não pode ser definido in-page"
                    )
                headers[nome] = valor
        # Authorization por último e sem exceção: sessão sem token não manda
        # Authorization nenhum, mesmo que o chamador tenha passado um.
        headers.pop("Authorization", None)
        for nome in [n for n in headers if n.lower() == "authorization"]:
            del headers[nome]
        if session.token:
            headers["Authorization"] = f"Bearer {session.token}"
        return headers

    # -- Protocol Transport -------------------------------------------------

    async def request(
        self,
        session: Session,
        metodo: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        corpo: bytes | None = None,
        timeout: float | None = None,
    ) -> Resposta:
        """Devolve a `Resposta` inclusive em status de erro. Não interpreta status,
        não repete, não segue redirect."""
        self._confere_sessao(session)
        alvo = self._alvo(url, params)
        espera = self._timeout if timeout is None else _timeout_valido(timeout)
        arg = {
            "url": str(alvo),
            "metodo": metodo.upper(),
            "headers": self._headers(session, headers),
            "corpoB64": base64.b64encode(corpo).decode("ascii") if corpo else None,
            "timeoutMs": int(espera * 1000),
        }
        try:
            bruto = await self._pagina.evaluate(_JS, arg)
        except Exception as erro:
            # Sem `str(erro)` e sem `from erro`: a mensagem do Playwright inclui o
            # argumento avaliado, e o argumento carrega URL e Authorization.
            raise TransienteError(
                f"falha ao avaliar fetch na página: {type(erro).__name__}"
            ) from None
        return self._resposta(bruto)

    def _resposta(self, bruto: Any) -> Resposta:
        """Traduz o retorno do JS. Formato inesperado é falha, não `bytes` vazio:
        devolver corpo vazio como sucesso arquivaria PDF de zero byte."""
        if isinstance(bruto, str):  # alguns drivers serializam o retorno
            try:
                bruto = json.loads(bruto)
            except ValueError:
                raise TransienteError("retorno do fetch não é objeto") from None
        if not isinstance(bruto, Mapping):
            raise TransienteError("retorno do fetch não é objeto")
        if not bruto.get("ok"):
            # `AbortError` é o timeout do AbortController; ambos são transientes.
            raise TransienteError(f"fetch falhou na página: {bruto.get('erro')!r}")
        status = bruto.get("status")
        if not isinstance(status, int):
            raise TransienteError("fetch sem status inteiro")
        if status == 0:
            # `redirect: 'manual'` produz resposta opaca: status 0, corpo vazio.
            # Tratar como sucesso vazio esconderia um redirect do adapter.
            raise PermanenteError("resposta opaca (redirect manual)")
        try:
            corpo = base64.b64decode(bruto.get("corpoB64") or "", validate=True)
        except (binascii.Error, ValueError):
            raise TransienteError("corpo do fetch não é base64 válido") from None
        cabecalhos = bruto.get("headers") or {}
        return Resposta(
            status=status,
            corpo=corpo,
            headers={str(k): str(v) for k, v in dict(cabecalhos).items()},
        )

    async def fetch_bytes(
        self,
        session: Session,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> bytes:
        """Binário. Confere o status **antes** de devolver bytes: uma página de erro
        do WAF é `bytes` válido e viraria PDF corrompido no storage.

        Mesma tradução de status do `HttpxTransport`, de propósito — o adapter não
        deve mudar de comportamento ao trocar de transporte.
        """
        resposta = await self.request(
            session, "GET", url, headers=headers, timeout=timeout
        )
        if resposta.ok:
            return resposta.corpo
        if resposta.status == 401:
            raise SessaoExpiradaError("sessão rejeitada (401)")
        if resposta.status == 429 or resposta.status >= 500:
            raise TransienteError(f"status {resposta.status}")
        # 403 e 404 param aqui de propósito. 403 pode ser sigilo, WAF, rate limit ou
        # falta de permissão; 404 pode ser peça inexistente ou URL errada. O
        # transporte não tem evidência para escolher — quem conhece o tribunal
        # traduz para SigiloError/InexistenteError, e nunca este módulo.
        raise PermanenteError(f"status {resposta.status}")
