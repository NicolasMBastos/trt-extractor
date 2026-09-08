from __future__ import annotations

import pytest

from trt_extractor.classify import ClassificadorTipoPje
from trt_extractor.core.contracts import (
    DocumentoRef,
    Grau,
    MetodoClassificacao,
    TipoDocumento,
)


def documento(*, codigo: str | None, sigiloso: bool = False) -> DocumentoRef:
    return DocumentoRef(
        id_origem="synthetic-document",
        numero_cnj="0000000-00.2026.5.04.0000",
        grau=Grau.PRIMEIRO,
        tipo_pje=codigo,
        sigiloso=sigiloso,
    )


@pytest.mark.asyncio
async def test_classifica_codigo_explicito_e_registra_sinal() -> None:
    classificador = ClassificadorTipoPje({"202": TipoDocumento.PETICAO_INICIAL})

    resultado = await classificador.classificar(documento(codigo="202"), texto="ignorado")

    assert resultado.tipo is TipoDocumento.PETICAO_INICIAL
    assert resultado.metodo is MetodoClassificacao.TIPO_PJE
    assert resultado.confianca == 1.0
    assert resultado.detalhe == {"codigo": "202"}


@pytest.mark.asyncio
@pytest.mark.parametrize("codigo", [None, "999999"])
async def test_abstem_para_codigo_ausente_ou_desconhecido(codigo: str | None) -> None:
    classificador = ClassificadorTipoPje({"202": TipoDocumento.PETICAO_INICIAL})

    resultado = await classificador.classificar(documento(codigo=codigo), texto=None)

    assert resultado.tipo is TipoDocumento.OUTRO
    assert resultado.metodo is MetodoClassificacao.TIPO_PJE
    assert resultado.confianca == 0.0
    assert resultado.detalhe == {"codigo": codigo, "resultado": "nao_mapeado"}


@pytest.mark.asyncio
async def test_mapeamento_vazio_nao_inventa_classe() -> None:
    resultado = await ClassificadorTipoPje({}).classificar(
        documento(codigo="202"), texto=None
    )

    assert resultado.tipo is TipoDocumento.OUTRO


@pytest.mark.asyncio
async def test_sigilo_nao_muda_classificacao_por_codigo() -> None:
    resultado = await ClassificadorTipoPje(
        {"202": TipoDocumento.PETICAO_INICIAL}
    ).classificar(documento(codigo="202", sigiloso=True), texto="peticao inicial")

    assert resultado.tipo is TipoDocumento.PETICAO_INICIAL
    assert resultado.detalhe == {"codigo": "202"}
