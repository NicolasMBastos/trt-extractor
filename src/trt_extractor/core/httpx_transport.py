"""Transporte HTTP sobre httpx. Implementa o Protocol `Transport` de `contracts`.

Substrato de volume da Via 0 nacional. `http2=True` e um `User-Agent` de browser
são **requisito medido**, não cosmético: o WAF do PDPJ devolve 403 para HTTP/1.1 e
para requisição sem UA, e 200 com os dois (ADR 002, adendo 2; evidência em
`research/evidencia/pdpj-nacional-H1-CONFIRMADA-2026-09-03.md`).

Três propriedades que o resto do pipeline depende:

1. **Quem fala vem da `Session` de cada chamada, e só dela.** O transporte não
   guarda identidade: nem token, nem cookie, nem jar. Duas credenciais podem usar
   a mesma instância em paralelo sem se misturarem (ver `_JarSurdo`).
2. **Zero política.** Sem retry, sem backoff, sem circuit breaker, sem seguir
   redirect. Isso é do orquestrador, que lê `capabilities.yaml` (ADR 002).
3. **Mensagem de erro não carrega segredo.** Nem URL, nem header, nem token, nem
   `__cause__` do httpx — o traceback encadeado do httpx imprime a URL, e a URL
   carrega identificadores de processo e, em `userinfo`, credencial.

O que este módulo *não* decide: se um 403 é sigilo. Não há evidência aqui para
isso; `SigiloError` e `InexistenteError` nascem no adapter, que conhece o tribunal.
"""

from __future__ import annotations

from collections.abc import Mapping
from http.cookiejar import CookieJar
from types import TracebackType
from typing import Any

import httpx

from .contracts import (
    PermanenteError,
    Resposta,
    SessaoExpiradaError,
    Session,
    TransienteError,
)

# Constante e nunca rotacionada: identificação estável do cliente, não evasão.
# Rotacionar UA para escapar de detecção seria exatamente o que o projeto não faz.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)

TIMEOUT_PADRAO = 30.0


class _JarSurdo(CookieJar):
    """Cookie jar que não aprende nada.

    `httpx.AsyncClient` extrai `Set-Cookie` para o jar do client em *toda*
    resposta — inclusive quando a `Request` foi montada à mão. Num client
    compartilhado isso é duas coisas ruins ao mesmo tempo: segredo de sessão em
    repouso na instância, e cookie de uma `Session` podendo sair na chamada de
    outra (o caso concorrente é o pior: duas respostas escrevendo no mesmo jar).

    Aqui o jar fica permanentemente vazio nas duas pontas — não aprende e não
    tem o que aplicar. Todo `Cookie` enviado é montado por chamada, a partir da
    `Session`. Passar um `CookieJar` ao construtor é API pública do httpx
    (`Cookies.__init__` adota o jar recebido); os testes provam o efeito, de modo
    que uma mudança interna do httpx quebra o teste em vez de vazar em silêncio.
    """

    def extract_cookies(self, response: Any, request: Any) -> None:
        return None

    def set_cookie(self, cookie: Any) -> None:
        return None


def _timeout_valido(valor: float) -> float:
    """Timeout finito e positivo. `None` (esperar para sempre) não é opção: uma
    conexão pendurada segura um worker e um slot do pool indefinidamente."""
    if not 0 < valor < float("inf"):  # NaN cai aqui também
        raise ValueError(f"timeout deve ser finito e positivo, recebido {valor!r}")
    return float(valor)


class HttpxTransport:
    """`Transport` sobre um `httpx.AsyncClient` reusado.

    O client é reusado de propósito: pool de conexões e HTTP/2 só valem se ele
    sobrevive entre chamadas. Fechar com `aclose()` ou usar como context manager.

    `origem` é a única origem HTTPS para onde esta instância entrega uma `Session`.
    Uma instância por origem — é o que impede um redirect, um href do próprio
    tribunal ou um `id_origem` malicioso de fazer o Bearer sair para outro host.

    `transporte` injeta um `httpx.AsyncBaseTransport` (p.ex. `httpx.MockTransport`)
    para teste sem rede.
    """

    def __init__(
        self,
        origem: str,
        *,
        timeout: float = TIMEOUT_PADRAO,
        transporte: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._origem = httpx.URL(origem)
        if (
            self._origem.scheme != "https"
            or not self._origem.host
            or self._origem.userinfo
        ):
            raise ValueError("origem deve ser https, com host e sem userinfo")
        self._timeout = _timeout_valido(timeout)
        self._client = httpx.AsyncClient(
            http2=True,  # requisito medido (ADR 002 adendo 2)
            timeout=self._timeout,
            follow_redirects=False,  # 3xx volta como resposta; seguir é do adapter,
            # que revalida a origem antes de reenviar a Session
            trust_env=False,  # sem proxy, netrc nem CA vindos do ambiente
            cookies=_JarSurdo(),
            transport=transporte,
        )

    # -- montagem da requisição --------------------------------------------

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

    def _headers(
        self, session: Session, extras: Mapping[str, str] | None
    ) -> httpx.Headers:
        """Identidade só da `Session`, aplicada por último.

        `httpx.Headers` é case-insensitive: um `authorization` minúsculo vindo do
        chamador é substituído, não duplicado. Sessão sem token não manda
        `Authorization` nenhum, mesmo que o chamador tenha passado um.
        """
        headers = httpx.Headers()
        if extras:
            headers.update(extras)
        for nome, valor in (
            ("User-Agent", USER_AGENT),
            ("Authorization", f"Bearer {session.token}" if session.token else None),
            (
                "Cookie",
                "; ".join(f"{n}={v}" for n, v in session.cookies.items())
                if session.cookies
                else None,
            ),
        ):
            if valor is not None:
                headers[nome] = valor
            elif nome in headers:
                del headers[nome]
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
        alvo = self._alvo(url, params)
        metodo = metodo.upper()
        try:
            resposta = await self._client.request(
                metodo,
                alvo,
                headers=self._headers(session, headers),
                content=corpo,
                timeout=self._timeout if timeout is None else _timeout_valido(timeout),
            )
        except httpx.HTTPError as erro:
            # Sem `str(erro)` e sem `from erro`: a mensagem e o encadeamento do
            # httpx carregam a URL. O nome da classe basta para diagnosticar.
            raise TransienteError(
                f"falha de rede em {metodo}: {type(erro).__name__}"
            ) from None
        return Resposta(
            status=resposta.status_code,
            corpo=resposta.content,
            headers=dict(resposta.headers),
        )

    async def fetch_bytes(
        self,
        session: Session,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> bytes:
        """Binário. Confere o status **antes** de devolver bytes: uma página de
        erro do WAF é `bytes` válido e viraria PDF corrompido no storage."""
        resposta = await self.request(
            session, "GET", url, headers=headers, timeout=timeout
        )
        if resposta.ok:
            return resposta.corpo
        if resposta.status == 401:
            raise SessaoExpiradaError("sessão rejeitada (401)")
        if resposta.status == 429 or resposta.status >= 500:
            raise TransienteError(f"status {resposta.status}")
        # 403 e 404 param aqui de propósito. 403 pode ser sigilo, WAF, rate limit
        # ou falta de permissão; 404 pode ser peça inexistente ou URL errada. O
        # transporte não tem evidência para escolher — quem conhece o tribunal
        # traduz para SigiloError/InexistenteError, e nunca este módulo.
        raise PermanenteError(f"status {resposta.status}")

    # -- ciclo de vida ------------------------------------------------------

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> HttpxTransport:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()
