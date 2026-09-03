"""Testes do sanitizador de HAR.

O HAR daqui é sintético. Nunca usar HAR real em teste — é justamente o artefato
que o sanitizador existe para tornar seguro.

O que importa nestes testes: **nenhum segredo sobrevive** e **a estrutura sobrevive**.
Um sanitizador que apaga tudo passaria na primeira metade e destruiria o valor do HAR;
um que preserva demais vaza. Os dois lados são testados.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from sanitizar_har import MARCADOR, caminho_saida, main, redigir_texto, sanitizar  # noqa: E402

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.cargaUtilFalsa.assinaturaFalsa"
BASE64_LONGO = "QUJD" * 200  # 800 chars


@pytest.fixture
def har() -> dict:
    return {
        "log": {
            "version": "1.2",
            "entries": [
                {
                    "startedDateTime": "2026-09-03T10:00:00.000Z",
                    "time": 412,
                    "request": {
                        "method": "GET",
                        "url": "https://portaldeservicos.pdpj.jus.br/api/v2/processos",
                        "headers": [
                            {"name": "Authorization", "value": f"Bearer {TOKEN}"},
                            {"name": "Cookie", "value": "AWSALB=abc; sessao=xyz"},
                            {"name": "X-CSRF-Token", "value": "csrf-secreto"},
                            {"name": "Accept", "value": "application/json"},
                        ],
                        "queryString": [
                            {"name": "cpfCnpjParte", "value": "12345678000199"},
                            {"name": "access_token", "value": TOKEN},
                            {"name": "grau", "value": "1"},
                        ],
                        "cookies": [{"name": "sessionid", "value": "s3cr3t"}],
                        "postData": {
                            "mimeType": "application/json",
                            "text": '{"cpf": "123.456.789-00"}',
                            "params": [{"name": "senha", "value": "hunter2"}],
                        },
                    },
                    "response": {
                        "status": 200,
                        "headers": [
                            {"name": "Set-Cookie", "value": "AWSALB=deadbeef"},
                            {"name": "Content-Type", "value": "application/json"},
                        ],
                        "cookies": [],
                        "content": {
                            "size": 42,
                            "mimeType": "application/json",
                            "text": '{"parte": "111.222.333-44", "ok": true}',
                        },
                    },
                },
                {
                    "startedDateTime": "2026-09-03T10:00:05.000Z",
                    "time": 1800,
                    "request": {
                        "method": "GET",
                        "url": "https://pje.trt4.jus.br/documento/9001",
                        "headers": [{"name": "Accept", "value": "application/pdf"}],
                        "queryString": [],
                        "cookies": [],
                    },
                    "response": {
                        "status": 200,
                        "headers": [
                            {"name": "Content-Type", "value": "application/pdf"}
                        ],
                        "cookies": [],
                        "content": {
                            "size": 900,
                            "mimeType": "application/pdf",
                            "encoding": "base64",
                            "text": BASE64_LONGO,
                        },
                    },
                },
            ],
        }
    }


def _tudo(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False)


# --- nada sensível sobrevive -------------------------------------------------


def test_token_nao_sobrevive(har: dict) -> None:
    limpo, _ = sanitizar(har)
    assert TOKEN not in _tudo(limpo)


def test_valores_de_headers_sensiveis_redigidos(har: dict) -> None:
    limpo, _ = sanitizar(har)
    req = limpo["log"]["entries"][0]["request"]
    por_nome = {h["name"]: h["value"] for h in req["headers"]}
    assert por_nome["Authorization"] == MARCADOR
    assert por_nome["Cookie"] == MARCADOR
    assert por_nome["X-CSRF-Token"] == MARCADOR


def test_set_cookie_da_resposta_redigido(har: dict) -> None:
    limpo, _ = sanitizar(har)
    resp = limpo["log"]["entries"][0]["response"]
    por_nome = {h["name"]: h["value"] for h in resp["headers"]}
    assert por_nome["Set-Cookie"] == MARCADOR


def test_query_param_sensivel_redigido(har: dict) -> None:
    limpo, _ = sanitizar(har)
    qs = {q["name"]: q["value"] for q in limpo["log"]["entries"][0]["request"]["queryString"]}
    assert qs["access_token"] == MARCADOR


def test_cpf_e_cnpj_removidos(har: dict) -> None:
    limpo, _ = sanitizar(har)
    texto = _tudo(limpo)
    for sensivel in ("123.456.789-00", "111.222.333-44", "12345678000199"):
        assert sensivel not in texto


def test_corpo_binario_grande_substituido_por_marcador(har: dict) -> None:
    limpo, _ = sanitizar(har)
    conteudo = limpo["log"]["entries"][1]["response"]["content"]
    assert BASE64_LONGO not in _tudo(limpo)
    assert conteudo["text"].startswith(MARCADOR)
    assert "application/pdf" in conteudo["text"]


def test_post_param_sensivel_redigido(har: dict) -> None:
    limpo, _ = sanitizar(har)
    params = limpo["log"]["entries"][0]["request"]["postData"]["params"]
    assert {p["name"]: p["value"] for p in params}["senha"] == MARCADOR


# --- a estrutura sobrevive ---------------------------------------------------


def test_urls_e_metodos_sobrevivem(har: dict) -> None:
    limpo, _ = sanitizar(har)
    entradas = limpo["log"]["entries"]
    assert entradas[0]["request"]["url"].endswith("/api/v2/processos")
    assert entradas[1]["request"]["url"].endswith("/documento/9001")
    assert entradas[0]["request"]["method"] == "GET"


def test_nomes_de_header_sobrevivem(har: dict) -> None:
    """O nome é metade do valor de engenharia do HAR. Só o valor some."""
    limpo, _ = sanitizar(har)
    nomes = {h["name"] for h in limpo["log"]["entries"][0]["request"]["headers"]}
    assert {"Authorization", "Cookie", "X-CSRF-Token", "Accept"} <= nomes


def test_status_e_timing_sobrevivem(har: dict) -> None:
    limpo, _ = sanitizar(har)
    assert limpo["log"]["entries"][0]["response"]["status"] == 200
    assert limpo["log"]["entries"][1]["time"] == 1800


def test_header_nao_sensivel_intacto(har: dict) -> None:
    limpo, _ = sanitizar(har)
    por_nome = {h["name"]: h["value"] for h in limpo["log"]["entries"][0]["request"]["headers"]}
    assert por_nome["Accept"] == "application/json"


def test_json_pequeno_preservado_mas_redigido(har: dict) -> None:
    limpo, _ = sanitizar(har)
    texto = limpo["log"]["entries"][0]["response"]["content"]["text"]
    assert '"ok": true' in texto        # estrutura sobrevive
    assert "111.222.333-44" not in texto  # dado pessoal não


# --- contagem, entrada inválida e CLI ---------------------------------------


def test_contagem_por_categoria(har: dict) -> None:
    _, contagem = sanitizar(har)
    assert contagem["header"] >= 4
    assert contagem["corpo_resposta"] == 1
    assert contagem["cpf"] >= 2


def test_nao_muta_a_entrada(har: dict) -> None:
    antes = _tudo(har)
    sanitizar(har)
    assert _tudo(har) == antes


def test_entrada_invalida_falha_alto() -> None:
    with pytest.raises(ValueError, match="não parece um HAR"):
        sanitizar({"qualquer": "coisa"})


def test_nome_de_saida_padrao() -> None:
    assert caminho_saida(Path("a/TRT4-login.har"), None).name == "TRT4-login.sanitized.har"


def test_cli_ponta_a_ponta(har: dict, tmp_path: Path) -> None:
    entrada = tmp_path / "TRT4-fluxo.har"
    entrada.write_text(json.dumps(har), encoding="utf-8")

    assert main([str(entrada)]) == 0

    saida = tmp_path / "TRT4-fluxo.sanitized.har"
    assert saida.is_file()
    conteudo = saida.read_text(encoding="utf-8")
    assert TOKEN not in conteudo
    assert "/api/v2/processos" in conteudo


def test_redigir_texto_isolado() -> None:
    from collections import Counter

    c: Counter[str] = Counter()
    assert redigir_texto("CPF 123.456.789-00 fim", c) == f"CPF {MARCADOR} fim"
    assert c["cpf"] == 1
