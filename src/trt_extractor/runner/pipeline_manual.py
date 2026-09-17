"""Runner manual de aquisição real, opt-in — substitui os scripts avulsos usados
para validar o pipeline nos 24 TRTs em 2026-09-17
(docs/execucao/validacao-24-trts-2026-09-17.md).

**Nunca roda sozinho.** Precisa de `TRT_EXTRACTOR_RUN_LIVE=1` explícito — sem essa
variável, `main()` sai sem tocar em rede, mesmo variável nenhuma faltando. Mesmo
princípio do smoke de migration (`TRT_EXTRACTOR_RUN_LOCAL_DB_SMOKE`,
`tests/test_migration_smoke.py`): opt-in explícito, nunca em CI, nunca em pytest
normal.

## Pré-requisitos operacionais

1. Chrome aberto pelo titular com `--remote-debugging-port` (login manual, ADR
   003/004/007 — este módulo não seleciona certificado nem digita PIN).
2. `TRT_EXTRACTOR_LIVE_CASES_FILE`: caminho pra um JSON local, **gitignored**,
   `{"TRT4": "0021479-63.2026.5.04.0402", ...}` — nunca versionar CNJs reais.
3. `TRT_EXTRACTOR_URL_SONDA`: endpoint de verificação de sessão. **Sem default**
   — qual requisição barata prova autenticação nunca foi medida (mesma regra de
   `criar_sonda`).
4. `TRT_EXTRACTOR_CDP_URL` (opcional, default `http://127.0.0.1:9333`).
5. `TRT_EXTRACTOR_CREDENCIAL_ID` — identificador local da credencial (nunca CPF).

## O que este módulo faz de diferente dos scripts de validação

Usa `Ritmo` de verdade (`capabilities.yaml`, disjuntor, janela operacional) em vez
de `asyncio.sleep` fixo — respeita parada em `ForaDaJanelaError`/
`DisjuntorAbertoError` em vez de dormir. Usa `SessionStore` real (persistência via
`Handshake.capturar`, já embutida em `executar_handshake_com_hook`). Registra
sucesso/falha no disjuntor a cada operação (`ritmo.registrar`).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from ..adapters.pdpj import PdpjAdapter
from ..core.capabilities import Capabilities
from ..core.contracts import (
    BloqueioError,
    Credencial,
    Grau,
    InexistenteError,
    PermanenteError,
    SigiloError,
    TipoDocumento,
    TransienteError,
)
from ..core.inpage_transport import InPageFetchTransport
from ..core.ritmo import Disjuntor, DisjuntorAbertoError, ForaDaJanelaError, Ritmo
from ..core.session_store import SessionStore
from ..storage.local_cas import LocalCASStorage
from .playwright_handshake import executar_handshake_com_hook

ORIGEM = "https://portaldeservicos.pdpj.jus.br"


def _mapear_grau(tramite: Mapping[str, Any]) -> Grau:
    """Mapeamento medido ao vivo em 2026-09-17: `tipo.grau` é objeto
    `{"numero": 1|2, ...}`, não string solta. Ver
    docs/execucao/validacao-24-trts-2026-09-17.md."""
    numero = tramite["grau"]["numero"]
    return {1: Grau.PRIMEIRO, 2: Grau.SEGUNDO}[numero]


def _ler_configuracao() -> dict[str, str] | None:
    """`None` quando o harness não está ativado — `main()` sai sem efeito.
    Levanta quando ativado sem o que ele precisa, sem inventar default."""
    if os.getenv("TRT_EXTRACTOR_RUN_LIVE") != "1":
        return None
    obrigatorias = {
        "cases_file": "TRT_EXTRACTOR_LIVE_CASES_FILE",
        "url_sonda": "TRT_EXTRACTOR_URL_SONDA",
        "credencial_id": "TRT_EXTRACTOR_CREDENCIAL_ID",
    }
    faltando = [nome for chave, nome in obrigatorias.items() if not os.getenv(nome)]
    if faltando:
        raise SystemExit("TRT_EXTRACTOR_RUN_LIVE=1 exige também: " + ", ".join(faltando))
    return {
        "cases_file": os.environ["TRT_EXTRACTOR_LIVE_CASES_FILE"],
        "url_sonda": os.environ["TRT_EXTRACTOR_URL_SONDA"],
        "credencial_id": os.environ["TRT_EXTRACTOR_CREDENCIAL_ID"],
        "cdp_url": os.getenv("TRT_EXTRACTOR_CDP_URL", "http://127.0.0.1:9333"),
    }


async def executar_lote(
    candidatos: dict[str, str],
    *,
    cdp_url: str,
    url_sonda: str,
    credencial: Credencial,
    store: SessionStore,
    ritmo: Ritmo,
    storage: LocalCASStorage,
) -> dict[str, dict[str, Any]]:
    """Roda list_documents + download de 1 documento não-sigiloso por
    `(tribunal, cnj)` em `candidatos`. Sequencial, sempre — nunca concorrente entre
    tribunais (concorrência aqui aumentaria tráfego sob a mesma identidade sem
    ganho de throughput real, dado que a API responde em <1s por chamada).

    Captura a sessão uma vez (primeiro candidato) e reaproveita o token nos
    tribunais seguintes — medido ao vivo que o Bearer do PDPJ nacional não é
    específico de tribunal.
    """
    if not candidatos:
        return {}
    primeiro_tribunal = next(iter(candidatos))

    sessao, _contexto, _browser, pw = await executar_handshake_com_hook(
        tribunal=primeiro_tribunal,
        origem=ORIGEM,
        credencial=credencial,
        cdp_url=cdp_url,
        url_navegacao=f"{ORIGEM}/consulta",
        url_sonda=url_sonda,
        store=store,
        ritmo=ritmo,
    )
    pagina = sessao.contexto_browser
    assert pagina is not None  # capturado por executar_handshake_com_hook

    resultados: dict[str, dict[str, Any]] = {}
    try:
        for tribunal, cnj in candidatos.items():
            try:
                await ritmo.aguardar(tribunal, credencial.id)
            except (ForaDaJanelaError, DisjuntorAbertoError) as e:
                resultados[tribunal] = {"status": type(e).__name__, "detalhe": str(e)}
                continue

            sessao_tribunal = replace(sessao, tribunal=tribunal)
            transporte = InPageFetchTransport(
                ORIGEM, pagina, credencial_id=credencial.id, timeout=60.0
            )
            adapter = PdpjAdapter(transporte, tribunal, grau_mapper=_mapear_grau)

            try:
                docs = await adapter.list_documents(sessao_tribunal, cnj, Grau.PRIMEIRO)
            except SigiloError:
                ritmo.registrar(tribunal, None)  # terminal legítimo, não é falha
                resultados[tribunal] = {"status": "sigiloso"}
                continue
            except InexistenteError:
                ritmo.registrar(tribunal, None)
                resultados[tribunal] = {"status": "inexistente"}
                continue
            except (BloqueioError, TransienteError, PermanenteError) as e:
                ritmo.registrar(tribunal, e)
                resultados[tribunal] = {
                    "status": "falha_list",
                    "detalhe": f"{type(e).__name__}: {e}",
                }
                if isinstance(e, BloqueioError):
                    break  # disjuntor já abriu; parar a rodada inteira
                continue
            ritmo.registrar(tribunal, None)

            alvo = next((d for d in docs if d.href_binario and not d.sigiloso), None)
            if alvo is None:
                resultados[tribunal] = {
                    "status": "listado_sem_binario",
                    "total_documentos": len(docs),
                }
                continue

            await ritmo.aguardar(tribunal, credencial.id)
            try:
                pedido = await adapter.request_download(
                    sessao_tribunal,
                    cnj,
                    Grau.PRIMEIRO,
                    tipos=[TipoDocumento.OUTRO],
                    documentos=[alvo],
                )
                poll = await adapter.poll_download(sessao_tribunal, pedido)
                artefato = await adapter.fetch_artifact(sessao_tribunal, pedido, poll)
            except (BloqueioError, TransienteError, PermanenteError) as e:
                ritmo.registrar(tribunal, e)
                resultados[tribunal] = {
                    "status": "falha_fetch",
                    "total_documentos": len(docs),
                    "detalhe": f"{type(e).__name__}: {e}",
                }
                if isinstance(e, BloqueioError):
                    break
                continue
            ritmo.registrar(tribunal, None)

            sha = await storage.put(artefato)
            resultados[tribunal] = {
                "status": "ok",
                "total_documentos": len(docs),
                "tipo_baixado": alvo.tipo_pje,
                "sha256": sha,
                "tamanho_bytes": len(artefato.conteudo),
                "pdf_valido": artefato.conteudo[:5] == b"%PDF-",
            }
    finally:
        await pw.stop()  # nunca browser.close() -- e' o Chrome do titular

    return resultados


async def main() -> None:
    config = _ler_configuracao()
    if config is None:
        print("TRT_EXTRACTOR_RUN_LIVE != '1' -- harness opt-in inativo, nada a fazer.")
        return

    candidatos = json.loads(Path(config["cases_file"]).read_text(encoding="utf-8"))
    capabilities = Capabilities.de_arquivo(Path("capabilities.yaml"))
    ritmo = Ritmo(capabilities, Disjuntor(falhas_para_abrir=3), jitter=0.2)
    store = SessionStore()
    credencial = Credencial(id=config["credencial_id"], cpf="")
    storage = LocalCASStorage(Path("data/cas-producao"))

    resultados = await executar_lote(
        candidatos,
        cdp_url=config["cdp_url"],
        url_sonda=config["url_sonda"],
        credencial=credencial,
        store=store,
        ritmo=ritmo,
        storage=storage,
    )
    for tribunal, resultado in resultados.items():
        print(tribunal, resultado)


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)
