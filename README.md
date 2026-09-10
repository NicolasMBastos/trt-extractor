# trt-extractor

Aquisição em volume de peças processuais (PDF) dos 24 TRTs.

Cinco classes-alvo: **petição inicial, acórdão, sentença, acordo, laudo/perícia**.
O entregável é o binário — metadado existe só para saber qual arquivo buscar e onde
guardar. Este não é um projeto de metadados.

Acesso por certificado digital próprio, legítimo, que já seria feito manualmente. O
objetivo é volume e velocidade, não acesso a algo indisponível.

> **Estado: base PDPJ em implementação.** Via nacional, transporte HTTP/2 e CAS foram
> comprovados; adapter, transporte e pool de sessão têm testes locais sem rede judicial.

## Comece por aqui

| Documento | O que é |
|---|---|
| [`Continua_codex.md`](Continua_codex.md) | **Comece aqui.** O mapa do projeto: contexto, o que está provado, o que falta, roadmap |
| [`docs/execucao/handoff-orquestrador.md`](docs/execucao/handoff-orquestrador.md) | **Se você vai orquestrar agentes:** estado do canvas, quais funcionam, armadilhas de ambiente, contrato de tarefa |
| [`docs/canais-publicos/`](docs/canais-publicos/) | O que dá para extrair **sem autenticar** — medido, com os percentuais honestos por classe |
| [`docs/arquitetura.md`](docs/arquitetura.md) | A arquitetura, e onde ela diverge do briefing original |
| [`docs/fase-0/plano.md`](docs/fase-0/plano.md) | Checklist executável da fase 0 + **3 perguntas para o dono do projeto** |
| [`docs/decisions/`](docs/decisions/) | Registros de decisão arquitetural |
| [`docs/maestri-cli.md`](docs/maestri-cli.md) | Mapa do Maestri CLI desta versão |
| [`capabilities.yaml`](capabilities.yaml) | Matriz de capacidade — **dado de produção**, lido em runtime |

## Estrutura

```
src/trt_extractor/
  core/contracts.py     TribunalAdapter, Transport, Session, Storage — interfaces
  adapters/             pdpj (Via 0, nacional) · pje2x (genérico) · mni · por tribunal
  storage/              content-addressed por sha256
  classify/             tipo_pje → posição no fluxo → keywords → LLM
migrations/001_inicial.sql   esquema + máquina de estados validada por trigger
config/keywords.yaml         pesos documentados; validação de fase 4 ainda pendente
capabilities.yaml            TRT4 parcial; demais TRTs não testados
research/har/                HARs sanitizados da fase 0
```

## Caminho nacional comprovado

H1 e H2 foram respondidas na evidência PDPJ: a API nacional entrega listagem e binário por
`hrefBinario`; `httpx` com HTTP/2 e User-Agent estável recebe 200. HTTP/1.1 sem UA recebeu
403. Os requisitos estão aplicados no transporte.

## Desenvolvimento

Python **3.12** (a máquina tem 3.14; ver arquitetura §2 D6).

```bash
py -3.12 -m venv .venv && .venv/Scripts/activate   # Windows
pip install -e ".[dev,pdf]"

pytest -m "not rede and not portao"   # suíte normal — tem que ficar verde
pytest -m "portao"                    # portões de fase — vermelho de propósito
```

`-m "not rede and not portao"` é obrigatório para a suíte normal: **zero teste que bate
em tribunal de produção**. O bloqueio de rede também é aplicado localmente.

### Smoke da migration

O PostgreSQL de desenvolvimento é exclusivo para este smoke, exposto apenas em
`127.0.0.1:54329` e armazenado em `tmpfs`; os dados desaparecem quando o container é
removido. As credenciais no `docker-compose.yml` são públicas e só valem nesse ambiente.

```powershell
docker compose up -d --wait
$env:TRT_EXTRACTOR_RUN_LOCAL_DB_SMOKE = "1"
pytest tests/test_migration_smoke.py
docker compose down
```

O teste permanece desabilitado sem `TRT_EXTRACTOR_RUN_LOCAL_DB_SMOKE=1`. Quando habilitado,
falha com instrução objetiva se o PostgreSQL local não estiver disponível. Ele aplica
`migrations/001_inicial.sql` sem modificá-la.

### Classificação

`config/keywords.yaml` contém pesos de produção e derivados documentados. A fase 4 segue
pendente de validação contra amostra rotulada e da confirmação de `hrefTexto`.

## Segurança e conformidade

- `.gitignore` exclui certificados, credenciais, `.env` e **todo PDF**. O CI tem job
  próprio que barra qualquer um deles no índice.
- HAR bruto carrega `Authorization`, cookies e peça processual. Só entra no git
  sanitizado (`*.sanitized.har`) — o CI verifica.
- Chave privada, senha de certificado e PIN nunca entram no processo nem em log.
  `Credencial` e `Session` têm `__repr__` que não vaza CPF nem token.
- `SIGILOSO` é estado terminal **legítimo**, não erro: registra, não faz retry, e sai do
  denominador da taxa de erro (view `v_taxa_erro`).
- Auditoria completa por credencial/processo/peça — para debug, para demonstrar
  legitimidade e para LGPD.
- **Não há evasão de detecção neste projeto.** Se essa parecer a saída, a resposta certa
  é subir de via ou escalar a decisão.
