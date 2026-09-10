# Continua_codex — briefing de continuação do `trt-extractor`

> **Para quem pega o projeto daqui (Codex ou humano):** este arquivo é o mapa completo.
> Lê ele inteiro antes de tocar código. Ele consolida contexto, objetivo, tudo que já foi
> decidido e medido, a arquitetura, o que está provado, o que falta, e como continuar sem
> quebrar os invariantes. Onde ele resume, o detalhe está nas ADRs (`docs/decisions/`) e
> nas evidências (`research/evidencia/`).
>
> Repositório (privado): `https://github.com/NicolasMBastos/trt-extractor`
> Estado: **fases 0 e 2 concluídas; fase 1 destravada e em implementação.** 224 testes
> verdes, 2 excluídos. Ruff, format e mypy limpos. CI verde no PR #1.
> Data-base: **2026-09-10** (revisão de 2026-09-08/10; a base original é de 2026-09-03).
>
> **Se você é o próximo orquestrador, leia também
> [`docs/execucao/handoff-orquestrador.md`](docs/execucao/handoff-orquestrador.md)** —
> este arquivo é o mapa do *projeto*; aquele é o runbook de *como tocar o trabalho aqui*
> (estado do canvas, quais agentes funcionam, armadilhas de ambiente, contrato de tarefa).

---

## 1. Contexto do projeto

Escritório de advocacia (Andrade Maia) precisa **baixar em volume os PDFs de peças
processuais trabalhistas** dos TRTs. Não é um projeto de metadados — o **entregável é o
binário** (o PDF). Metadado só existe para saber *qual* arquivo buscar e *onde* guardar.

Cinco classes de documento importam:

1. **Petição inicial**
2. **Acórdão**
3. **Sentença**
4. **Acordo**
5. **Laudo/perícia** (secundário — confirmar prioridade; entra na fase 4 ou depois)

**Foco primário: TRT4 (Rio Grande do Sul)** — onde o escritório atua e há volume real.
TRT2 e TRT13 são alvos de contraste, só depois que o TRT4 fechar ponta a ponta.

Ambiente: **Windows 10**, Python fixado em **3.12** (a máquina tem 3.14; wheels atrasam —
ver `docs/arquitetura.md` D6). Orquestração via **Maestri** (canvas de agentes). Existe um
projeto irmão, **`TaxMap-main`**, na mesma máquina, em produção, mesmas credenciais — é
arte prévia legítima e a principal fonte de inspiração técnica.

## 2. Objetivo

Extrair, com **volume moderado e legítimo** (não cargas massivas — há tempo/tenant para
scrapear devagar), as cinco classes de documento dos processos-alvo, classificá-las,
deduplicá-las e arquivá-las de forma idempotente e auditável.

## 3. O caminho de aquisição — RESOLVIDO e PROVADO

Este é o achado central do projeto, medido ao vivo (evidência:
`research/evidencia/pdpj-nacional-H1-CONFIRMADA-2026-09-03.md`).

### A via: API nacional do PDPJ (Portal de Serviços / Jus.br)

```
https://portaldeservicos.pdpj.jus.br/api/v2/processos/{numero_cnj}
```

- **É NACIONAL.** Um login com certificado, chaveado pelo número CNJ, alcança **os 24
  TRTs**. Não são 24 integrações — é **uma**. (ADR 001.)
- Retorna, numa resposta JSON, os **metadados completos + a lista de todos os documentos**,
  cada um com o campo **`hrefBinario`**.
- `GET .../processos/{cnj}/documentos/{uuid}/binario` → **devolve o PDF** (`%PDF`).
  **Isto foi baixado de verdade**, incluindo a petição inicial (561 KB) de um processo
  real de terceiro, público, do TRT4.

### Por que funciona para processo de terceiro

O acesso é por **publicidade** do processo, imposta pela plataforma, não por vínculo
(ADR 004). Processo público abre para qualquer identidade autenticada, de qualquer TRT.
Processo em **segredo de justiça não abre** — e isso é fronteira dura, respeitada, nunca
contornada.

### Estrutura de cada documento na resposta (ouro para o projeto)

