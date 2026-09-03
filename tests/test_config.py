"""Testes de configuração. Rodam sem rede, sem banco, sem credencial.

O teste de keywords falha de propósito enquanto o dono do projeto não fornecer os
termos. É o portão que impede a fase 4 de ser declarada pronta com o classificador
vazio.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[1]
CLASSES_ALVO = {
    "peticao_inicial",
    "acordao",
    "sentenca",
    "acordo",
    "laudo_pericia",
}
CAMPOS_BUSCA_VALIDOS = {
    "titulo",
    "tipo_pje",
    "nome_arquivo",
    "texto_primeira_pagina",
    "texto_completo",
}


def _carrega(caminho: Path) -> dict:
    return yaml.safe_load(caminho.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# capabilities.yaml
# ---------------------------------------------------------------------------


def test_capabilities_tem_os_24_trts() -> None:
    dados = _carrega(RAIZ / "capabilities.yaml")
    esperados = {f"TRT{n}" for n in range(1, 25)}
    assert set(dados["tribunais"]) == esperados


def test_capabilities_status_valido() -> None:
    dados = _carrega(RAIZ / "capabilities.yaml")
    validos = {"nao_testado", "parcial", "operacional", "bloqueado"}
    for sigla, tribunal in dados["tribunais"].items():
        assert tribunal["status"] in validos, sigla


def test_capabilities_medido_exige_data() -> None:
    """Um tribunal só sai de `nao_testado` com medição datada.

    Sem isto a matriz vira documentação otimista, e o orquestrador decide via de
    aquisição em cima de palpite.
    """
    dados = _carrega(RAIZ / "capabilities.yaml")
    for sigla, tribunal in dados["tribunais"].items():
        if tribunal["status"] != "nao_testado":
            assert tribunal["testado_em"], f"{sigla}: status medido sem testado_em"


def test_capabilities_limites_conservadores_enquanto_nao_medido() -> None:
    """Não medido ⇒ não paralelize. O briefing é explícito: medir o teto antes."""
    dados = _carrega(RAIZ / "capabilities.yaml")
    for sigla, tribunal in dados["tribunais"].items():
        if tribunal["status"] == "nao_testado":
            limites = tribunal["limites"]
            assert limites["jobs_concorrentes_por_sessao"] == 1, sigla
            assert limites["req_por_minuto"] <= 6, sigla


# ---------------------------------------------------------------------------
# keywords.yaml — falha enquanto vazio, por design
# ---------------------------------------------------------------------------


@pytest.mark.portao
def test_keywords_preenchido() -> None:
    """FALHA ESPERADA até o dono do projeto fornecer as palavras-chave.

    Não preencher para "fazer passar". Ver config/keywords.yaml e a pergunta 3 em
    docs/fase-0/plano.md §6.
    """
    dados = _carrega(RAIZ / "config" / "keywords.yaml")
    if not dados.get("classes"):
        pytest.fail(
            "config/keywords.yaml está vazio. As palavras-chave são fornecidas "
            "pelo dono do projeto — não inventar. Este teste é o portão da fase 4."
        )


def test_keywords_esquema_quando_preenchido() -> None:
    """Valida a forma assim que houver conteúdo. Passa (vazio) até lá."""
    dados = _carrega(RAIZ / "config" / "keywords.yaml")
    classes = dados.get("classes") or {}
    if not classes:
        pytest.skip("keywords.yaml ainda vazio; coberto por test_keywords_preenchido")

    for campo in dados.get("onde_buscar") or []:
        assert campo in CAMPOS_BUSCA_VALIDOS, f"campo de busca desconhecido: {campo}"

    for nome, classe in classes.items():
        assert nome in CLASSES_ALVO, f"classe fora das 5 alvo: {nome}"
        assert isinstance(classe.get("score_minimo"), int), nome
        for termo in classe.get("positivos") or []:
            assert termo["peso"] > 0, f"{nome}: positivo com peso <= 0"
            assert termo["termo"] == termo["termo"].lower(), (
                f"{nome}: termo deve estar normalizado (minúsculo, sem acento)"
            )
        for termo in classe.get("negativos") or []:
            assert termo["peso"] < 0, f"{nome}: negativo com peso >= 0"
