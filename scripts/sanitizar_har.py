"""Sanitiza um HAR antes de versionar.

HAR bruto do fluxo do PJe carrega `Authorization`, cookies de sessão e o conteúdo
das peças processuais. Só a versão sanitizada pode ir para o git — o job `segredos`
do CI barra o resto.

Postura: **over-redaction é seguro, under-redaction não é.** Na dúvida, remove.
O que precisa sobreviver é a *estrutura* — URL, método, status, timing, nomes de
header — porque é isso que torna o HAR útil como insumo de engenharia.

    python scripts/sanitizar_har.py ENTRADA.har [-o SAIDA.sanitized.har]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# Nome de header/param cujo VALOR nunca pode sobreviver.
SENSIVEL_RE = re.compile(
    r"authorization|cookie|token|auth|session|sessao|senha|password|secret|key|csrf",
    re.IGNORECASE,
)

MARCADOR = "[REDIGIDO]"

# Corpo de resposta só sobrevive se for metadado pequeno e legível.
MIMES_PRESERVAVEIS = ("application/json", "text/plain")
MAX_CORPO_PRESERVADO = 20_000  # chars

# Ordem importa: CNPJ (14) antes de CPF (11) para não fatiar um CNPJ nu.
PADROES_TEXTO: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("cnpj", re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")),
    ("cnpj", re.compile(r"\b\d{14}\b")),
    ("cpf", re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")),
    ("cpf", re.compile(r"\b\d{11}\b")),
    ("base64_longo", re.compile(r"[A-Za-z0-9+/]{512,}={0,2}")),
)


def redigir_texto(texto: str, contagem: Counter[str]) -> str:
    """Remove CPF, CNPJ e blobs base64 longos de texto livre."""
    for rotulo, padrao in PADROES_TEXTO:
        texto, n = padrao.subn(MARCADOR, texto)
        if n:
            contagem[rotulo] += n
    return texto


def _redigir_lista_nome_valor(
    itens: list[dict[str, Any]], contagem: Counter[str], rotulo: str
) -> list[dict[str, Any]]:
    """HAR guarda headers, queryString e cookies como lista de {name, value}.

    Preserva o NOME (é o que dá valor de engenharia ao HAR) e redige o valor.
    """
    saida = []
    for item in itens:
        if not isinstance(item, dict):
            continue
        novo = dict(item)
        nome = str(novo.get("name", ""))
        if SENSIVEL_RE.search(nome):
            novo["value"] = MARCADOR
            contagem[rotulo] += 1
        elif isinstance(novo.get("value"), str):
            novo["value"] = redigir_texto(novo["value"], contagem)
        saida.append(novo)
    return saida


def _redigir_conteudo(conteudo: dict[str, Any], contagem: Counter[str]) -> dict[str, Any]:
    """Corpo de resposta. Substitui por marcador quando não for metadado pequeno."""
    novo = dict(conteudo)
    texto = novo.get("text")
    if not isinstance(texto, str):
        return novo

    mime = str(novo.get("mimeType", "")).lower()
    preservavel = any(mime.startswith(m) for m in MIMES_PRESERVAVEIS)

    if not preservavel or len(texto) > MAX_CORPO_PRESERVADO:
        novo["text"] = (
            f"{MARCADOR} corpo removido (mimeType={mime or 'desconhecido'}, "
            f"{len(texto)} chars)"
        )
        contagem["corpo_resposta"] += 1
        return novo

    novo["text"] = redigir_texto(texto, contagem)
    return novo


def sanitizar(har: Any) -> tuple[Any, Counter[str]]:
    """Devolve (har_sanitizado, contagem_por_categoria). Não muta a entrada."""
    contagem: Counter[str] = Counter()

    if not isinstance(har, dict) or "log" not in har:
        raise ValueError("não parece um HAR: falta a chave 'log' na raiz")

    log = dict(har["log"])
    entradas = []

    for entrada in log.get("entries", []) or []:
        if not isinstance(entrada, dict):
            continue
        nova = dict(entrada)

        req = dict(nova.get("request", {}) or {})
        for campo, rotulo in (
            ("headers", "header"),
            ("queryString", "query_param"),
            ("cookies", "cookie"),
        ):
            if isinstance(req.get(campo), list):
                req[campo] = _redigir_lista_nome_valor(req[campo], contagem, rotulo)

        post = req.get("postData")
        if isinstance(post, dict):
            post = dict(post)
            if isinstance(post.get("params"), list):
                post["params"] = _redigir_lista_nome_valor(
                    post["params"], contagem, "post_param"
                )
            if isinstance(post.get("text"), str):
                post["text"] = redigir_texto(post["text"], contagem)
            req["postData"] = post
        nova["request"] = req

        resp = dict(nova.get("response", {}) or {})
        for campo, rotulo in (("headers", "header"), ("cookies", "cookie")):
            if isinstance(resp.get(campo), list):
                resp[campo] = _redigir_lista_nome_valor(resp[campo], contagem, rotulo)
        if isinstance(resp.get("content"), dict):
            resp["content"] = _redigir_conteudo(resp["content"], contagem)
        nova["response"] = resp

        entradas.append(nova)

    log["entries"] = entradas
    return {**har, "log": log}, contagem


def caminho_saida(entrada: Path, explicito: str | None) -> Path:
    if explicito:
        return Path(explicito)
    nome = entrada.name
    if nome.endswith(".har"):
        nome = nome[: -len(".har")]
    return entrada.with_name(f"{nome}.sanitized.har")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("entrada", type=Path)
    p.add_argument("-o", "--saida", default=None)
    args = p.parse_args(argv)

    if not args.entrada.is_file():
        print(f"erro: {args.entrada} não existe", file=sys.stderr)
        return 2

    har = json.loads(args.entrada.read_text(encoding="utf-8"))
    limpo, contagem = sanitizar(har)

    destino = caminho_saida(args.entrada, args.saida)
    destino.write_text(
        json.dumps(limpo, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"sanitizado: {destino}")
    if contagem:
        print("removido, por categoria:")
        for rotulo, n in sorted(contagem.items()):
            print(f"  {rotulo:<16} {n}")
    else:
        print("nada sensível encontrado (confira se o HAR está completo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