```
sequencia      ordem de juntada — o 1º documento É a petição inicial (sinal camada 2)
dataHoraJuntada
idCodex        id nacional do documento
idOrigem       id no tribunal de origem
nome           ex.: "Peticao Inicial.pdf"
nivelSigilo    PUBLICO | ... — filtro de segredo POR documento
tipo:          { codigo, nome, ... }  CODEBOOK NACIONAL. 202 = Peticao Inicial
hrefBinario    /processos/{cnj}/documentos/{uuid}/binario   → o PDF
hrefTexto      /processos/{cnj}/documentos/{uuid}/texto      → camada de texto
```

Dois presentes que isto trouxe:
- **`tipo.codigo` é nacional** — a classificação camada 1 fica confiável nos 24 TRTs, bem
  melhor que o `tipoDocumento` inconsistente que o briefing temia.
- **`hrefTexto` pode dispensar OCR** — se a API serve a camada de texto, OCR vira exceção.
  **A CONFIRMAR.**

### 3.1 Decisão de estratégia (2026-09-08, do dono do projeto)

**A fonte é o portal autenticado, e é ele que dá "tudo".** Autentica quando precisa,
mantém a sessão, vai devagar, pega tudo. Três consequências que não se renegociam:

1. **Navegador é obrigatório — para autenticar, não para raspar.** O handshake por
   certificado só existe em browser. Depois dele, o conteúdo sai de dentro da página
   autenticada, via `InPageFetchTransport`.
2. **Raspar DOM está descartado.** O portal já entrega a lista de documentos **tipada**,
   com link direto do binário. Raspar a tela dá os mesmos bytes, mais devagar, quebrando
   a cada mudança de layout — e perde `tipo.codigo` e `nivelSigilo`, que são exatamente o
   que faz a classificação camada 1 e o respeito ao sigilo funcionarem.
   **`api/v2/...` não é "API externa": é o backend do próprio portal**, a mesma chamada
   que a página faz ao clicar. Usá-la *é* raspar o portal do jeito certo.
3. **Lentidão é requisito, não concessão.** Tempo não é restrição do escritório. O recurso
   escasso é a credencial do titular (ADR 007) — ir devagar protege o recurso escasso.

Proposta escrita em `docs/execucao/proposta-adr-008-transporte-por-canal.md`.
**Pendente:** promover a `docs/decisions/008-...` (o diretório é do Maestro).

### 3.2 O que existe SEM autenticar — medido em 2026-09-08

Resposta curta: **100% da triagem, ~0% da petição inicial.** Detalhe completo em
`docs/canais-publicos/`. Isto **não substitui** a via autenticada — **protege** ela,
tirando dela o volume repetitivo de descoberta e acompanhamento.

| Canal | Autenticação | Entrega | Estado |
|---|---|---|---|
| **DataJud** `api-publica.datajud.cnj.jus.br/api_publica_trt{1..24}/_search` | chave **pública** do CNJ | metadado. **Zero binário** | confirmado por doc |
| **DJEN** `comunicaapi.pje.jus.br/api/v1/comunicacao` | **nenhuma** | sinal tipado de peça + certidão em PDF. **Zero peça** | **medido** |
| **FALCÃO** `jurisprudencia.jt.jus.br` | nenhuma | acórdão nacional, inteiro teor | **medido** |
| Consulta pública PJe | nenhuma | barrada por captcha | fechado por decisão |
| **Codex** (CNJ) | convênio + custeio | conteúdo de peças | não iniciado |

Por classe: **petição inicial 0%** (estrutural — não é publicada em lugar nenhum),
acórdão alto (FALCÃO), **sentença ~0%** (o DJEN serve certidão, não peça), acordo ~0%,
laudo 0%.

Dois achados que valem para a arquitetura:

- **FALCÃO é nacional.** `jurisprudencia.jt.jus.br/jurisprudencia-nacional/`, sem login,
  API literalmente chamada `no-auth`. Acórdão vira **1 integração, não 24**. Mas a busca é
  **full-text sobre o CNJ, não lookup chaveado**: devolveu 2 resultados, um de outro
  processo. Casar por **igualdade exata** no campo de número, **nunca por ranking**.
- **A consulta pública também é uniforme nos 24** (`pje.trt{N}.jus.br/consultaprocessual/`,
  21 confirmados servindo a mesma SPA) — e é justamente a que o captcha barra.

## 4. O transporte — RESOLVIDO para o PDPJ, e NÃO generaliza

