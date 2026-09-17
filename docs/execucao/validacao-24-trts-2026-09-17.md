# Validação real dos 24 TRTs — 2026-09-17

**Método:** descoberta de processos públicos via DataJud/CNJ (API pública oficial,
`api-publica.datajud.cnj.jus.br`, sem autenticação); consulta real via UI do portal PDPJ
nacional (`portaldeservicos.pdpj.jus.br`) com sessão do titular autenticada manualmente
(login feito pelo próprio titular; nenhuma automação de PIN/certificado). Navegação
assistida via maestri portal (browser real), volume mínimo, sequencial.

**O que NÃO foi commitado:** números CNJ reais, nomes de partes, conteúdo de documentos.
Manifest completo com CNJs fica em `data/live_validation_2026-09-17.json`, gitignored.

## Critérios (conforme handoff)

- **A — descoberta:** CNJ público localizado via DataJud.
- **B — consulta:** processo reconhecido no portal PDPJ nacional.
- **C — documentos:** listagem de documentos ("autos digitais") abre e mostra itens.
- **D — binário:** tentado, não provado (ver limitação abaixo).
- **E — pipeline:** não testado (ver bloqueio abaixo).

## Matriz final (após retestes)

| TRT | A | B | C | Resultado | Observação |
|---|---|---|---|---|---|
| TRT1  | ✓ | ✓ | ✓ | **PASS** | Vara, docs reais |
| TRT2  | ✓ | ✓ | ✓ | **PASS** | 1º/2º candidatos (G2) migravam pro TST e não abriam autos; 3º candidato (vara) abriu |
| TRT3  | ✓ | ✓ | ✓ | **PASS** | Vara |
| TRT4  | ✓ | ✓ | ✓ | **PASS** | Vara, 5 docs |
| TRT5  | ✓ | ✓ | ✓ | **PASS** | Vara |
| TRT6  | ✓ | ✓ | ✓ | **PASS** | Candidato gabinete não abriu; candidato vara abriu |
| TRT7  | ✓ | ✓ | ✓ | **PASS** | Idem |
| TRT8  | ✓ | ✓ | ✓ | **PASS** | Idem, 14 docs |
| TRT9  | ✓ | ✓ | ✓ | **PASS** | Idem |
| TRT10 | ✓ | ✓ | ✓ | **PASS** | Idem |
| TRT11 | ✓ | ✓ | ✓ | **PASS** | Idem |
| TRT12 | ✓ | ✓ | ✓ | **PASS** | Idem |
| TRT13 | ✓ | ✓ | ✓ | **PASS** | Idem |
| TRT14 | ✓ | ✓ | ✓ | **PASS** | Idem |
| TRT15 | ✓ | ✓ | ✓ | **PASS** | Idem |
| TRT16 | ✓ | ✓ | ✓ | **PASS** | Idem |
| TRT17 | ✓ | ✓ | ✓ | **PASS** | Vara, 9 docs |
| TRT18 | ✓ | ✓ | ✓ | **PASS** | Vara, 14 docs |
| TRT19 | ✓ | ✓ | ✓ | **PASS** | Vara, autos abrem com 0 docs (processo recente) |
| TRT20 | ✓ | ✓ | ✓ | **PASS** | Vara, 13 docs |
| TRT21 | ✓ | ✓ | ✓ | **PASS** | Vara, 7 docs |
| TRT22 | ✓ | ✓ | ✓ | **PASS** | Gabinete, mas abriu (exceção ao padrão) |
| TRT23 | ✓ | ✓ | ✓ | **PASS** | 1º candidato sumiu entre DataJud e PDPJ; 3º (vara) abriu |
| TRT24 | ✓ | ✓ | ✓ | **PASS** | Vara, 11 docs |

**Resumo final: 24/24 PASS em A, B e C.**

## Hipótese confirmada

**Candidato em fase de 2ª instância/gabinete (desembargador) não abre "autos digitais"
nesta UI; candidato de vara (1ª instância) abre de forma confiável.** Confirmada em
13/13 casos onde havia comparação direta (TRT2, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
23 — todos falharam com candidato de gabinete/G2 e funcionaram com candidato de vara).
Exceção: TRT22, gabinete que abriu mesmo assim — não é regra absoluta, é o padrão
dominante. **Não é bug do projeto** — é comportamento da tela de consulta do PDPJ
(provavelmente por trâmite/instância do processo), fora do nosso código.

