"""Synthetic wire policies; these fixtures are not live PDPJ recordings."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from trt_extractor.adapters.pdpj import BASE_URL, GeracaoPendenteError, PdpjAdapter
from trt_extractor.core.contracts import (
    BloqueioError,
    Credencial,
    DocumentoRef,
    Grau,
    InexistenteError,
    PermanenteError,
    Resposta,
    SessaoExpiradaError,
    Session,
    SigiloError,
    TipoDocumento,
    TransienteError,
    TribunalAdapter,
)
from trt_extractor.storage.local_cas import LocalCASStorage

CNJ = "0000000-00.2026.5.04.0000"
NOW = datetime(2026, 9, 8, tzinfo=UTC)
PDF = b"%PDF-1.4\nsynthetic transport fixture\n%%EOF\n"
INITIAL = (TipoDocumento.PETICAO_INICIAL,)
SESSION = Session(
    Credencial("synthetic", ""),
    "TRT4",
    "synthetic-not-jwt",
    expira_em=NOW + timedelta(hours=1),
)


class FakeTransport:
    def __init__(self, *responses: Resposta | Exception) -> None:
        self.responses = list(responses)
        self.calls: list[str] = []

    async def request(
        self, session: Session, metodo: str, url: str, **kwargs: Any
    ) -> Resposta:
        self.calls.append(url)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def fetch_bytes(self, *args: Any, **kwargs: Any) -> bytes:
        raise AssertionError("Adapter needs status and headers, not unchecked bytes")


def wire_document(**overrides: Any) -> dict[str, Any]:
    # O href acompanha o `idOrigem` por padrão: um payload em que dois documentos
    # compartilham um binário é ambíguo, e o adapter recusa. Quem quiser testar essa
    # ambiguidade passa `hrefBinario` explicitamente — é o que a faz aparecer no teste.
    id_origem = overrides.get("idOrigem", "synthetic-doc-1")
    return {
        "idOrigem": id_origem,
        "nome": "Peticao Inicial.pdf",
        "nivelSigilo": "PUBLICO",
        "tipo": {"codigo": 202},
        "sequencia": 1,
        "dataHoraJuntada": "2026-09-08T10:00:00-03:00",
        "hrefBinario": f"/processos/{CNJ}/documentos/{id_origem}/binario",
        **overrides,
    }


def process(*documents: dict[str, Any], **overrides: Any) -> Resposta:
    payload = {
        "nivelSigilo": 0,
        "numeroProcesso": CNJ,
        "siglaTribunal": "TRT4",
        "tramitacaoAtual": {"grau": "1", "documentos": list(documents)},
        **overrides,
    }
    return Resposta(200, json.dumps(payload).encode())


def adapter(transport: FakeTransport, **kwargs: Any) -> PdpjAdapter:
    return PdpjAdapter(
        transport,
        grau_mapper=lambda tramite: Grau(tramite["grau"]),
        clock=lambda: NOW,
        **kwargs,
    )


def reference(**overrides: Any) -> DocumentoRef:
    return DocumentoRef(
        **{
            "id_origem": "synthetic-doc-1",
            "numero_cnj": CNJ,
            "grau": Grau.PRIMEIRO,
            "tipo_pje": "202",
            "href_binario": (
                f"{BASE_URL}/processos/{CNJ}/documentos/synthetic-doc-1/binario"
            ),
            **overrides,
        }
    )


async def download(subject: PdpjAdapter) -> Any:
    pedido = await subject.request_download(
        SESSION, CNJ, Grau.PRIMEIRO, INITIAL, documentos=[reference()]
    )
    poll = await subject.poll_download(SESSION, pedido)
    return await subject.fetch_artifact(SESSION, pedido, poll)


async def test_maps_public_and_restricted_without_dropping_refs() -> None:
    transport = FakeTransport(
        process(
            wire_document(),
            wire_document(
                idOrigem="synthetic-restricted", nivelSigilo="SIGILOSO", sequencia=2
            ),
        )
    )
    subject = adapter(transport)
    assert isinstance(subject, TribunalAdapter)
    docs = await subject.list_documents(SESSION, CNJ, Grau.PRIMEIRO)
    assert len(docs) == 2
    assert docs[0].tipo_pje == "202"
    assert docs[0].sequencia == 1
    assert docs[0].juntado_em.utcoffset() == timedelta(hours=-3)
    assert docs[1].sigiloso
    assert transport.calls == [f"{BASE_URL}/processos/{CNJ}"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"tipo": None},
        {"tipo": {}},
        {"tipo": {"codigo": 999999}},
        {"sequencia": None},
        {"hrefBinario": None},
    ],
)
async def test_optional_and_unknown_metadata(overrides: dict[str, Any]) -> None:
    subject = adapter(FakeTransport(process(wire_document(**overrides))))
    docs = await subject.list_documents(SESSION, CNJ, Grau.PRIMEIRO)
    assert len(docs) == 1
    if overrides.get("tipo") == {"codigo": 999999}:
        assert docs[0].tipo_pje == "999999"


@pytest.mark.parametrize("value", [None, False, True, "UNKNOWN", "", -1, [], {}])
async def test_unknown_sigilo_is_not_a_terminal_classification(value: Any) -> None:
    subject = adapter(FakeTransport(process(wire_document(nivelSigilo=value))))
    with pytest.raises(PermanenteError) as error:
        await subject.list_documents(SESSION, CNJ, Grau.PRIMEIRO)
    assert not isinstance(error.value, SigiloError)


async def test_process_sigilo_stops_after_listing() -> None:
    transport = FakeTransport(process(nivelSigilo=1))
    with pytest.raises(SigiloError):
        await adapter(transport).list_documents(SESSION, CNJ, Grau.PRIMEIRO)
    assert len(transport.calls) == 1


async def test_empty_process_and_missing_grade_are_distinct() -> None:
    subject = adapter(FakeTransport(process(), process()))
    assert await subject.list_documents(SESSION, CNJ, Grau.PRIMEIRO) == []
    with pytest.raises(InexistenteError):
        await subject.list_documents(SESSION, CNJ, Grau.SEGUNDO)


async def test_selects_requested_grade_without_current_grade_assumption() -> None:
    transport = FakeTransport(
        process(
            wire_document(),
            tramitacoes=[{"grau": "2", "documentos": [wire_document(idOrigem="appeal")]}],
        )
    )
    docs = await adapter(transport).list_documents(SESSION, CNJ, Grau.SEGUNDO)
    assert [doc.id_origem for doc in docs] == ["appeal"]
    assert docs[0].grau == Grau.SEGUNDO


async def test_no_unmeasured_grade_default() -> None:
    transport = FakeTransport()
    subject = PdpjAdapter(transport, clock=lambda: NOW)
    with pytest.raises(PermanenteError, match="Mapeamento"):
        await subject.list_documents(SESSION, CNJ, Grau.PRIMEIRO)
    assert not transport.calls


@pytest.mark.parametrize(
    "changes",
    [
        {"numeroProcesso": "0000001-00.2026.5.04.0000"},
        {"siglaTribunal": "TRT2"},
        {"tramitacaoAtual": {"grau": "1"}},
        {"tramitacoes": {}},
    ],
)
async def test_rejects_inconsistent_process(changes: dict[str, Any]) -> None:
    with pytest.raises(PermanenteError):
        await adapter(FakeTransport(process(**changes))).list_documents(
            SESSION, CNJ, Grau.PRIMEIRO
        )


@pytest.mark.parametrize(
    "status,error",
    [
        (401, SessaoExpiradaError),
        (403, BloqueioError),
        (404, InexistenteError),
        (429, BloqueioError),
        (408, TransienteError),
        (500, TransienteError),
        (502, TransienteError),
        (503, TransienteError),
        (206, TransienteError),
        (302, PermanenteError),
    ],
)
async def test_http_status_is_not_success(status: int, error: type[Exception]) -> None:
    with pytest.raises(error):
        await adapter(FakeTransport(Resposta(status, b"{}"))).list_documents(
            SESSION, CNJ, Grau.PRIMEIRO
        )


async def test_timeout_propagates_without_retry() -> None:
    transport = FakeTransport(TransienteError("timeout"))
    with pytest.raises(TransienteError):
        await adapter(transport).list_documents(SESSION, CNJ, Grau.PRIMEIRO)
    assert len(transport.calls) == 1


@pytest.mark.parametrize(
    "docs,error",
    [
        ([], InexistenteError),
        ([reference(sigiloso=True)], SigiloError),
        ([reference(href_binario=None)], PermanenteError),
        ([reference(), reference(id_origem="second")], PermanenteError),
        ([reference(grau=Grau.SEGUNDO)], PermanenteError),
        ([reference(tipo_pje="999999")], InexistenteError),
    ],
)
async def test_explicit_selection_guards(
    docs: list[DocumentoRef], error: type[Exception]
) -> None:
    transport = FakeTransport()
    with pytest.raises(error):
        await adapter(transport).request_download(
            SESSION, CNJ, Grau.PRIMEIRO, INITIAL, documentos=docs
        )
    assert not transport.calls


@pytest.mark.parametrize(
    "href",
    [
        "https://other.invalid/document",
        "https://user@portaldeservicos.pdpj.jus.br/api/v2/processos/a",
        f"/processos/{CNJ}/documentos/a/binario?token=synthetic",
        f"/processos/{CNJ}/documentos/../binario",
        "/processos/0000001-00.2026.5.04.0000/documentos/a/binario",
        "//other.invalid/a",
    ],
)
async def test_untrusted_href_never_reaches_transport(href: str) -> None:
    transport = FakeTransport()
    with pytest.raises(PermanenteError):
        await adapter(transport).request_download(
            SESSION,
            CNJ,
            Grau.PRIMEIRO,
            INITIAL,
            documentos=[reference(href_binario=href)],
        )
    assert not transport.calls


@pytest.mark.parametrize(
    "content_type", ["application/pdf", "application/json", "text/html"]
)
async def test_pdf_bytes_win_over_misleading_content_type(content_type: str) -> None:
    transport = FakeTransport(Resposta(200, PDF, {"Content-Type": content_type}))
    artifact = await download(adapter(transport))
    assert artifact.conteudo == PDF
    assert artifact.sha256 == hashlib.sha256(PDF).hexdigest()
    assert artifact.content_type == "application/pdf"
    assert not artifact.consolidado
    assert len(transport.calls) == 1


@pytest.mark.parametrize(
    "body,headers,error",
    [
        (b"", {}, TransienteError),
        (b"%PDF-1.4\ntruncated", {}, TransienteError),
        (PDF, {"Content-Range": "bytes 0-5/100"}, TransienteError),
        (PDF, {"Content-Length": "9999"}, TransienteError),
        (PDF, {"Content-Length": "bad"}, PermanenteError),
        (b'{"codigo":"unknown"}', {"Content-Type": "application/pdf"}, PermanenteError),
        (b"<html>denied</html>", {"Content-Type": "application/pdf"}, PermanenteError),
        (b"{broken", {}, PermanenteError),
    ],
)
async def test_never_stores_non_pdf(
    body: bytes, headers: dict[str, str], error: type[Exception]
) -> None:
    with pytest.raises(error):
        await download(adapter(FakeTransport(Resposta(200, body, headers))))


async def test_explicit_synthetic_generation_policy_and_later_pdf() -> None:
    transport = FakeTransport(
        Resposta(200, b'{"synthetic_state":"pending"}', {"Retry-After": "3"}),
        Resposta(200, PDF),
    )
    subject = adapter(
        transport, geracao_pendente=lambda data: data.get("synthetic_state") == "pending"
    )
    with pytest.raises(GeracaoPendenteError) as error:
        await download(subject)
    assert error.value.tentar_em_segundos == 3
    assert len(transport.calls) == 1
    assert (await download(subject)).conteudo == PDF
    assert len(transport.calls) == 2


@pytest.mark.parametrize(
    "session",
    [
        replace(SESSION, expira_em=None),
        replace(SESSION, expira_em=NOW),
        replace(SESSION, token=None),
    ],
)
async def test_rejects_unusable_session_before_request(session: Session) -> None:
    transport = FakeTransport()
    with pytest.raises(SessaoExpiradaError):
        await adapter(transport).list_documents(session, CNJ, Grau.PRIMEIRO)
    assert not transport.calls


async def test_authentication_resolves_existing_session_only() -> None:
    async def provider(tribunal: str, credencial: Credencial) -> Session:
        assert tribunal == "TRT4"
        assert credencial == SESSION.credencial
        return SESSION

    subject = adapter(FakeTransport(), session_provider=provider)
    assert await subject.authenticate(SESSION.credencial) == SESSION
    with pytest.raises(SessaoExpiradaError):
        await adapter(FakeTransport()).authenticate(SESSION.credencial)


async def test_download_to_cas_is_repeatable(tmp_path: Any) -> None:
    transport = FakeTransport(Resposta(200, PDF), Resposta(200, PDF))
    subject = adapter(transport)
    storage = LocalCASStorage(tmp_path)
    first = await storage.put(await download(subject))
    second = await storage.put(await download(subject))
    assert first == second
    assert await storage.get(first) == PDF
    assert len([path for path in tmp_path.rglob("*") if path.is_file()]) == 1


async def test_unknown_grade_does_not_become_inexistente() -> None:
    subject = adapter(FakeTransport(process(tramitacaoAtual={"grau": "unknown"})))
    with pytest.raises(PermanenteError) as error:
        await subject.list_documents(SESSION, CNJ, Grau.PRIMEIRO)
    assert not isinstance(error.value, InexistenteError)


async def test_request_cannot_change_credential() -> None:
    transport = FakeTransport()
    subject = adapter(transport)
    pedido = await subject.request_download(
        SESSION, CNJ, Grau.PRIMEIRO, INITIAL, documentos=[reference()]
    )
    other = replace(SESSION, credencial=Credencial("other", ""))
    with pytest.raises(PermanenteError, match="outra credencial"):
        await subject.poll_download(other, pedido)
    assert not transport.calls


async def test_restricted_unknown_type_does_not_become_inexistente() -> None:
    with pytest.raises(PermanenteError) as error:
        await adapter(FakeTransport()).request_download(
            SESSION,
            CNJ,
            Grau.PRIMEIRO,
            INITIAL,
            documentos=[reference(sigiloso=True, tipo_pje=None)],
        )
    assert not isinstance(error.value, InexistenteError)


# -- achados da revisão adversarial L11 (docs/execucao/revisao-adversarial-2026-09-14.md)


async def test_accepted_status_is_never_a_ready_binary() -> None:
    """`202` é aceito-mas-não-concluído, mesmo quando o corpo parece um PDF.

    Achado 2 da revisão L11. Arquivar a resposta de um `202` publicaria um artefato
    que o tribunal ainda não declarou pronto, e L2 (semântica da geração) segue não
    confirmada. A regra vem do HTTP, não de uma suposição sobre o PDPJ: por isso ela
    não depende do predicado `geracao_pendente`, que existe para o corpo JSON.
    """
    transport = FakeTransport(Resposta(202, PDF, {"Retry-After": "7"}))
    with pytest.raises(GeracaoPendenteError) as error:
        await download(adapter(transport))
    assert error.value.tentar_em_segundos == 7
    assert len(transport.calls) == 1


async def test_accepted_status_is_not_a_document_listing() -> None:
    """Mesma regra na listagem: `202` não é corpo final, então não vira documento."""
    transport = FakeTransport(Resposta(202, process().corpo))
    with pytest.raises(GeracaoPendenteError):
        await adapter(transport).list_documents(SESSION, CNJ, Grau.PRIMEIRO)


async def test_rejects_two_documents_sharing_one_binary_url() -> None:
    """Dois `idOrigem` distintos apontando para o mesmo binário é ambiguidade.

    Achado 1 da revisão L11, na parte que é provável sem medição nova. Não dá para
    exigir que o id da URL seja igual ao `idOrigem` — a evidência H1 registra a rota
    como `/documentos/{uuid}/binario` e **não** diz qual id é esse uuid (ver L14).
    Mas dois documentos distintos disputando um binário só pode acabar em atribuir
    os mesmos bytes a duas peças, então isso para aqui.
    """
    transport = FakeTransport(
        process(
            wire_document(),
            wire_document(
                idOrigem="synthetic-doc-2",
                sequencia=2,
                hrefBinario=f"/processos/{CNJ}/documentos/synthetic-doc-1/binario",
            ),
        )
    )
    with pytest.raises(PermanenteError):
        await adapter(transport).list_documents(SESSION, CNJ, Grau.PRIMEIRO)
