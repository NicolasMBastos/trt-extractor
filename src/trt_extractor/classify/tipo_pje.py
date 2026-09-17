"""First classification layer: only caller-provided national type codes."""

from __future__ import annotations

from collections.abc import Mapping

from trt_extractor.core.contracts import (
    Classificacao,
    DocumentoRef,
    MetodoClassificacao,
    TipoDocumento,
)


class ClassificadorTipoPje:
    """Classifies a known PJe code and abstains for every other document.

    Code meanings are evidence-dependent and therefore supplied by the caller.
    This component does not infer a class from title, sequence, text or sigilo.
    """

    def __init__(self, tipos_por_codigo: Mapping[str, TipoDocumento]) -> None:
        self._tipos_por_codigo = dict(tipos_por_codigo)

    async def classificar(
        self, documento: DocumentoRef, texto: str | None
    ) -> Classificacao:
        del texto
        codigo = documento.tipo_pje
        tipo = self._tipos_por_codigo.get(codigo or "")
        if tipo is None:
            return Classificacao(
                tipo=TipoDocumento.OUTRO,
                metodo=MetodoClassificacao.TIPO_PJE,
                confianca=0.0,
                detalhe={"codigo": codigo, "resultado": "nao_mapeado"},
            )
        return Classificacao(
            tipo=tipo,
            metodo=MetodoClassificacao.TIPO_PJE,
            confianca=1.0,
            detalhe={"codigo": codigo},
        )