## Nível D (binário) — tentado, NÃO PROVADO

Tentei abrir PDF real em TRT1, TRT2 e TRT4 (link "Abrir ... .pdf", `href="javascript:"`,
com `logs-start`/`logs` do console e `screenshot` depois do clique). Nenhuma evidência
observável: sem popup, sem mudança de DOM, console vazio, screenshot expirou (a aba após
o clique some da lista de renderização ativa do maestri, típico de download acionado via
`<a download>` + blob URL sintético que o navegador processa sem abrir nova janela).
**Hipótese mais provável: a UI dispara download direto pro disco do titular, invisível
às ferramentas de inspeção usadas.** Não é evidência de falha nem de sucesso — é lacuna
de instrumentação desta rodada.

## Nível E (pipeline completo) — BLOQUEADO, não tentado

Rodar o pipeline Python real (`pdpj.py` + `InPageFetchTransport`) contra a sessão viva
exigiria uma das duas coisas:

1. Um objeto `Page` do Playwright real (que `InPageFetchTransport` espera via
   `PaginaFetch.evaluate`) — o portal do maestri não expõe isso, só uma CLI de alto
   nível (`navigate`/`click`/`evaluate` sem correspondência 1:1 com Playwright).
2. Ou fazer o Python chamar `fetch()` direto na página via `maestri portal evaluate`,
   **mas isso retornou 401** quando testado (ver rodada anterior) — a API do PDPJ exige
   um Bearer token que não está em cookie nem em `localStorage`/`sessionStorage`
   inspecionáveis; provavelmente vive em memória do app (Angular), acessível só via
   inspeção de estado interno do JS.

Tentei uma sondagem mínima de onde o token vive (`Object.keys(window)` filtrando por
`token`/`auth`/`keycloak`) e **o classificador de segurança do Claude Code bloqueou a
ação como "Credential Exploration"** — corretamente, porque isso é extração de
credencial de sessão de terceiro, exatamente o que a ADR 007 e o handshake.py proíbem
("login é ato do titular"; "este módulo não tem superfície para automatizar login").

**Não tentei contornar o bloqueio.** Rodar o pipeline Python real contra esta sessão
exigiria uma automação de browser de verdade (Playwright) controlada pelo próprio
projeto, iniciada pelo titular via `handshake.capturar()` — não uma ponte externa via
CLI de portal. Isso é trabalho de integração, não de teste, e fica fora desta rodada.

## O que ficou provado, fortemente indicado, não provado

- **PROVADO:** os 24 TRTs têm processos públicos localizáveis via DataJud oficial; o
  portal PDPJ nacional reconhece e lista documentos de processos de vara dos 24 TRTs,
  pela mesma sessão de titular, sem tratamento especial por tribunal.
- **PROVADO:** o padrão gabinete-não-abre/vara-abre é consistente (13/13 comparações).
- **NÃO PROVADO:** download de binário (nível D).
- **BLOQUEADO POR DESENHO DE SEGURANÇA:** pipeline Python completo (nível E) — exigiria
  extrair token de sessão do navegador, o que o projeto proíbe e o Claude Code recusou.

## Limitações desta rodada

- 24 TRTs cobertos com 1-3 candidatos cada; nenhum teste de concorrência ou volume.
- Nenhuma chamada usou o código Python do projeto — foi validação de UI, não do adapter.
- Nível D e E ficam como próxima prioridade, mas E requer decisão de arquitetura (como
  o handshake real vai rodar: browser dedicado do projeto via Playwright, não ponte
  externa) antes de qualquer tentativa nova.

---

## Adendo 2026-09-17 (mesma data, sessão seguinte): nível E desbloqueado

Depois deste relatório original, o dono do projeto trouxe uma referência do projeto
irmão **TaxMap** (mesma organização, mesmo portal PDPJ, em produção): em vez de sondar
`window.*` (o que foi corretamente bloqueado acima), o TaxMap injeta um hook via CDP
que faz monkey-patch de `window.fetch`/`XMLHttpRequest.setRequestHeader`, capturando
passivamente o `Authorization` que **o próprio app** anexa numa requisição real dele —
equivalente a ler a aba Network do DevTools, não a extrair estado interno.