Hipótese de que o WAF exige um navegador real: **FALSA, com correção** (ADR 002, adendo 2).

| Cliente | Resultado |
|---|---|
| `httpx` HTTP/1.1, sem User-Agent | **403 Forbidden** |
| `httpx` **`http2=True` + User-Agent de browser** | **200** — listagem e binário |

**Conclusão para o PDPJ:** `HttpxTransport` (com `http2=True` e UA de Chrome) faz todo o
volume da Via 0. Não precisa de fazenda de navegador.

### 4.1 A medição que mostrou que isto NÃO generaliza (2026-09-08)

No FALCÃO, o comportamento é o **inverso**:

| Canal | `httpx` http2+UA | `fetch` in-page |
|---|---|---|
| PDPJ nacional (`api/v2`) | **200** em listagem e binário | não necessário |
| FALCÃO (`no-auth/pesquisa`) | **403** `"Tentativa inválida de acesso ao sistema"` | responde |

Dois canais públicos brasileiros, transportes incompatíveis, mesma máquina, mesma hora.

**Regra que sai disto:** o transporte é **propriedade do canal**, medido por canal, nunca
herdado. Nenhum canal novo herda o transporte de outro, nem por analogia, nem por "é tudo
`jus.br`". Canal sem medição fica `desconhecido` em `capabilities.yaml` e **não roda em
volume**.

Isto não corrige a ADR 002 — confirma que ela era uma medição *do PDPJ*, e que ter
`Transport` como `Protocol` separado do `Adapter` já era a decisão certa por esta exata
razão. O contrato estava à frente da evidência.

`InPageFetchTransport` foi implementado em 2026-09-08 (`core/inpage_transport.py`) e não
é evasão: em vez de forjar um browser, usa o browser de verdade — o mesmo padrão do TaxMap.

## 5. Autenticação e sessão — MEDIDO

- Login por **certificado A1** (todos os certificados da máquina são A1; ver ADR 003) via
  **PJeOffice Pro** → SSO **Keycloak** → cookies/JWT. O certificado é usado **uma vez, no
  handshake, localmente** — nunca viaja na requisição (ADR 007).
- **TTL da sessão: 8 horas no PDPJ nacional**, 60 min no PJe local do TRT4.
- MFA é **por dispositivo** (login raro, não a cada acesso) — é o que torna sessão
  persistente viável.
- Preservação de sessão: `storage_state` capturado, reaproveitado, renovado
  proativamente com single-flight (ADR 006).

### 5.1 Onde o `storage_state` fica — DECIDIDO e PROVADO (2026-09-08)

**DPAPI do Windows, escopo de usuário**, via `crypt32` por `ctypes`. Zero dependência
nova. Decisão do dono do projeto; era ela que bloqueava a fase 1.

- **Não há chave para gerenciar.** O SO deriva do perfil da conta Windows.
- **O arquivo só abre pela conta do titular, naquela máquina.** Copiar não adianta. É a
  ADR 007 imposta pelo SO em vez de por convenção.
- **A amarração à identidade é criptográfica, não uma checagem:** `(tribunal,
  credencial_id)` entra como **entropia secundária** do DPAPI, então estado da credencial
  A **não descriptografa** como B — o SO recusa antes de qualquer `if`.

Implementado em `core/session_store.py`. Há um teste que exercita o DPAPI de verdade e se
exclui fora do Windows (o CI é `ubuntu-latest`); ele **passou na máquina do titular** — o
estado não aparece em claro no disco e entropia errada não abre. A cifra é injetável para
que o resto da suíte rode em qualquer plataforma.

Outras propriedades, cada uma com teste: nome do arquivo é o sha256 da chave lógica (o
diretório não revela CPF, credencial, nem em quais TRTs o escritório atua); escrita
atômica; **ilegível devolve `None` e não apaga o arquivo** (ilegível é caso *normal* —
outro usuário, outra máquina, truncado — e apagar destruiria evidência); recusa raiz
dentro de árvore git.

## 6. Segurança e governança — A ESPINHA DORSAL (ADR 004 e 007)

**Estes invariantes não são negociáveis. Quem continuar o projeto os respeita.**

1. **O certificado nunca viaja na requisição.** Usado 1x no login, local, pelo PJeOffice.
   Fazer 30 ou 30.000 requisições é idêntico para o certificado. Nunca carregar chave
   privada em código.
