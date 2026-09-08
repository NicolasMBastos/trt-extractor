# Continua_codex — briefing de continuação do `trt-extractor`

> **Para quem pega o projeto daqui (Codex ou humano):** este arquivo é o mapa completo.
> Lê ele inteiro antes de tocar código. Ele consolida contexto, objetivo, tudo que já foi
> decidido e medido, a arquitetura, o que está provado, o que falta, e como continuar sem
> quebrar os invariantes. Onde ele resume, o detalhe está nas ADRs (`docs/decisions/`) e
> nas evidências (`research/evidencia/`).
>
> Repositório (privado): `https://github.com/NicolasMBastos/trt-extractor`
> Estado: **fase 0 concluída, fase 2 provada ponta a ponta.** 35 testes verdes.
> Data-base: 2026-09-03.

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

## 4. O transporte — RESOLVIDO

Hipótese de que o WAF exige um navegador real: **FALSA, com correção** (ADR 002, adendo 2).

| Cliente | Resultado |
|---|---|
| `httpx` HTTP/1.1, sem User-Agent | **403 Forbidden** |
| `httpx` **`http2=True` + User-Agent de browser** | **200** — listagem e binário |

**Conclusão:** `HttpxTransport` (com `http2=True` e UA de Chrome) faz todo o volume. Não
precisa de fazenda de navegador. **PORÉM** — ver seção 6: a decisão do dono do projeto é
manter uma **camada de navegador estilo TaxMap** por fidelidade e legitimidade, com httpx
como opção. As duas funcionam; a escolha é de postura, não de capacidade.

## 5. Autenticação e sessão — MEDIDO

- Login por **certificado A1** (todos os certificados da máquina são A1; ver ADR 003) via
  **PJeOffice Pro** → SSO **Keycloak** → cookies/JWT. O certificado é usado **uma vez, no
  handshake, localmente** — nunca viaja na requisição (ADR 007).
- **TTL da sessão: 8 horas no PDPJ nacional**, 60 min no PJe local do TRT4.
- MFA é **por dispositivo** (login raro, não a cada acesso) — é o que torna sessão
  persistente viável.
- Preservação de sessão: `storage_state` capturado, reaproveitado, renovado
  proativamente com single-flight (ADR 006).

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
tests/                                  35 testes verdes (config, storage, sanitizador)
docs/arquitetura.md                     arquitetura + divergências do briefing + H1/H2
docs/fase-0/{plano,capacidade}.md       reconhecimento
docs/decisions/001-007                  as 7 ADRs
research/evidencia/                     3 arquivos de medição ao vivo
```

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
| L1 | **Segredo de justiça não vem** (por lei) | peças sigilosas ficam de fora, sempre | nada a fazer — é terminal SIGILOSO, correto |
| L2 | `/binario` às vezes devolve JSON curto antes do PDF | precisa de retry/poll | medir a semântica; tratar JSON curto como "não pronto" |
| L3 | **`hrefTexto` não confirmado** | decide se OCR é regra ou exceção | um teste: buscar hrefTexto de um doc |
| L4 | duração da **sessão de dispositivo** do Keycloak | frequência de re-login manual | medir ao longo de dias |
| L5 | **teto de concorrência** (Q6c) não medido | dimensiona o ritmo/volume | subir devagar, achar onde degrada |
| L6 | testado **só no TRT4** | generalização aos outros TRTs | provável (é nacional), mas confirmar em TRT2/13 |
| L7 | processos com **muitos/grandes documentos** | pode ter geração assíncrona (Área de Download) | testar um processo volumoso |
| L8 | **governança** (ADR 007) | libera VOLUME | aprovação titular+compliance |

Nenhuma dessas invalida o caminho. Elas são o que separa "provado num processo" de "roda
em volume com confiança". L1 é limite legal permanente; o resto é medição.

## 11. Roadmap (fases, com critério de saída)

| Fase | Escopo | Critério de saída | Estado |
|---|---|---|---|
| 0 | Reconhecimento | H1/H2 respondidas, capacidade documentada | ✅ **feito** |
| 2 | Um processo ponta a ponta | petição inicial em disco, hash+metadados | ✅ **feito** (fora de ordem) |
| 1 | Camada de sessão isolada | 50 sessões emitidas/renovadas sem intervenção | **próxima** |
| 3 | Estado, fila, idempotência, retry, circuit breaker | 100 processos, kill -9 no meio, retoma | |
| 4 | Classificação + split + OCR | ≥95% em amostra de 100 rotulada à mão | |
| 5 | Generalização aos 24 TRTs | capabilities.yaml preenchido; adapters de exceção | |
| 6 | Volume, observabilidade, incremental | 10k processos, erro medido, sem bloqueio | |

Ordem recomendada agora: **fechar L2/L3/L5 com alguns processos da carteira → fase 1
(sessão) → fase 3 (estado/fila) → fase 4 (classificação)**.

## 12. Como continuar (instruções para o Codex)

**Antes de tudo:** leia este arquivo, `docs/arquitetura.md`, e as ADRs 001–007. Elas são a
constituição do projeto.

**Invariantes que você NÃO viola** (seção 6): certificado só no handshake; SIGILOSO
terminal; zero evasão; ritmo humano; auditoria; nada de chave privada em código; nada de
teste contra tribunal de produção (use fixtures gravadas, marcador `rede` fica fora do CI).

**Arquivos que você NÃO edita sem pedir:** `core/contracts.py` (contratos), `capabilities.yaml`
(dado de produção), `migrations/` (esquema), `docs/decisions/` (decisões tomadas).

**Onde você trabalha:** `adapters/` (o adapter PDPJ nacional é a primeira peça real a
escrever — implementa `TribunalAdapter` usando `HttpxTransport` http2+UA), `core/` (fila,
rate_limit, session pool), `storage/`, `classify/`, `tests/`.

**Padrão de tarefa:** contrato fechado — assinatura, entrada, saída, critério de aceite,
arquivos permitidos. Nunca "implemente o scraper". Revisão antes de integrar.

**Primeira peça sugerida:** `adapters/pdpj.py` — o adapter da Via 0 nacional. Ele já tem
tudo medido para nascer: base `portaldeservicos.pdpj.jus.br/api/v2`, `authenticate` recebe
a `Session` capturada do handshake, `list_documents` faz `GET /processos/{cnj}` e mapeia
`documentos[]` → `DocumentoRef` (usando `tipo.codigo`, `sequencia`, `nivelSigilo`,
`hrefBinario`), `fetch_artifact` baixa via `hrefBinario` com retry para o JSON-curto (L2).
Testes com resposta gravada (VCR), zero rede real.

---

*Última atualização: 2026-09-03. Mantido pelo orquestrador (Claude Code). Ao avançar,
atualize a seção 10 (lacunas) e a 11 (roadmap) — são o termômetro honesto do projeto.*
