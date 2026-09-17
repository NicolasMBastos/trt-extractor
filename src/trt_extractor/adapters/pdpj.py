"""National PDPJ adapter. Unknown wire formats require explicit caller policy.

authenticate resolves an existing session; it never performs a handshake.
One request handle identifies one document. Poll exposes the resolved location;
fetch performs the single HTTP read, including generation/error interpretation.
tipo_pje preserves the national type code as a string. No text URL is inferred.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Awaitable, Callable, Iterable, Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from trt_extractor.core.contracts import (
    Artefato,
    BloqueioError,
    Credencial,
    DocumentoRef,
    Grau,
    InexistenteError,
    PedidoDownload,
    PermanenteError,
    Resposta,
    ResultadoPoll,
    SessaoExpiradaError,
    Session,
    SigiloError,
    StatusDownload,
    TipoDocumento,
    TransienteError,
    Transport,
    Via,
)

BASE_URL = "https://portaldeservicos.pdpj.jus.br/api/v2"
GrauMapper = Callable[[Mapping[str, Any]], Grau]
SessionProvider = Callable[[str, Credencial], Awaitable[Session]]
GenerationPredicate = Callable[[Mapping[str, Any]], bool]


class GeracaoPendenteError(TransienteError):
    """Caller-recognized generation response; caller owns retry and deadline."""

    def __init__(self, tentar_em_segundos: float | None = None) -> None:
        super().__init__("Geracao pendente segundo a politica configurada")
        self.tentar_em_segundos = tentar_em_segundos


def _cnj(numero: str) -> str:
    if re.fullmatch(r"[0-9]{20}", numero):
        numero = (
            f"{numero[:7]}-{numero[7:9]}.{numero[9:13]}."
            f"{numero[13]}.{numero[14:16]}.{numero[16:]}"
        )
    if not re.fullmatch(
        r"[0-9]{7}-[0-9]{2}\.[0-9]{4}\.[0-9]\.[0-9]{2}\.[0-9]{4}", numero
    ):
        raise PermanenteError("Formato CNJ invalido")
    return numero


def _objeto(valor: object) -> dict[str, Any]:
    if not isinstance(valor, dict):
        raise PermanenteError("Objeto PDPJ ausente ou invalido")
    return valor


def _sigilo(valor: object) -> bool:
    if (type(valor) is int and valor == 0) or valor == "PUBLICO":
        return False
    if (type(valor) is int and valor > 0) or valor == "SIGILOSO":
        return True
    raise PermanenteError("Nivel de sigilo ausente ou nao reconhecido; acesso suspenso")


def _retry_after(headers: Mapping[str, str]) -> float | None:
    """`Retry-After` em segundos, quando o tribunal informa.

    O formato de data HTTP e ignorado de proposito: converte-lo exigiria confiar no
    relogio do servidor, que nao foi medido. Sem numero valido, quem decide o intervalo
    e o orquestrador.
    """
    minusculo = {nome.lower(): valor for nome, valor in headers.items()}
    try:
        segundos = float(minusculo.get("retry-after", ""))
    except (TypeError, ValueError):
        return None
    return segundos if math.isfinite(segundos) and segundos >= 0 else None


def _status(resposta: Resposta) -> None:
    if resposta.status == 401:
        raise SessaoExpiradaError("Sessao recusada pelo PDPJ")
    if resposta.status in (403, 429):
        raise BloqueioError("PDPJ recusou a requisicao; nao alternar a via")
    if resposta.status == 404:
        raise InexistenteError("Recurso PDPJ inexistente")
    if resposta.status == 408 or 500 <= resposta.status < 600:
        raise TransienteError("PDPJ temporariamente indisponivel")
    if resposta.status == 206:
        raise TransienteError("Resposta parcial recusada")
    if resposta.status == 202:
        # 202 e "aceito", nao "pronto" — regra do HTTP, nao suposicao sobre o PDPJ.
        # O corpo de um 202 e intermediario: aceita-lo arquivaria como peca final algo
        # que o tribunal ainda nao declarou concluido. Vale para listagem e binario.
        raise GeracaoPendenteError(_retry_after(resposta.headers))
    if resposta.status != 200:
        raise PermanenteError("Status PDPJ inesperado")


def _json(corpo: bytes) -> dict[str, Any]:
    try:
        valor = json.loads(corpo)
    except (ValueError, UnicodeError):
        raise PermanenteError("JSON PDPJ invalido") from None
    return _objeto(valor)


def _processo_json(corpo: bytes) -> dict[str, Any]:
    """Como `_json`, mas para o endpoint de processo: medido ao vivo em 2026-09-17
    (docs/execucao/validacao-24-trts-2026-09-17.md) que o PDPJ nacional devolve uma
    lista JSON de um item, não um objeto solto. Lista de tamanho diferente de 1 é
    ambígua — melhor falhar alto que escolher um item sem critério."""
    try:
        valor = json.loads(corpo)
    except (ValueError, UnicodeError):
        raise PermanenteError("JSON PDPJ invalido") from None
    if isinstance(valor, list):
        if len(valor) != 1:
            raise PermanenteError("Lista de processos ambigua (esperado 1 item)")
        valor = valor[0]
    return _objeto(valor)


class PdpjAdapter:
    """Consumes sessions and transport; never chooses retry, storage or OCR policy."""

    vias_suportadas = (Via.PDPJ_API,)

    def __init__(
        self,
        transport: Transport,
        tribunal: str = "TRT4",
        *,
        grau_mapper: GrauMapper | None = None,
        session_provider: SessionProvider | None = None,
        tipos_por_codigo: Mapping[str, TipoDocumento] | None = None,
        geracao_pendente: GenerationPredicate | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not re.fullmatch(r"TRT(?:[1-9]|1[0-9]|2[0-4])", tribunal):
            raise ValueError("Tribunal invalido")
        self.tribunal = tribunal
        self._transport = transport
        self._grau_mapper = grau_mapper
        self._session_provider = session_provider
        self._tipos = dict(
            tipos_por_codigo
            if tipos_por_codigo is not None
            else {"202": TipoDocumento.PETICAO_INICIAL}
        )
        self._geracao = geracao_pendente
        self._clock = clock

    def _sessao(self, session: Session) -> None:
        if session.tribunal != self.tribunal:
            raise PermanenteError("Sessao pertence a outro tribunal")
        if not session.token and not session.cookies:
            raise SessaoExpiradaError("Sessao sem autenticacao")
        agora = self._clock()
        if (
            session.expira_em is None
            or session.expira_em.utcoffset() is None
            or agora.utcoffset() is None
            or session.expira_em <= agora
        ):
            raise SessaoExpiradaError("Sessao expirada ou validade nao comprovada")

    async def authenticate(self, credencial: Credencial) -> Session:
        if self._session_provider is None:
            raise SessaoExpiradaError("Sessao do handshake humano nao fornecida")
        session = await self._session_provider(self.tribunal, credencial)
        if session.credencial != credencial:
            raise PermanenteError("Provedor retornou outra credencial")
        self._sessao(session)
        return session

    def _url(self, href: str, numero_cnj: str) -> str:
        if href.startswith("/processos/"):
            href = BASE_URL + href
        try:
            parsed = urlsplit(href)
        except ValueError:
            raise PermanenteError("URL de documento invalida") from None
        base = urlsplit(BASE_URL)
        if (
            parsed.scheme != base.scheme
            or parsed.netloc != base.netloc
            or parsed.query
            or parsed.fragment
        ):
            raise PermanenteError("URL de documento fora da origem permitida")
        cnj = _cnj(numero_cnj)
        numeros = (cnj, re.sub(r"\D", "", cnj))
        if not any(
            re.fullmatch(
                rf"/api/v2/processos/{re.escape(numero)}/documentos/[A-Za-z0-9-]+/binario",
                parsed.path,
            )
            for numero in numeros
        ):
            raise PermanenteError("URL nao corresponde ao documento do processo")
        return href

    def _documento(self, valor: object, numero_cnj: str, grau: Grau) -> DocumentoRef:
        doc = _objeto(valor)
        sigiloso = _sigilo(doc.get("nivelSigilo"))
        origem = doc.get("idOrigem")
        if not isinstance(origem, str) or not origem:
            raise PermanenteError("Documento sem idOrigem")
        tipo = doc.get("tipo")
        tipo_obj = None if tipo is None else _objeto(tipo)
        codigo = None if tipo_obj is None else tipo_obj.get("codigo")
        if codigo is not None and (type(codigo) not in (int, str) or not str(codigo)):
            raise PermanenteError("Codigo de tipo invalido")
        # Medido ao vivo em 2026-09-17: o PDPJ nacional manda "tipo" sem "codigo"
        # nenhum (só "nome"/"idCodex"/"idOrigem") — o formato com "codigo" pode
        # existir em outro canal/tribunal, mas não é o que este processo real
        # devolveu. Sem "codigo", cai para o nome do tipo — melhor sinal disponível
        # do que nenhum, e quem decide o mapeamento nome->TipoDocumento é o
        # chamador (`tipos_por_codigo`), não este método.
        tipo_nome = None if tipo_obj is None else tipo_obj.get("nome")
        if tipo_nome is not None and not isinstance(tipo_nome, str):
            raise PermanenteError("Nome de tipo invalido")
        sequencia = doc.get("sequencia")
        if sequencia is not None and (type(sequencia) is not int or sequencia < 0):
            raise PermanenteError("Sequencia invalida")
        data = doc.get("dataHoraJuntada")
        juntado_em = None
        if data is not None:
            # Medido ao vivo em 2026-09-17: o PDPJ nacional manda datetime SEM
            # offset ("2026-09-01T00:24:36.704938"), nao só com offset como os
            # testes sintéticos assumiam. Exigir offset aqui rejeitava toda peça
            # real. `juntado_em` é sinal de ordenação/classificação, não usado em
            # comparação com relógio — naive serve.
            try:
                juntado_em = datetime.fromisoformat(data)
            except (TypeError, ValueError):
                raise PermanenteError("Data de juntada invalida") from None
        nome = doc.get("nome")
        href = doc.get("hrefBinario")
        if nome is not None and not isinstance(nome, str):
            raise PermanenteError("Nome de documento invalido")
        if href is not None and not isinstance(href, str):
            raise PermanenteError("hrefBinario invalido")
        return DocumentoRef(
            id_origem=origem,
            numero_cnj=numero_cnj,
            grau=grau,
            titulo=nome,
            tipo_pje=str(codigo) if codigo is not None else tipo_nome,
            juntado_em=juntado_em,
            sequencia=sequencia,
            href_binario=self._url(href, numero_cnj) if href else None,
            sigiloso=sigiloso,
        )

    async def list_documents(
        self,
        session: Session,
        numero_cnj: str,
        grau: Grau,
        *,
        tipos: Iterable[TipoDocumento] | None = None,
    ) -> list[DocumentoRef]:
        self._sessao(session)
        numero_cnj = _cnj(numero_cnj)
        if self._grau_mapper is None:
            raise PermanenteError(
                "Mapeamento de grau nao configurado; formato nao medido"
            )
        resposta = await self._transport.request(
            session, "GET", f"{BASE_URL}/processos/{numero_cnj}"
        )
        _status(resposta)
        processo = _processo_json(resposta.corpo)
        if "processo" in processo:
            processo = _objeto(processo["processo"])
        if _sigilo(processo.get("nivelSigilo")):
            raise SigiloError("Processo sigiloso")
        numero_resposta = processo.get("numeroProcesso")
        if not isinstance(numero_resposta, str) or _cnj(numero_resposta) != numero_cnj:
            raise PermanenteError("Resposta pertence a outro processo")
        if processo.get("siglaTribunal") != self.tribunal:
            raise PermanenteError("Resposta pertence a outro tribunal")
        atual = processo.get("tramitacaoAtual")
        candidatas = processo.get("tramitacoes", [])
        if not isinstance(candidatas, list):
            raise PermanenteError("Lista de tramitacoes invalida")
        candidatas = [atual, *candidatas] if atual is not None else candidatas
        encontrados: dict[str, DocumentoRef] = {}
        # Dono de cada binario. A rota e /documentos/{uuid}/binario e a evidencia H1
        # NAO diz se esse uuid e o idOrigem ou o idCodex (lacuna L14), entao exigir
        # igualdade com idOrigem seria inventar semantica. O que da para provar sem
        # medicao nova e mais fraco e suficiente: dois documentos distintos disputando
        # um mesmo binario so pode terminar com os mesmos bytes atribuidos a duas pecas.
        binarios: dict[str, str] = {}
        grau_encontrado = False
        for candidata in candidatas:
            tramitacao = _objeto(candidata)
            try:
                mapeado = self._grau_mapper(tramitacao)
            except (KeyError, ValueError, TypeError):
                raise PermanenteError(
                    "Grau nao reconhecido pela politica configurada"
                ) from None
            if not isinstance(mapeado, Grau):
                raise PermanenteError("Mapeador retornou grau invalido")
            if mapeado != grau:
                continue
            grau_encontrado = True
            documentos = tramitacao.get("documentos")
            if not isinstance(documentos, list):
                raise PermanenteError("Documentos da tramitacao indisponiveis no payload")
            for valor in documentos:
                doc = self._documento(valor, numero_cnj, grau)
                anterior = encontrados.get(doc.id_origem)
                if anterior is not None and anterior != doc:
                    raise PermanenteError(
                        "Referencias divergentes para o mesmo documento"
                    )
                if doc.href_binario is not None:
                    dono = binarios.setdefault(doc.href_binario, doc.id_origem)
                    if dono != doc.id_origem:
                        raise PermanenteError("Dois documentos disputam o mesmo binario")
                encontrados[doc.id_origem] = doc
        if not grau_encontrado:
            raise InexistenteError("Grau solicitado ausente")
        filtro = None if tipos is None else set(tipos)
        return [
            doc
            for doc in encontrados.values()
            if filtro is None
            or doc.sigiloso
            or self._tipos.get(doc.tipo_pje or "", TipoDocumento.OUTRO) in filtro
        ]

    async def request_download(
        self,
        session: Session,
        numero_cnj: str,
        grau: Grau,
        tipos: Iterable[TipoDocumento],
        *,
        documentos: Iterable[DocumentoRef] | None = None,
    ) -> PedidoDownload:
        self._sessao(session)
        numero_cnj = _cnj(numero_cnj)
        tipos = tuple(tipos)
        if not tipos or any(not isinstance(tipo, TipoDocumento) for tipo in tipos):
            raise PermanenteError("Selecione tipos validos antes do download")
        docs = (
            list(documentos)
            if documentos is not None
            else await self.list_documents(session, numero_cnj, grau, tipos=tipos)
        )
        for doc in docs:
            if doc.numero_cnj != numero_cnj or doc.grau != grau:
                raise PermanenteError("Documento pertence a outro processo ou grau")
        alvos = [
            doc
            for doc in docs
            if self._tipos.get(doc.tipo_pje or "", TipoDocumento.OUTRO) in tipos
        ]
        if not alvos:
            if any(doc.sigiloso and doc.tipo_pje not in self._tipos for doc in docs):
                raise PermanenteError("Tipo de documento restrito nao identificado")
            raise InexistenteError("Nenhum documento do tipo solicitado")
        if len(alvos) != 1:
            raise PermanenteError(
                "Selecione um documento por pedido; nao ha lote implicito"
            )
        doc = alvos[0]
        if doc.sigiloso:
            raise SigiloError("Documento sigiloso")
        if not doc.href_binario:
            raise PermanenteError("Documento sem hrefBinario")
        return PedidoDownload(
            id_pedido=doc.id_origem,
            tribunal=self.tribunal,
            numero_cnj=numero_cnj,
            grau=grau,
            via=Via.PDPJ_API,
            tipos_solicitados=tipos,
            submetido_em=self._clock(),
            opaco={
                "href_binario": self._url(doc.href_binario, numero_cnj),
                "credencial_id": session.credencial.id,
            },
        )

    def _pedido(self, session: Session, pedido: PedidoDownload) -> str:
        self._sessao(session)
        if pedido.tribunal != self.tribunal or pedido.via != Via.PDPJ_API:
            raise PermanenteError("Pedido pertence a outro tribunal ou via")
        if pedido.opaco.get("credencial_id") != session.credencial.id:
            raise PermanenteError("Pedido pertence a outra credencial")
        href = pedido.opaco.get("href_binario")
        if not isinstance(href, str):
            raise PermanenteError("Pedido sem hrefBinario")
        return self._url(href, pedido.numero_cnj)

    async def poll_download(
        self, session: Session, pedido: PedidoDownload
    ) -> ResultadoPoll:
        return ResultadoPoll(
            status=StatusDownload.PRONTO, url_artefato=self._pedido(session, pedido)
        )

    async def fetch_artifact(
        self, session: Session, pedido: PedidoDownload, resultado: ResultadoPoll
    ) -> Artefato:
        url = self._pedido(session, pedido)
        if resultado.status != StatusDownload.PRONTO or resultado.url_artefato != url:
            raise PermanenteError("Resultado nao corresponde ao pedido pronto")
        resposta = await self._transport.request(session, "GET", url)
        _status(resposta)
        headers = {nome.lower(): valor for nome, valor in resposta.headers.items()}
        corpo = resposta.corpo
        if not corpo or "content-range" in headers:
            raise TransienteError("Binario vazio ou parcial")
        if "content-length" in headers and "content-encoding" not in headers:
            try:
                tamanho = int(headers["content-length"])
            except ValueError:
                raise PermanenteError("Content-Length invalido") from None
            if tamanho != len(corpo):
                raise TransienteError("Comprimento de binario divergente")
        if corpo.startswith(b"%PDF-"):
            if not corpo.rstrip().endswith(b"%%EOF"):
                raise TransienteError("PDF possivelmente truncado")
            return Artefato(
                conteudo=corpo,
                sha256=hashlib.sha256(corpo).hexdigest(),
                content_type="application/pdf",
                consolidado=False,
            )
        if corpo.lstrip().startswith(b"{"):
            valor = _json(corpo)
            if self._geracao is not None and self._geracao(valor):
                raise GeracaoPendenteError(_retry_after(headers))
            raise PermanenteError("JSON de binario nao reconhecido; L2 nao confirmado")
        raise PermanenteError("Conteudo de binario inesperado")