2. **Toda requisição carrega a identidade completa do titular** (nome, CPF, e-mail, papéis
   no JWT). Cada acesso é atribuível, no servidor, àquele advogado. Este certificado é do
   **advogado do setor de TI, de uso compartilhado** — logo, todo acesso é juridicamente
   ato dele.
3. **`SIGILOSO` é terminal legítimo.** Registra, não faz retry, não entra na métrica de
   falha, não se tenta obter por outra via.
4. **ZERO evasão de detecção.** Sem spoof de fingerprint, sem rotação de UA/IP/proxy para
   despistar, sem simulação de mouse para vencer detecção comportamental. O TaxMap **não
   faz nada disso** (verificado) — ele reusa o navegador real do humano e vai devagar. É
   esse o padrão: não *parecer* humano, mas *ser* (sessão real, ritmo humano).
5. **Volume moderado, ritmo humano de verdade** — jitter entre peças, teto por hora bem
   abaixo do limite medido, horário comercial, backoff, circuit breaker por tribunal.
   O objetivo é ser um usuário leve e educado, não disfarçar um robô. Anti-detecção
   *aumentaria* o risco ao advogado, não reduziria.
   **Reforçado em 2026-09-08 (§3.1):** lentidão é **requisito**, não concessão. Tempo não
   é restrição do escritório, então não há troca a fazer aqui — ir devagar é grátis e
   protege o único recurso escasso.
   **Corolário operacional, já exercitado:** no `429` do FALCÃO a execução **parou**. Sem
   retry, sem backoff para insistir, sem trocar sessão, sem tentar outra via. Limite
   encontrado é limite respeitado e registrado, não obstáculo a vencer.
6. **Auditoria completa** — qual credencial, qual processo, qual peça, quando, resultado.
   Demonstra legitimidade; é o oposto de esconder.
7. **Governança pendente (bloqueia VOLUME, não bloqueia teste):** aprovação escrita do
   advogado titular + compliance para uso automatizado da credencial, com teto acordado.
   Para volume real, o caminho certo é **canal institucional** (convênio MNI / API PJ em
   nome do escritório), não espremer a credencial de uma pessoa.

## 7. Estrutura imaginada (arquitetura)

Camadas, de cima para baixo (contratos em `src/trt_extractor/core/contracts.py` — tipados,
sem implementação; **não editar sem pedir**):

```
TribunalAdapter   O QUÊ: authenticate, list_documents, request_download,
                         poll_download, fetch_artifact
      ↓ usa
Transport         O COMO: request / fetch_bytes
                  HttpxTransport (http2+UA) | InPageFetchTransport (navegador; não
                  implementar agora, fica no contrato como carta na manga)
      ↓ carrega
Session           QUEM: token, cookies, validade, credencial de origem
```

Pipeline:

```
[seed]      CNJs (DataJud, CSV do cliente, carteira própria/OAB)
[triagem]   via preferida ← capabilities.yaml; descarta processo sem peça-alvo
[sessão]    pool por (tribunal, credencial); handshake por certificado; renovação
[transport] httpx http2+UA (ou navegador estilo TaxMap)
[submit]    pede documentos filtrados pelos 5 tipos (via nacional: já vêm listados)
[poll]      só quando a geração é assíncrona (o /binario às vezes devolve JSON curto
            primeiro — tratar como "ainda não pronto / retry")
[fetch]     baixa o binário via hrefBinario
[split]     separa PDF consolidado, quando aplicável
[classify]  tipo.codigo (nacional) → sequência → keywords.yaml → LLM (desempate)
[store]     content-addressed sha256 (LocalCASStorage; S3 na fase 5) + metadados no Postgres
[ocr]       fila separada, só sem camada de texto (talvez dispensável via hrefTexto)
```

**Estado, não etapas.** Cada `(numero_cnj, grau, tipo_documento)` é uma linha com máquina
de estados explícita, validada por trigger no Postgres (`migrations/001_inicial.sql`):

```
PENDENTE → SUBMETIDO → GERANDO → BAIXADO → CLASSIFICADO → ARQUIVADO
              ↘ FALHA_TRANSIENTE (retry backoff)
              ↘ SIGILOSO / INEXISTENTE (terminais legítimos, fora da métrica de erro)
              ↘ FALHA_PERMANENTE (dead-letter)
```