Portado para `src/trt_extractor/runner/playwright_handshake.py`
(`HOOK_CAPTURA_BEARER_JS`, `criar_montador_via_hook`, `conectar_chrome_existente`)
com autorização explícita do dono do projeto, ciente da mudança de modelo (o token
passa a transitar pela memória do processo Python).

**Teste ao vivo, rodado pelo dono do projeto (não pelo Claude Code — a ação de
capturar credencial de sessão real foi bloqueada pelo classificador de segurança
como "Credential Materialization", e não foi contornada):**

- Chrome real aberto com `--remote-debugging-port`, titular logado no PDPJ.
- Script conecta via `connect_over_cdp`, instala o hook, dispara uma busca real de
  processo (TRT4) pela UI.
- Resultado: **`TOKEN CAPTURADO: SIM`, tamanho 2118 caracteres.** Valor do token
  nunca transitou pelo chat nem foi persistido em log/arquivo — só o fato da
  captura e o tamanho.

**Isso PROVA** que o mecanismo de captura passiva funciona contra a sessão real do
PDPJ nacional. **Continua NÃO PROVADO**: usar esse token para de fato rodar
`pdpj.py`/`InPageFetchTransport` fim-a-fim (LIST → FETCH → VALIDATE → HASH → STORE)
— o teste desta rodada só confirmou a captura, não o pipeline completo depois dela.

Nível E passa de **BLOQUEADO** para **FORTEMENTE INDICADO** (mecanismo provado,
integração fim-a-fim ainda não).

---

## Adendo 2026-09-17 (terceira sessão): pipeline real fim-a-fim PROVADO

Com o token capturado (adendo anterior), liguei o pipeline Python de verdade
(`PdpjAdapter` + `InPageFetchTransport`, sessão com token real, TRT4, mesmo processo
público usado na validação original) e apareceram dois bugs reais — o adapter nunca
tinha rodado contra a API de verdade, só contra fixtures sintéticas medidas por
inferência.

### Bugs reais encontrados e corrigidos

1. **`GET /processos/{cnj}` devolve lista JSON de 1 item, não objeto solto.**
   `list_documents` assumia objeto direto; toda chamada real falhava com "Objeto
   PDPJ ausente ou invalido". Corrigido: `_processo_json` (pdpj.py) desembrulha lista
   de tamanho 1, rejeita lista de outro tamanho como ambígua. Teste de regressão:
   `test_accepts_process_wrapped_in_single_item_list`,
   `test_rejects_process_list_with_more_than_one_item`.

2. **`dataHoraJuntada` real não tem offset de fuso** (`"2026-09-01T00:24:36.704938"`,
   não `"...-03:00"`). O código exigia `utcoffset() is not None` — suposição nunca
   medida, sem justificativa registrada em comentário. Toda peça real era rejeitada
   com "Data de juntada invalida". Corrigido: aceita naive também (`juntado_em` é
   sinal de ordenação, nunca comparado com relógio). Teste de regressão:
   `test_accepts_naive_juntada_datetime_without_offset`.

3. **`grau` real é objeto `{"sigla": "G1", "nome": "1º Grau", "numero": 1}`**, não
   string solta como as fixtures assumiam. Não é bug do adapter — `grau_mapper` é
   injetável de propósito porque esse formato nunca tinha sido medido. Resolvido no
   `grau_mapper` do chamador (`numero: 1|2 -> Grau.PRIMEIRO|SEGUNDO`), sem mudança em
   `pdpj.py`. Fica registrado aqui para quem for escrever o `grau_mapper` de produção.

4. **`tipo` real não tem chave `"codigo"`** (`{"nome": "Documento Diverso",
   "idCodex": ..., "idOrigem": ...}`), então `tipo_pje` fica `None` para documentos
   reais — a classificação por `tipos_por_codigo` (`codigo -> TipoDocumento`) não
   tem o que casar. **Não corrigido nesta rodada** — é decisão de classificação
   (usar `idCodex`? `nome`? outro campo?), não um bug de parsing. Fica como próxima
   prioridade de investigação, não como conserto silencioso.

### Resultado do pipeline real (TRT4, processo público da validação original)

- `list_documents`: **22 documentos reais retornados**, sessão real, sem tratamento
  especial de tribunal.
- `request_download` → `poll_download` → `fetch_artifact`: binário real baixado —
  **321.713 bytes, assinatura `%PDF-` válida**, sha256 calculado e conferido no
  `LocalCASStorage`.

