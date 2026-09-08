# Backlog vivo - 2026-09-08

Orquestrador: Codex. Checkout compartilhado, sem commit/push. Nenhuma rede judicial.
Base: main, 7057fa267acd35f0a7a805f78894147cb99ff349, inicialmente limpo.

| ID | Tarefa | Dependencias | Agente | Arquivos | Estado | Gate |
| -- | ------ | ------------ | ------ | -------- | ------ | ---- |
| A1 | Contrato operacional PDPJ | leitura constitucional | Prisma / Claude | somente leitura | DONE | revisao Codex |
| B1 | Fixtures sinteticas PDPJ | evidencia local | Molde / OpenCode + Codex | tests/fixtures/pdpj; tests/test_pdpj_fixtures.py | DONE | testes + revisao |
| C1 | Matriz L2 | evidencia local | Codex apos falha AGY | docs/execucao/download-l2.md | DONE | sem semantica inventada |
| E1 | Baseline e ambiente 3.12 | nenhuma | Codex | .venv; docs/execucao | DONE | baseline 35; gate atual verde |
| T1 | HttpxTransport injetavel | E1 | Sonda / Claude substituiu AGY | core/httpx_transport.py; tests/test_httpx_transport.py | DONE | 49 testes; revisao Codex |
| A2 | Adapter nacional | A1, B1, C1 | Codex | adapters/pdpj.py; tests/test_pdpj.py | DONE LOCAL | 159 testes; lint e mypy verdes |
| S0 | Plano SessionPool | A1 revisada | Prisma / Claude + Codex | core/session_pool.py; tests/test_session_pool.py | DONE LOCAL | 50 consumidores simulados |
| R1 | Revisao cruzada adapter/transport | A2, T1 | Prisma/Claude | somente leitura | BLOCKED | quota Maestri; parecer independente pendente |
| S1 | SessionPool offline | Gate 1, S0 | Codex | core/session_pool.py; testes proprios | DONE LOCAL | 50 consumidores simulados |
| K1 | Classificacao por codigo PJe | S1 | Codex | classify/tipo_pje.py; tests/test_classify_tipo_pje.py | DONE LOCAL | mapeamento injetado; 5 testes |
| X1 | Preparar L3 sem OCR | C1 | Codex | docs/execucao/l3-href-texto.md | DONE | probe minimo, sem rede |
| F3 | Estado/fila | Gate 1 e Session estaveis | a designar | a definir conforme migration | BLOCKED | Postgres local + restart |

## Baseline

- Python inicialmente exposto: 3.14. Localizado uv Python 3.12.13 e criado .venv.
- Baseline confirmado em 3.12.13: 35 passed, 1 deselected; mypy 7 arquivos OK.
- Primeira execucao sandbox: 22 passaram, 13 erros WinError 5 em tmp_path, 1 excluido.
- Reexecucao autorizada fora do sandbox: 35 passed, 1 deselected, 0.80s.
- `python -m mypy`: sucesso, 7 arquivos.
- Ruff 0.15.19: 20 ocorrencias preexistentes; format: 5 arquivos.
- Contrato protegido tinha ocorrencias UP035, UP042, RUF002 e formatacao.
  Patch mecanico separado foi aplicado; lint global esta verde.
- ~~README ainda diz keywords vazio e fase 0~~ RESOLVIDO (verificado 2026-09-08: README ja
  diz "base PDPJ em implementacao" e keywords "pesos documentados").
- ~~CI executa portao em job separado~~ RESOLVIDO (verificado 2026-09-08).
- ~~Guarda CI de nomes inclui `.env.example`~~ RESOLVIDO (verificado 2026-09-08:
  ci.yml:40 ja tem `grep -v '^\.env\.example$'`).
- L2: somente prefixo e tamanho do JSON registrados; codigo/semantica NAO CONFIRMADOS.
- Graus da resposta, varios documentos por pedido e authenticate precisam conciliacao explicita.

## Ownership

Nenhum agente pode alterar contracts.py, capabilities.yaml, migrations ou ADRs.
Nenhum agente pode fazer commit, push, acessar certificado ou trafegar contra tribunal.
Saidas dos agentes sao propostas ate revisao do diff e execucao local pelo Codex.

## Integracao corrente

- CI exclui rede e portao, guarda permite somente .env.example na raiz.
- Pytest bloqueia rede por padrao; loopback permitido para asyncio Windows.
- 2 testes do bloqueio + 60 testes PDPJ passaram localmente.
- AGY falhou duas vezes com erro interno; Maestri debug indicou conexao saudavel.
  Slot substituido por Claude para T1, sem criar terminal duplicado.
- B1 OpenCode tentou caminho com erro de grafia; acesso externo rejeitado e task reduzida.
- A1 revisada: rejeitados menor sequencia como desempate que descarta pecas,
  derivacao de hrefTexto e JSON curto como geracao presumida. Mapeador de grau injetado.
- R1 tentou reutilizar o terminal OpenCode apos interrupcao; o agente nao estava ativo e
  recebeu o contrato como comando PowerShell. Nenhuma alteracao foi feita por ele.
  Revisao final foi feita pelo Codex com testes adversariais, mypy e diff.
- K1 implementa somente a camada `tipo_pje`: aceita mapeamento explicito do
  chamador e se abstém com OUTRO para codigo ausente ou desconhecido. Nao usa
  texto, sequencia, keywords, LLM ou rede.
