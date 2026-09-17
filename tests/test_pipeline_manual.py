"""Testes do runner de pipeline manual. Sem browser, sem rede — só a parte pura:
leitura de configuração (opt-in) e mapeamento de grau.

A rede (`executar_lote`, `main` com RUN_LIVE=1) não é testável aqui, mesmo
princípio de `tests/test_migration_smoke.py`: opt-in explícito, fora do CI normal.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trt_extractor.core.contracts import Grau
from trt_extractor.runner.pipeline_manual import _ler_configuracao, _mapear_grau


@pytest.fixture(autouse=True)
def _limpa_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for nome in (
        "TRT_EXTRACTOR_RUN_LIVE",
        "TRT_EXTRACTOR_LIVE_CASES_FILE",
        "TRT_EXTRACTOR_URL_SONDA",
        "TRT_EXTRACTOR_CREDENCIAL_ID",
        "TRT_EXTRACTOR_CDP_URL",
    ):
        monkeypatch.delenv(nome, raising=False)


def test_harness_inativo_sem_run_live() -> None:
    """Sem a variável, `None` — `main()` sai sem tocar em rede. Nem uma variável
    faltando bloqueia: o harness só existe quando explicitamente ligado."""
    assert _ler_configuracao() is None


def test_harness_ativo_exige_as_tres_variaveis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRT_EXTRACTOR_RUN_LIVE", "1")
    with pytest.raises(SystemExit, match="LIVE_CASES_FILE"):
        _ler_configuracao()


def test_harness_ativo_com_tudo_devolve_configuracao(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRT_EXTRACTOR_RUN_LIVE", "1")
    monkeypatch.setenv("TRT_EXTRACTOR_LIVE_CASES_FILE", "data/live-cases.json")
    monkeypatch.setenv("TRT_EXTRACTOR_URL_SONDA", "https://exemplo/sonda")
    monkeypatch.setenv("TRT_EXTRACTOR_CREDENCIAL_ID", "titular-x")
    config = _ler_configuracao()
    assert config == {
        "cases_file": "data/live-cases.json",
        "url_sonda": "https://exemplo/sonda",
        "credencial_id": "titular-x",
        "cdp_url": "http://127.0.0.1:9333",
    }


def test_harness_cdp_url_e_configuravel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRT_EXTRACTOR_RUN_LIVE", "1")
    monkeypatch.setenv("TRT_EXTRACTOR_LIVE_CASES_FILE", "data/live-cases.json")
    monkeypatch.setenv("TRT_EXTRACTOR_URL_SONDA", "https://exemplo/sonda")
    monkeypatch.setenv("TRT_EXTRACTOR_CREDENCIAL_ID", "titular-x")
    monkeypatch.setenv("TRT_EXTRACTOR_CDP_URL", "http://127.0.0.1:9999")
    config = _ler_configuracao()
    assert config is not None
    assert config["cdp_url"] == "http://127.0.0.1:9999"


@pytest.mark.parametrize(("numero", "esperado"), [(1, Grau.PRIMEIRO), (2, Grau.SEGUNDO)])
def test_mapear_grau(numero: int, esperado: Grau) -> None:
    assert _mapear_grau({"grau": {"numero": numero, "sigla": "irrelevante"}}) == esperado


def test_mapear_grau_numero_desconhecido_levanta() -> None:
    with pytest.raises(KeyError):
        _mapear_grau({"grau": {"numero": 3}})
