"""Contratos do trt-extractor. Interfaces apenas — nenhuma implementação aqui.

Camadas, de cima para baixo:

    TribunalAdapter   o QUE fazer   (authenticate, list_documents, request_download,
                                     poll_download, fetch_artifact)
         usa
    Transport         o COMO falar  (httpx OU fetch de dentro da página autenticada)
         carrega
    Session           QUEM é        (token, cookies, validade, credencial de origem)

A separação `Transport` existe porque ainda não sabemos se o volume roda em httpx ou
dentro de um browser (hipótese H2, docs/arquitetura.md §4). Sem ela, essa decisão
vazaria para todos os adapters. Ver docs/decisions/002.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Vocabulário
# ---------------------------------------------------------------------------


class TipoDocumento(str, Enum):  # noqa: UP042
    """As cinco classes-alvo. `OUTRO` é o que o classificador rejeita."""

    PETICAO_INICIAL = "peticao_inicial"
    ACORDAO = "acordao"
    SENTENCA = "sentenca"
    ACORDO = "acordo"
    LAUDO_PERICIA = "laudo_pericia"
    OUTRO = "outro"


class Grau(str, Enum):  # noqa: UP042
    PRIMEIRO = "1"
    SEGUNDO = "2"
    # TST/instância extraordinária entra como `SUPERIOR` para não colidir com o
    # par (numero_cnj, grau) da chave de idempotência.
    SUPERIOR = "S"


class EstadoJob(str, Enum):  # noqa: UP042
    """Máquina de estados de `(numero_cnj, grau, tipo_documento)`.

    Terminais: ARQUIVADO, SIGILOSO, INEXISTENTE, FALHA_PERMANENTE.
    SIGILOSO e INEXISTENTE são resultados legítimos, não falhas — não entram na
    métrica de erro e nunca sofrem retry.
    """

    PENDENTE = "PENDENTE"
    SUBMETIDO = "SUBMETIDO"
    GERANDO = "GERANDO"
    BAIXADO = "BAIXADO"
    CLASSIFICADO = "CLASSIFICADO"
    ARQUIVADO = "ARQUIVADO"
    FALHA_TRANSIENTE = "FALHA_TRANSIENTE"
    SIGILOSO = "SIGILOSO"
    INEXISTENTE = "INEXISTENTE"
    FALHA_PERMANENTE = "FALHA_PERMANENTE"


class Via(str, Enum):  # noqa: UP042
    """Via de aquisição. Ordem de preferência decrescente.

    A ordem difere do briefing: `PDPJ_API` é nacional e antecede o MNI, que é por
    tribunal. Justificativa em docs/arquitetura.md §2 (D1).
    """

    PDPJ_API = "pdpj_api"  # 0 — nacional, api/v2
    MNI_SOAP = "mni_soap"  # 1 — por tribunal
    AUTOS_FILTRADO = "autos_filtrado"  # 2 — "Download autos" com filtro de tipo
    DOC_INDIVIDUAL = "doc_individual"  # 3 — peça a peça
    BROWSER = "browser"  # 4 — Playwright no navegador oficial
    LEGADO = "legado"  # 5 — visualizadores legados (VDOC etc.)


# ---------------------------------------------------------------------------
# Erros
# ---------------------------------------------------------------------------


class ExtractorError(Exception):
    """Base. Nunca levantada diretamente."""


class TransienteError(ExtractorError):
    """Vale retry com backoff: 429, 5xx, timeout, indisponibilidade programada."""


class PermanenteError(ExtractorError):
    """Não vale retry. Vai para dead-letter e revisão humana."""


class SigiloError(PermanenteError):
    """Segredo de justiça. Estado terminal legítimo — não é falha.

    Existe como exceção separada para que o orquestrador a converta em
    `EstadoJob.SIGILOSO` sem poluir a métrica de erro.
    """


class InexistenteError(PermanenteError):
    """O processo não tem essa peça. Terminal legítimo, não é falha."""


class SessaoExpiradaError(TransienteError):
    """Sessão inválida ou expirada. O pool deve renovar e o job repetir."""


class BloqueioError(TransienteError):
    """WAF, rate limit ou circuit breaker aberto para este tribunal."""


# ---------------------------------------------------------------------------
# Identidade e sessão
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Credencial:
    """Origem de uma sessão. Nunca carrega chave privada nem senha.

    `certificado_thumbprint` referencia o certificado no repositório do SO
    (MSCAPI no Windows); o material criptográfico não passa por este processo.
    """

    id: str
    cpf: str
    certificado_thumbprint: str | None = None
    certificado_expira_em: datetime | None = None
    rotulo: str = ""

    def __repr__(self) -> str:  # evita CPF em log/traceback
        return f"Credencial(id={self.id!r}, rotulo={self.rotulo!r})"


@dataclass(frozen=True, slots=True)
class Session:
    """Sessão autenticada. Opaca para o adapter — quem a usa é o Transport."""

    credencial: Credencial
    tribunal: str
    token: str | None
    cookies: Mapping[str, str] = field(default_factory=dict)
    expira_em: datetime | None = None
    # Handle do contexto de browser, quando o transporte é in-page fetch.
    contexto_browser: Any | None = None

    def __repr__(self) -> str:  # nunca vazar token
        return (
            f"Session(tribunal={self.tribunal!r}, "
            f"credencial={self.credencial.id!r}, expira_em={self.expira_em!r})"
        )


# ---------------------------------------------------------------------------
# Transporte
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Resposta:
    status: int
    corpo: bytes
    headers: Mapping[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


@runtime_checkable
class Transport(Protocol):
    """Como as requisições saem. Duas implementações previstas:

    - `HttpxTransport`        — cliente HTTP normal, assíncrono, paralelizável.
    - `InPageFetchTransport`  — executa `fetch` dentro da página autenticada,
                                herdando cookies de load balancer e a impressão
                                TLS/HTTP2 do browser.

    Qual usar por tribunal vem de `capabilities.yaml`, medido (H2), não hardcoded.
    """

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
    ) -> Resposta: ...

    async def fetch_bytes(
        self,
        session: Session,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> bytes:
        """Busca binário. Separado de `request` porque o caminho in-page precisa
        serializar bytes de volta do JS (base64) em vez de devolver o corpo cru."""
        ...


# ---------------------------------------------------------------------------
# Documento e download
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DocumentoRef:
    """Referência a um documento, antes de baixá-lo.

    `id_origem` é o identificador no sistema do tribunal — não é adivinhável, tem
    que vir de `list_documents`.
    """

    id_origem: str
    numero_cnj: str
    grau: Grau
    titulo: str | None = None
    # `tipoDocumento` cru do PJe. Preenchido de forma inconsistente entre
    # tribunais — é a primeira camada do classificador, nunca a única.
    tipo_pje: str | None = None
    juntado_em: datetime | None = None
    # Posição na sequência de juntada. Sinal mais forte para petição inicial.
    sequencia: int | None = None
    polo_juntada: str | None = None
    tamanho_bytes: int | None = None
    href_binario: str | None = None
    sigiloso: bool = False


@dataclass(frozen=True, slots=True)
class PedidoDownload:
    """Handle devolvido por `request_download`, consumido por `poll_download`.

    Opaco por design: no MNI o download é síncrono e isto vem já resolvido; na via
    de autos é um job na Área de Download com id do tribunal.
    """

    id_pedido: str
    tribunal: str
    numero_cnj: str
    grau: Grau
    via: Via
    tipos_solicitados: tuple[TipoDocumento, ...] = ()
    submetido_em: datetime | None = None
    opaco: Mapping[str, Any] = field(default_factory=dict)


class StatusDownload(str, Enum):  # noqa: UP042
    GERANDO = "gerando"
    PRONTO = "pronto"
    FALHOU = "falhou"


@dataclass(frozen=True, slots=True)
class ResultadoPoll:
    status: StatusDownload
    url_artefato: str | None = None
    # Sugestão do tribunal para a próxima consulta, quando informada.
    tentar_em_segundos: float | None = None
    detalhe: str | None = None


@dataclass(frozen=True, slots=True)
class Artefato:
    """Binário baixado, antes de split/classificação."""

    conteudo: bytes
    sha256: str
    content_type: str | None = None
    nome_sugerido: str | None = None
    # True quando é o PDF consolidado dos autos e ainda precisa de split.
    consolidado: bool = False


# ---------------------------------------------------------------------------
# Adapter de tribunal
# ---------------------------------------------------------------------------


@runtime_checkable
class TribunalAdapter(Protocol):
    """Uma implementação por tribunal (ou uma genérica + overrides).

    Contrato de erro, válido para todas as operações:

    - `TransienteError` (e subclasses) ⇒ retry com backoff pelo orquestrador.
    - `SigiloError` / `InexistenteError` ⇒ estado terminal legítimo, sem retry,
      fora da métrica de falha.
    - `PermanenteError` ⇒ dead-letter.

    O adapter **não** decide rate limit, retry, circuit breaker nem escolha de via.
    Isso é do orquestrador, que lê `capabilities.yaml`. O adapter só sabe falar com
    o tribunal.
    """

    #: Sigla do tribunal, ex. "TRT2". Deve casar com a chave em capabilities.yaml.
    tribunal: str
    #: Vias que esta implementação sabe operar, em ordem de preferência.
    vias_suportadas: tuple[Via, ...]

    async def authenticate(self, credencial: Credencial) -> Session:
        """Emite uma sessão autenticada.

        Caminho esperado: certificado A1 → SSO Keycloak → token + cookies. O
        certificado só entra aqui; todo o volume depois roda sobre a `Session`.

        Levanta `PermanenteError` se a credencial não tem acesso ao tribunal.
        """
        ...

    async def list_documents(
        self,
        session: Session,
        numero_cnj: str,
        grau: Grau,
        *,
        tipos: Iterable[TipoDocumento] | None = None,
    ) -> list[DocumentoRef]:
        """Lista os documentos do processo, sem baixá-los.

        `tipos` é uma dica: quando o tribunal aceita filtro server-side, aplica lá;
        senão filtra localmente. Documentos em segredo devem vir na lista com
        `sigiloso=True`, não omitidos — a ausência é indistinguível de inexistência
        e o job precisa dessa diferença para escolher entre SIGILOSO e INEXISTENTE.

        Levanta `InexistenteError` se o processo não existe naquele grau.
        """
        ...

    async def request_download(
        self,
        session: Session,
        numero_cnj: str,
        grau: Grau,
        tipos: Iterable[TipoDocumento],
        *,
        documentos: Iterable[DocumentoRef] | None = None,
    ) -> PedidoDownload:
        """Pede o download, filtrado por tipo. Não bloqueia.

        **Sempre filtrar por tipo.** Nunca pedir autos integrais para filtrar depois:
        corta 70-90% de volume, de tempo de geração e de pegada de tráfego.

        Quando a via for síncrona (MNI, ou API que devolve binário direto), devolve
        um `PedidoDownload` já resolvido — `poll_download` retorna PRONTO na
        primeira chamada. O orquestrador não precisa saber a diferença.
        """
        ...

    async def poll_download(
        self, session: Session, pedido: PedidoDownload
    ) -> ResultadoPoll:
        """Consulta se o artefato ficou pronto. Não bloqueia, não faz sleep.

        Backoff, deadline e dead-letter são do orquestrador. Este método é uma
        leitura só. Se o tribunal informar tempo estimado, devolve em
        `tentar_em_segundos`.
        """
        ...

    async def fetch_artifact(
        self, session: Session, pedido: PedidoDownload, resultado: ResultadoPoll
    ) -> Artefato:
        """Baixa o binário e devolve com `sha256` já calculado.

        Deve marcar `consolidado=True` quando o retorno for o PDF único dos autos,
        para que o pipeline saiba que ainda precisa de split.
        """
        ...


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


@runtime_checkable
class Storage(Protocol):
    """Content-addressed por sha256: uma cópia física, N referências lógicas.

    Resolve o dedup entre 1º e 2º grau sem lógica extra. `LocalCASStorage` cobre
    as fases 0-4; `S3Storage` entra na fase 5. Ver docs/arquitetura.md §2 (D5).
    """

    async def put(self, artefato: Artefato) -> str:
        """Grava e devolve o sha256. Idempotente: regravar o mesmo conteúdo é no-op."""
        ...

    async def get(self, sha256: str) -> bytes: ...

    async def exists(self, sha256: str) -> bool: ...


# ---------------------------------------------------------------------------
# Classificação
# ---------------------------------------------------------------------------


class MetodoClassificacao(str, Enum):  # noqa: UP042
    """Camadas do classificador, na ordem em que são tentadas."""

    TIPO_PJE = "tipo_pje"
    POSICAO_FLUXO = "posicao_fluxo"
    KEYWORDS = "keywords"
    LLM = "llm"
    HUMANO = "humano"


@dataclass(frozen=True, slots=True)
class Classificacao:
    """Toda classificação grava método e confiança. Abaixo do limiar configurado,
    o documento entra em fila de revisão humana amostral."""

    tipo: TipoDocumento
    metodo: MetodoClassificacao
    confianca: float
    detalhe: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class Classificador(Protocol):
    async def classificar(
        self, documento: DocumentoRef, texto: str | None
    ) -> Classificacao: ...