Idempotência: chave `(numero_cnj, grau, tipo_documento)` para o job, `sha256` para o
binário. Dedup 1º/2º grau cai de graça do content-addressing.

## 8. O que já existe no repo

```
src/trt_extractor/core/contracts.py     TribunalAdapter, Transport, Session, Storage,
                                         Artefato, DocumentoRef, enums, erros — TIPADOS
src/trt_extractor/storage/local_cas.py  LocalCASStorage: sha256, fanout ab/cd, escrita
                                         atômica, idempotente — PROVADO na fase 2
migrations/001_inicial.sql              esquema + máquina de estados por trigger + views
                                         de métrica (SIGILOSO fora do erro)
capabilities.yaml                       24 TRTs; TRT4 medido (pdpj_api=ok, transporte=httpx,
                                         sessão 8h, autos locais exigem habilitação)
config/keywords.yaml                    5 classes; peças 1-3 com pesos de produção do
                                         TaxMap, 4-5 derivadas (não validadas)
scripts/probe_mni.py                    probe do WSDL MNI (achou: TRT4 exige convênio)
scripts/sanitizar_har.py                remove token/CPF/cookies de HAR antes de versionar
scripts/gerar_capabilities.py           gerador da matriz
docs/arquitetura.md                     arquitetura + divergências do briefing + H1/H2
docs/fase-0/{plano,capacidade}.md       reconhecimento
docs/decisions/001-007                  as 7 ADRs
research/evidencia/                     3 arquivos de medição ao vivo
```