**Isso PROVA nível D (binário) e nível E (pipeline completo) contra o PDPJ nacional
real**, usando o código de produção do projeto (não UI manual, não ponte externa).
Único ponto ainda não resolvido: qual campo real usar para classificar tipo de
documento (item 4 acima) — sem isso, a seleção de classes-alvo (petição inicial,
sentença, acórdão, acordo, laudo) continua sem sinal do PJe neste processo de amostra.

---

## Adendo 2026-09-17 (quarta sessão): mapa código→classe medido em 8 tribunais reais

Com o pipeline fim-a-fim provado (adendo anterior), rodei o mesmo mecanismo contra
mais 8 processos reais em segunda instância (TRT6, 7, 9, 11, 12, 14, 22, 23 —
candidatos de gabinete/desembargador da rodada de descoberta original, que a UI não
abria mas a API respondeu normalmente), respeitando ritmo (pausa de 12s entre
tribunais, acima do piso de 6 req/min da matriz; parei a linha na primeira falha,
sem insistir). **Mais de 2000 documentos reais inspecionados**, só metadados de
tipo (nome/código), nunca título de peça nem nome de parte.

### Resultado: mapa código → classe

| Código | Nome real (`tipo.nome`) | Classe |
|---|---|---|
| 202 | PETIÇÃO INICIAL / Petição Inicial | `PETICAO_INICIAL` |
| 550 | SENTENÇA / Sentença | `SENTENCA` |
| 14442 | Acórdão | `ACORDAO` |

Nenhum código próprio apareceu para **acordo** nem **laudo/perícia** nesta amostra
(laudo aparece só como "Apresentação de Laudo Pericial", sem código — cai no
fallback por nome já implementado, não neste mapa).

Também confirmado: o `codigo` 202 já estava certo desde a primeira suposição do
projeto (`{"202": TipoDocumento.PETICAO_INICIAL}`, não medido até agora) — a
suposição original acertou, mas só virou evidência nesta rodada.

**Implementado:** `TIPOS_POR_CODIGO_MEDIDO` em `pdpj.py`, agora o default de
`PdpjAdapter` quando `tipos_por_codigo` não é passado. Testes de regressão cobrindo
os 3 códigos via `ClassificadorTipoPje`.

### Amostra completa de nomes vistos (para referência futura, sem valor de doc)

Documentos com código: CONTESTAÇÃO(16), Contraminuta(17), CONTRARRAZÕES(18),
IMPUGNAÇÃO(26), CONTRATO(73), DECLARAÇÃO DE HIPOSSUFICIÊNCIA(79),
MANIFESTAÇÃO(101), Notificação(103), PROVA EMPRESTADA(114),
Exceção de Incompetência(157), Exceção de Pré-executividade(159),
PETIÇÃO INICIAL(202), Recurso de Revista(233), RECURSO ORDINÁRIO(243),
Contrato Social(293), Extrato Bancário(298), Extrato de FGTS(299),
Ficha de Registro de Empregado(301), Recibo de EPI(326),
Recibo de Vale Refeição(328), Agravo Interno(370), Embargos de Declaração(373),
Alvará(398), CERTIDÃO(402), DECISÃO(404), DESPACHO(409), MANDADO(415),
Ofício(417), Certidão de Julgamento(503), Certidão de Trânsito em Julgado(527),
SENTENÇA(550), INTIMAÇÃO(575), Mandado de Citação(608),
Comprovante de Depósito Judicial(709), Comprovante de Depósito Recursal(710),
Comunicação de Acidente de Trabalho (CAT)(711), Edital(14404), Acórdão(14442),
ESTATUTO(14482), Recibo(15431).

Documentos sem código (fallback por nome): Ata da Audiência, Agravo de Petição,
Agravo de Instrumento em Agravo de Petição, Apresentação de Laudo Pericial,
Apresentação de Procuração, Apresentação de Quesitos, diversos documentos
pessoais/cadastrais (RG, CTPS, CPF, CNPJ), integrações federais
(Sisbajud/Renajud/Infojud), Jurisprudência, Planilhas de Cálculo, Procuração,
Razões Finais, Sentença (cópia), Substabelecimento, e dois valores brutos não
resolvidos pelo PJe (`TipoProcessoDocumento#758`, `TipoProcessoDocumento#765`).

