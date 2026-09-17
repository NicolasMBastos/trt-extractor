# EXECUTION REPORT - TRT Extractor

## 1. Estado inicial

- Branch `main`, commit `7057fa267acd35f0a7a805f78894147cb99ff349`, worktree limpo.
- Baseline em Python 3.12.13: 35 aprovados e 1 excluido.
- O sandbox puro teve 13 erros `WinError 5` para `tmp_path`; a reexecucao em
  ambiente gravavel confirmou o baseline. Isso e bloqueio de ambiente, nao falha
  do repositorio.

## 2. O que foi executado

| Task | Agente | Resultado | Evidencia |
| --- | --- | --- | --- |
| Contrato operacional PDPJ | Prisma/Claude + Codex | concluido | proposta revisada contra contratos e ADRs |
| Fixture PDPJ sintetica | Molde/OpenCode + Codex | concluido | `tests/fixtures/pdpj/` sem dados reais |
| Semantica L2 | Codex | parcial | `download-l2.md`; payload real continua nao confirmado |
| Transporte HTTP/2 | Sonda/Claude + Codex | concluido | MockTransport, cookies isolados e erros normalizados |
| Adapter nacional PDPJ | Codex | concluido localmente | selecao explicita, sigilo, PDF e JSON injetavel |
| SessionPool | Codex | concluido localmente | 50 consumidores, single-flight e invalidação |
| Classificacao por codigo | Codex | concluido localmente | cinco testes, sem inferencia por texto |
| Preparacao L3 | Codex | concluido | probe sanitizado sem rede |

As tarefas de revisao em Maestri foram reenviadas, mas Claude e OpenCode estavam
indisponiveis por quota/terminal. Nenhuma delas foi declarada como revisao
independente concluida.

## 3. Codigo alterado

- `src/trt_extractor/adapters/pdpj.py`: adapter nacional com sessao existente e
  politica conservadora para sigilo, CNJ, binario e geracao.
- `src/trt_extractor/core/httpx_transport.py`: HTTP/2, timeout, origem HTTPS,
  cookie jar surdo e isolamento de cabecalhos de autenticacao.
- `src/trt_extractor/core/session_pool.py`: cache por tribunal/credencial,
  renovacao single-flight e invalidação segura.
- `src/trt_extractor/classify/tipo_pje.py`: camada deterministica para mapeamento
  explicitamente fornecido.
- `tests/`: fixtures sinteticas, bloqueio outbound e cobertura dos componentes.
- `pyproject.toml` e CI: testes normais offline; `rede` e `portao` fora do CI.
- `src/trt_extractor/core/contracts.py`: patch mecanico separado, sem mudanca de
  assinatura, campo, enum ou valor, para satisfazer lint.

## 4. Testes

- Baseline inicial: 35 aprovados, 1 excluido.
- Testes adicionados: PDPJ, transporte, SessionPool, fixture, bloqueio de rede e
  classificacao por codigo.
- Resultado final: 164 aprovados, 1 excluido; `portao`: 1 aprovado, 164 excluidos.
- Ruff: aprovado; formatter: 51 arquivos formatados; mypy: 11 arquivos sem erros.
- `git diff --check`: aprovado. Varredura local de padroes de chave, bearer e CPF:
  sem ocorrencias.

## 5. Bugs encontrados

- HIGH: nenhum bug de producao confirmado.
- MEDIUM: CI mantinha um job `portao`, contrario a regra de mantê-lo fora do CI;
  corrigido e coberto pela selecao normal de marcadores.
- MEDIUM: o adapter poderia permitir sobrescrita do User-Agent por cabecalho extra;
  corrigido antes do gate.
- LOW: lint preexistente no contrato protegido; corrigido por patch mecanico
  documentado em `proposta-lint-contratos.md`.

## 6. Lacunas

| Lacuna | Estado |
| --- | --- |
| L1 sigilo | CLOSED como limite legal no adapter |
| L2 JSON antes do PDF | PARTIAL |
| L3 hrefTexto | OPEN; probe preparado |
| L4 duracao de sessao | OPEN |
| L5 teto de concorrencia | OPEN; software local testado, teto real nao medido |
| L6 TRT2/TRT13 | OPEN |
| L7 processos volumosos | OPEN |
| L8 governanca para volume | OPEN |

## 7. Estado das fases

- Fase 0: concluida conforme evidencia existente.
- Fase 1: PARTIAL; adapter local e fixtures existem, sem captura autorizada nova.
- Fase 2: comprovada pela evidencia preexistente; nao foi reexecutada contra rede.
- Fase 3: nao iniciada; exige PostgreSQL para provar a migration e restart.
- Fase 4: PARTIAL; somente camada 1 por codigo explicitamente mapeado.
- Fase 5: nao iniciada.
- Fase 6: nao iniciada.

## 8. Decisoes tomadas

- Nao derivar `hrefTexto`, nem interpretar JSON curto como geracao sem predicado
  injetado.
- Nao usar sequencia para escolher silenciosamente entre multiplos documentos.
- Nao inferir grau; o adapter exige mapeador fornecido pelo chamador.
- Nao construir fila em memoria que duplique a maquina de estados da migration.

## 9. Riscos

- Revisao cruzada independente do adapter e transporte ainda pendente.
- Nenhuma medicao de sessao, L2 ou L3 foi autorizada; os contratos permanecem
  conservadores onde a evidencia e insuficiente.
- Sem PostgreSQL local nao ha prova de `SKIP LOCKED`, transicoes duraveis ou
  retomada apos queda.
- Toda sessao real deve permanecer fora do repositorio e nascer exclusivamente do
  handshake humano autorizado.

## 10. Proximas 10 tarefas

1. Revisar adapter e transporte por agente independente. Aceite: parecer com
   achados por severidade e referencias de linha.
2. Disponibilizar PostgreSQL descartavel com a migration. Aceite: schema aplicado
   sem edicao da migration.
3. Implementar repository de jobs sobre esse schema. Aceite: idempotencia pela
   chave unica e testes reais de claim com `SKIP LOCKED`.
4. Testar reinicio de worker. Aceite: trabalho duravel retorna sem duplicar PDF e
   terminal nao reabre.
5. Definir origem e permissao da chave para storage state. Aceite: decisao humana
   de segredo e modelo de ameaca aprovado.
6. Implementar persistencia de sessao somente apos a decisao. Aceite: atomica,
   permissao restrita, corrupcao tratada e sem chave privada.
7. Executar probe L2 autorizado. Aceite: ficha sanitizada distingue PDF, geracao e
   erro sem corpo bruto.
8. Executar probe L3 autorizado. Aceite: categoria de texto registrada sem URL,
   token, cookie ou texto integral.
9. Validar contraste TRT2/TRT13 em baixa taxa autorizada. Aceite: evidencia
   sanitizada de compatibilidade ou excecao documentada.
10. Definir governanca conservadora de volume. Aceite: limites configuraveis por
    tribunal, responsavel, auditoria e criterio de suspensao.