**Acrescentado em 2026-09-08 (PR #1, commits `ac49798` e `776fe02`):**

```
adapters/pdpj.py                 adapter da Via 0 nacional. Seleção explícita de
                                 documento, sigilo terminal, grau por mapeador INJETADO
core/httpx_transport.py          http2+UA (requisito medido). Identidade só da Session
                                 por chamada, cookie jar surdo, ZERO política de retry,
                                 erro sem URL/token/__cause__
core/inpage_transport.py         fetch de dentro da página autenticada. Uma identidade
                                 por página; Session com cookies próprios é RECUSADA
                                 (fetch não define Cookie); bytes por base64
core/session_pool.py             cache por (tribunal, credencial), renovação
                                 single-flight, invalidação por geração
core/session_store.py            storage_state em repouso sob DPAPI (§5.1)
classify/tipo_pje.py             camada 1 por tipo.codigo nacional; abstém-se com OUTRO
docker-compose.yml               Postgres efêmero (tmpfs, só 127.0.0.1) p/ smoke da migration
tests/                           224 verdes, 2 excluídos. Fixtures sintéticas, guarda de
                                 bloqueio de rede outbound
docs/canais-publicos/            via-sem-autenticacao.md + matriz-24-trts.md (§3.2)
docs/execucao/                   backlog, relatórios, protocolos de medição, propostas,
                                 handoff-orquestrador.md, proposta-adr-008
```

**Ainda NÃO existe:** handshake (nada cria `Session` de verdade), fila/repository de jobs
sobre a migration, split de PDF, OCR, camadas 2-4 do classificador, adapter DataJud,
adapter FALCÃO.

CI (`.github/workflows/ci.yml`): roda testes (`-m "not rede and not portao"`), lint, mypy,
e um job que **barra credencial, certificado, PDF e HAR bruto** no índice.

## 9. Resultado imaginado (estado final)

Um serviço que, dado um conjunto de números CNJ:
- emite e mantém sessão autenticada (handshake manual raro do titular),
- para cada processo, lista os documentos pela API nacional,
- baixa as 5 classes de peça (filtradas), deduplicadas por sha256,
- classifica cada peça com método+confiança, revisão humana amostral abaixo do limiar,
- arquiva binário + metadados de forma idempotente e auditável,
- roda em volume moderado, ritmo humano, com rate limit e circuit breaker por tribunal,
- retoma de kill -9 sem duplicar nem perder (estado no Postgres),
- OCR só para digitalizações sem texto (talvez dispensável via hrefTexto).

## 10. RESPOSTA HONESTA: "vamos conseguir extrair todas as informações assim?"

**Sim, para processos públicos — e está provado ponta a ponta.** A API nacional entregou
metadados + os PDFs de todas as peças de um processo real, e baixamos a petição inicial
com hash e metadados corretos. As 5 classes são identificáveis pelo `tipo.codigo` nacional.

**Com estas ressalvas honestas — o que ainda NÃO está provado:**

| # | Lacuna | Impacto | Como fechar |
|---|---|---|---|
| L1 | **Segredo de justiça não vem** (por lei) | peças sigilosas ficam de fora, sempre | **FECHADA** como limite legal: terminal SIGILOSO no adapter |
| L2 | `/binario` às vezes devolve JSON curto antes do PDF | precisa de retry/poll | **PARCIAL** — só prefixo e tamanho registrados. Semântica NÃO confirmada; o adapter exige predicado injetado, não presume |
| L3 | **`hrefTexto` não confirmado** | decide se OCR é regra ou exceção | **ABERTA** — probe escrito (`docs/execucao/l3-href-texto.md`), não executado |
| L4 | duração da **sessão de dispositivo** do Keycloak | frequência de re-login manual | **ABERTA** — protocolo escrito (`l4-l5-medicao-autorizada.md`) |
| L5 | **teto de concorrência** não medido | dimensiona o ritmo/volume | **ABERTA** — software local testado (50 consumidores); teto real do tribunal não medido |
| L6 | testado **só no TRT4** | generalização aos outros TRTs | **ABERTA** para a via autenticada. Mas ver §3.2: a consulta pública e o FALCÃO já se mostraram **nacionais e uniformes** |
| L7 | processos com **muitos/grandes documentos** | pode ter geração assíncrona (Área de Download) | **ABERTA** — testar um processo volumoso |
| L8 | **governança** (ADR 007) | libera VOLUME | **ABERTA** — aprovação titular + compliance |
| **L9** | **nenhuma `Session` é criada** — não existe handshake | **bloqueia a fase 1 inteira**; nada roda ponta a ponta hoje | `playwright install chromium` + um login manual do titular + costurar `SessionStore` ↔ `SessionPool` |
| **L10** | **Postgres nunca subiu** — migration nunca aplicada | bloqueia a fase 3; `SKIP LOCKED` e retomada não provados | subir o Docker Desktop (CLI instalado, **daemon parado**) |
| **L11** | **revisão adversarial independente** do adapter/transporte/pool | risco de defeito não visto em código de aquisição | 2 tentativas falharam (quota e erro de agente). Refazer |
| **L12** | endpoint dos **bytes do PDF no FALCÃO** | decide se acórdão fecha ponta a ponta sem autenticar | 1 clique no navegador real. Rota do frontend é `/pdfInteiroTeor`; o artefato é PDF, o endpoint não foi capturado |
| **L13** | **teto de taxa do FALCÃO** | dimensiona o ritmo do canal público | sabemos que existe (**429** após poucas chamadas). Valor seguro exige o protocolo L4/L5 |

Nenhuma dessas invalida o caminho. Elas são o que separa "provado num processo" de "roda
em volume com confiança". L1 é limite legal permanente; o resto é medição.

## 11. Roadmap (fases, com critério de saída)

| Fase | Escopo | Critério de saída | Estado |
|---|---|---|---|
| 0 | Reconhecimento | H1/H2 respondidas, capacidade documentada | ✅ **feito** |
| 2 | Um processo ponta a ponta | petição inicial em disco, hash+metadados | ✅ **feito** (fora de ordem) |
| 1 | Camada de sessão isolada | 50 sessões emitidas/renovadas sem intervenção | 🟡 **em curso.** `SessionPool` e `SessionStore` existem e têm teste. Falta o **handshake** (L9) — nada emite sessão hoje |
| 3 | Estado, fila, idempotência, retry, circuit breaker | 100 processos, kill -9 no meio, retoma | 🔴 **bloqueada por L10** (Postgres) |
| 4 | Classificação + split + OCR | ≥95% em amostra de 100 rotulada à mão | 🟡 só camada 1 (`tipo.codigo`). Falta sequência, keywords, LLM, split, OCR |
| 5 | Generalização aos 24 TRTs | capabilities.yaml preenchido; adapters de exceção | 🔴 não iniciada — mas §3.2 mostra que consulta pública e FALCÃO já são **nacionais** |
| 6 | Volume, observabilidade, incremental | 10k processos, erro medido, sem bloqueio | 🔴 não iniciada. O DJEN dá o **feed incremental** de graça (§3.2) |

**Ordem recomendada agora**, na sequência que destrava mais coisa por passo:

1. **Fase 1 — handshake** (L9). `playwright install chromium`, um login manual do titular,
   costurar `SessionStore` ↔ `SessionPool`. Sem isto **nada roda ponta a ponta**, e todas
   as medições autenticadas (L2, L3, L4, L7) continuam impossíveis.
2. **Fase 3 — Postgres** (L10). Subir o Docker Desktop e aplicar a migration **sem editá-la**.
3. **L11** — revisão adversarial independente do que já existe, antes de empilhar mais.
4. **L2, L3, L7** — caem juntas, numa rodada autorizada, assim que houver sessão.
5. **Fase 4** — camadas 2-4 do classificador.

Barato e independente de tudo isso, se quiser paralelizar: **L12** (1 clique) e o adapter
DataJud de seed (não precisa de credencial nenhuma).

## 12. Como continuar (instruções para o Codex)

**Antes de tudo:** leia este arquivo, `docs/arquitetura.md`, e as ADRs 001–007. Elas são a
constituição do projeto.

**Invariantes que você NÃO viola** (seção 6): certificado só no handshake; SIGILOSO
terminal; zero evasão; ritmo humano; auditoria; nada de chave privada em código; nada de
teste contra tribunal de produção (use fixtures gravadas, marcador `rede` fica fora do CI).

**Arquivos que você NÃO edita sem pedir:** `core/contracts.py` (contratos), `capabilities.yaml`
(dado de produção), `migrations/` (esquema), `docs/decisions/` (decisões tomadas).

**Onde você trabalha:** `adapters/`, `core/` (fila, rate_limit), `storage/`, `classify/`,
`tests/`, `docs/execucao/`, `docs/canais-publicos/`.

**Padrão de tarefa:** contrato fechado — assinatura, entrada, saída, critério de aceite,
arquivos permitidos. Nunca "implemente o scraper". Revisão antes de integrar.
O template pronto está no `handoff-orquestrador.md`.

~~**Primeira peça sugerida:** `adapters/pdpj.py`~~ — **FEITO** em 2026-09-08 (commit
`ac49798`). Base `portaldeservicos.pdpj.jus.br/api/v2`, `authenticate` recebe a `Session`
do handshake, `list_documents` mapeia `documentos[]` → `DocumentoRef` por `tipo.codigo` /
`nivelSigilo` / `hrefBinario`, `fetch_artifact` baixa via `hrefBinario`. Testes com
resposta gravada, zero rede real. Falta a revisão adversarial independente (L11).

**Próxima peça sugerida: o handshake (L9).** É o que trava tudo. Contrato:

- **Onde:** um módulo novo em `core/` (p.ex. `handshake.py`). Não mexer em `contracts.py`.
- **Entrada:** `Credencial` + tribunal. **Saída:** uma `Session` válida, e o
  `storage_state` salvo via `SessionStore` (§5.1).
- **Como:** Playwright abre o navegador, o **titular** loga com o certificado
  (PJeOffice → Keycloak). O agente **não automatiza o login** — invariante 3. O código
  espera o humano terminar, captura `storage_state`, monta a `Session`, persiste.
- **Reaproveitamento:** na partida, tentar `SessionStore.carregar` antes de pedir
  handshake. `None` (ausente ou ilegível) significa "pede login", nunca erro fatal.
- **Aceite:** com o browser instalado e **um** login manual, o processo reinicia e
  continua **sem** novo login; `SessionPool` entrega a sessão a 50 consumidores
  concorrentes com uma renovação só.
- **Teste:** o fluxo Playwright fica atrás de um duplo, como em `test_inpage_transport.py`.
  O login real é verificação manual do titular, marcada `rede`, fora do CI.

**Pré-requisito de ambiente:** `playwright install chromium` — a dependência está
declarada em `[project.optional-dependencies] browser`, o navegador **não** está baixado.

---

*Última atualização: **2026-09-10** (revisão anterior: 2026-09-03). Mantido pelo
orquestrador (Claude Code). Ao avançar,
atualize a seção 10 (lacunas) e a 11 (roadmap) — são o termômetro honesto do projeto.*