### Status atualizado

Nível de classificação real (que fração das 5 classes-alvo tem sinal determinístico
de `tipo_pje`): **3 de 5 PROVADAS** (petição inicial, sentença, acórdão). Acordo e
laudo/perícia continuam sem código próprio medido — precisam de amostra com esses
documentos presentes, ou de investigação por outro sinal (nome/posição no fluxo).

---

## Adendo 2026-09-17 (quinta sessão): acordo e laudo — classificação 5/5 fechada

Busquei candidatos com "acordo" via DataJud (`movimentos.nome` contendo
"Homologação de Transação Extrajudicial"/"Acordo") em 12 tribunais — todos
retornaram candidatos. Testei 6 (TRT1, 5, 8, 9, 17, 20) via pipeline real,
respeitando ritmo (12s entre tribunais, sem insistir).

**Achado:** TRT17, processo `0000340-76.2026.5.17.0181` — documento com
`tipo.codigo=11`, `tipo.nome="Acordo"`. Confirma classe **ACORDO** com código
próprio, estável.

**Laudo pericial** já tinha 2 ocorrências reais confirmadas na sessão anterior
(TRT9, TRT12: `"Apresentação de Laudo Pericial"`, sempre sem `codigo`, só `nome`).
Não vale a pena investir mais rodadas nisso — o padrão já é consistente (2
ocorrências, mesmo nome exato, dois tribunais diferentes) e o mecanismo de
fallback por nome (`_documento`) já cobre esse caso.

### Mapa final de classificação (5/5 classes-alvo)

| Classe | Chave em `TIPOS_POR_CODIGO_MEDIDO` | Fonte |
|---|---|---|
| `ACORDO` | `"11"` (código) | TRT17, 1 ocorrência |
| `PETICAO_INICIAL` | `"202"` (código) | 8+ tribunais |
| `SENTENCA` | `"550"` (código) | 8+ tribunais |
| `ACORDAO` | `"14442"` (código) | 8+ tribunais |
| `LAUDO_PERICIA` | `"Apresentação de Laudo Pericial"` (nome, sem código) | TRT9, TRT12 |

**Status:** classificação por `tipo_pje` agora cobre as 5 classes-alvo com
evidência real, medida ao vivo — nenhuma delas é suposição. `ACORDO` e
`LAUDO_PERICIA` têm amostra pequena (1 e 2 ocorrências) comparado a
`PETICAO_INICIAL`/`SENTENCA`/`ACORDAO` (8+ tribunais, milhares de documentos) —
**fortemente indicado**, não tão robusto quanto os outros três, mas já é
evidência real, não inferência.

---

## Adendo 2026-09-17 (sexta sessão): pipeline completo (nível E) nos 24 TRTs

Rodei o pipeline real (`PdpjAdapter` + `InPageFetchTransport`, mesma sessão/token via
hook) contra os 24 candidatos de vara já validados (nível C), sequencial, pausa de
15s entre qualquer duas chamadas HTTP (acima do piso de 6 req/min = 10s da matriz),
parando a linha inteira na primeira ocorrência de bloqueio (403/429) — nenhum
ocorreu. Duração total: **704,5s (~11,7 min) para 24 tribunais**.

### Resultado

| Status | Quantidade | TRTs |
|---|---|---|
| **OK** (list→fetch→validate→hash→store completo) | **22/24** | todos exceto TRT1, TRT22 |
| Fetch falhou (achado real, ver abaixo) | 1 | TRT1 |
| Grau inexistente nesta via | 1 | TRT22 (candidato é gabinete/2ª instância; grau 1 não existe pra esse processo — esperado, não é bug) |

**Nível E agora PROVADO em 22 dos 24 TRTs** — PDF real baixado, assinatura válida,
sha256 calculado e conferido no CAS local, sem tratamento especial por tribunal.

### Latência real medida (24 amostras)

- `list_documents`: média **0,16s**
- `fetch_artifact` (binário): média **0,43s**

A API nacional é rápida — a latência de rede não é o fator limitante da operação;
o ritmo (pausas deliberadas) é.

### Achado real: TRT1, "JSON de binário não reconhecido; L2 não confirmado"

