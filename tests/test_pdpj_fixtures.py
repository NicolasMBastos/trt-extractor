"""Structural assertions for deliberately synthetic PDPJ test data."""

from __future__ import annotations

import json
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "pdpj" / "processo_sintetico.json"
CNJ = "0000000-00.2026.5.04.0000"


def test_fixture_is_synthetic_and_exercises_required_document_shapes() -> None:
    processo = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert processo["numeroProcesso"] == CNJ
    assert processo["siglaTribunal"] == "TRT4"
    documentos = processo["tramitacaoAtual"]["documentos"]
    assert len(documentos) == 5
    assert {doc["sequencia"] for doc in documentos} == {1, 2, 3, 4, 5}
    assert {doc["idOrigem"] for doc in documentos} == {
        f"synthetic-{n}" for n in range(1, 6)
    }
    assert all(doc["idCodex"].startswith("synthetic-") for doc in documentos)
    assert all("@" not in json.dumps(doc) for doc in documentos)
    assert all("cpf" not in json.dumps(doc).lower() for doc in documentos)


def test_fixture_keeps_public_restricted_and_text_binary_shapes_distinct() -> None:
    documentos = json.loads(FIXTURE.read_text(encoding="utf-8"))["tramitacaoAtual"][
        "documentos"
    ]
    assert any(doc["nivelSigilo"] == "PUBLICO" for doc in documentos)
    assert any(doc["nivelSigilo"] == "SIGILOSO" for doc in documentos)
    assert {202, 402, 990001, 990002} <= {doc["tipo"]["codigo"] for doc in documentos}
    for doc in documentos:
        assert doc["hrefBinario"].startswith(f"/processos/{CNJ}/documentos/synthetic-")
        assert doc["hrefBinario"].endswith("/binario")
        assert doc["hrefTexto"].startswith(f"/processos/{CNJ}/documentos/synthetic-")
        assert doc["hrefTexto"].endswith("/texto")