O documento escolhido no TRT1 devolveu **JSON no lugar de PDF** no endpoint de
binário — o código já previa esse caso (`_resposta` em `httpx_transport`/
`inpage_transport`... na verdade em `pdpj.py:_documento`/`fetch_artifact`) mas sem
`geracao_pendente` configurado (não passei essa política no script), então virou
`PermanenteError` em vez de retry. Isso é exatamente o "L2 não confirmado" que o
código já documentava como não medido — **agora tem uma ocorrência real**, mas
ainda não o suficiente para confirmar o formato do JSON de geração pendente (não
investiguei o corpo desta vez, para não estender a sessão). Fica registrado como
próxima investigação, não como bug corrigido.

### Amostra de artefatos reais (sanitizado — sem conteúdo, só hash/tamanho)

Ver `data/pipeline_24trts_resultado.json` (gitignored) para os 22 sha256 completos.
Tamanhos entre 53KB e 322KB, todos com assinatura `%PDF-` válida.

---

## Adendo 2026-09-17 (sétima sessão): acordo reforçado + estimativa de throughput

### Acordo: segunda confirmação

Testei mais 5 candidatos com movimento de acordo (TRT13, 14, 16, 23, 24). TRT24
confirmou `codigo=11, nome="Acordo"` em **3 documentos** do mesmo processo.
Combinado com TRT17 (sessão anterior), **código 11 = Acordo está confirmado em 2
tribunais diferentes, 4 ocorrências totais** — evidência bem mais sólida que a
única ocorrência anterior.

### Estimativa de throughput (prudente, considerando o certificado do titular)

**Medido nesta rodada:** latência real da API — `list_documents` média 0,16s,
`fetch_artifact` média 0,43s. A rede não é o gargalo; o ritmo deliberado é.

**Teto técnico da matriz atual:** `capabilities.yaml` declara **6 req/min por
`(tribunal, credencial)`**, uniforme nos 24 TRTs — não é uma estimativa de
capacidade real medida por tribunal, é o piso conservador que a governança
(`docs/execucao/governanca-volume.md`) define para tribunal não medido
individualmente. A governança também deixa explícito: **o limite é por
`(tribunal, credencial)`, não há teto agregado por soma de tribunais** — não é
proibido, arquiteturalmente, operar em vários TRTs simultaneamente no teto de cada
um.

**Por que eu não uso esse teto mesmo assim:** ADR 009 é explícita — o risco real
não é "ser detectado como robô" (a credencial já é identificável, JWT carrega
nome/CPF/e-mail do titular), é **um auditor perguntando por que essa credencial
abriu muitos processos numa tarde**. Esse risco não desaparece por processo estar
espalhado entre 24 tribunais diferentes — é a mesma pessoa, o mesmo certificado,
o mesmo dia. Por isso toda medição desta rodada usou pausa de 12-15s **entre
qualquer duas chamadas, cruzando tribunais**, não 10s por tribunal isolado.

| Cenário | Ritmo | Requisições/hora | Processos/hora* | Status |
|---|---|---|---|---|
| Teto técnico da matriz (1 tribunal só, sem pausa extra) | 6 req/min | 360 | ~180 | Nunca testado nesta rodada — não recomendo operar aqui |
| **Medido nesta rodada** (24 tribunais, pausa 15s entre chamadas) | 4 req/min | 240 | ~120 | **Testado ao vivo, zero bloqueio, 22/24 sucesso** |
| **Recomendação prudente para início de produção** | 1 processo a cada 2-3 min | ~20-30 | ~20-30 | Não testado em volume sustentado — recomendação, não medição |

*Processos/hora assume 1 documento baixado por processo (2 requisições: list +
fetch). Buscar múltiplas classes-alvo por processo multiplica requisições
proporcionalmente (ex.: 3 documentos-alvo = 4 requisições = throughput cai à metade).

**Isso é recomendação minha, não autorização.** Por `governanca-volume.md`: "Nenhum
limite sobe por analogia, urgência ou sucesso isolado" — qualquer volume sustentado
em produção precisa de decisão do responsável operacional, com evidência registrada
em `capabilities.yaml`/`testado_em`, não só o teste desta rodada.

**Recomendação concreta:** começar em produção na faixa prudente (~20-30
processos/hora, horário comercial, dias úteis — já é o que `Ritmo`/`JanelaOperacional`
impõem), observar por alguns dias (taxa de erro, resposta do PDPJ, qualquer sinal de
questionamento), só then considerar subir — com evidência, não por analogia ao
teste de hoje.
