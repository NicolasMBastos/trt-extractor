# Arquitetura — `trt-extractor`

Versão 1, 2026-09-03. Escrita depois do reconhecimento de ambiente, antes de qualquer
código de extração. Onde eu discordo do briefing, digo por quê e com que evidência.

---

## 0. Sumário executivo

O reconhecimento derrubou quatro premissas do briefing. Uma delas — a via de aquisição —
muda a forma do projeto inteiro.

| # | Premissa do briefing | Achado | Impacto |
|---|---|---|---|
| 1 | Certificados podem ser A3 → sessões serializadas | **Todos A1**, CSP de software, exportáveis. `list.a3=` vazio no PJeOffice | Emissão de sessão paralelizável. Deixa de ser gargalo |
| 2 | "24 TRTs não são um sistema" | Existe **API REST nacional** `portaldeservicos.pdpj.jus.br/api/v2` em produção, chaveada por CNJ | Pode colapsar 24 integrações em 1. Vira **Via 0** |
| 3 | "Volume roda em HTTP paralelo com o token" | Código de produção anterior afirma que **WAF exige `fetch` de dentro da página** | Se confirmado, `httpx` não é o substrato de volume. **Maior risco do projeto** |
| 4 | Roda em macOS | **Windows 10 Pro 19045** | Muda tooling, não arquitetura |

Consequência: a fase 0 deixa de ser "descobrir como funciona" e passa a ser
**falsificar duas hipóteses específicas** (H1 e H2, seção 4). Isso encurta a fase 0 de
semanas para dias.

Fonte dos achados 1–3: inventário do repositório de certificados do Windows, config do
PJeOffice Pro (`~/.pjeoffice-pro/pjeoffice-pro.config`) e código de produção do projeto
irmão `TaxMap-main`, na mesma máquina. Detalhe em `docs/decisions/`.

---

## 1. O que eu mantenho do briefing, sem ressalva

Estas decisões estão certas e não vou re-litigar:

- **Estado explícito por `(processo, tipo_documento)`**, não etapas de pipeline. É o que
  torna "completar os que faltaram" um `SELECT`, e não uma fila especial.
- **Idempotência via `sha256`** e chave `(numero_cnj, grau, tipo_documento)`.
- **`SIGILOSO` como estado terminal legítimo**, fora da métrica de falha.
- **Filtro por tipo antes de gerar**, nunca autos integrais + filtro depois.
- **Matriz de capacidade como dado de produção**, lida em runtime.
- **Classificador em camadas** com `metodo` + `confianca` persistidos.
- **OCR fora do caminho de download**, fila separada.
- **Circuit breaker por tribunal**, não global.
- **Não implementar evasão de detecção.** Se a saída parecer ser essa, subir de via ou escalar.
- **DataJud não é via de aquisição.** Só seed, filtro de desperdício e chave de reconciliação.

---

## 2. Onde eu discordo

### D1 — A tabela 2.2 começa no nível errado. Falta a Via 0.

**Discordo.** O briefing manda tentar MNI SOAP primeiro, e MNI é **por tribunal**: WSDL
próprio, convênio próprio, credenciamento próprio. São 24 negociações e 24 integrações —
exatamente o problema que a seção 3.1 diz para evitar.

Existe uma camada acima disso. O projeto TaxMap, na mesma máquina e com as mesmas
credenciais, roda em produção contra:

```
https://portaldeservicos.pdpj.jus.br/api/v2/processos?cpfCnpjParte=...&filter=...
```

É a API do **Portal de Serviços do PDPJ** — nacional, chaveada pelo número CNJ unificado,
autenticada pelo mesmo SSO Keycloak que o briefing já identificou, com paginação por
`searchAfter` e filtro server-side (`filter=classe.codigo in ...`). Uma integração, não 24.

Tabela revisada:

| # | Via | Escopo | Status |
|---|---|---|---|
| **0** | **API PDPJ `api/v2/processos`** | **nacional** | **provada para listagem; entrega de binário é H1** |
| 1 | MNI SOAP `consultarProcesso` | por tribunal | fallback onde a Via 0 não entregar binário |
| 2 | "Download autos" com filtro de tipo | por tribunal | fallback |
| 3 | Download de documento individual | por tribunal | retry cirúrgico |
| 4 | Playwright no navegador oficial | por tribunal | último recurso **e** emissor de sessão |
| 5 | Visualizadores legados (VDOC etc.) | pontual | só com volume real |

**O que ainda não sei, e é a pergunta mais importante da fase 0:** a Via 0 entrega o
**binário** do documento, ou só metadados e a lista de documentos? O TaxMap usa a API v2
apenas para *listar* processos; para pegar o PDF ele volta a clicar no DOM
(`DOCUMENTO_LINK_SELECTOR`, `DOWNLOAD_BUTTON_SELECTORS`). Isso pode significar (a) que a
API não serve binário, ou (b) que ninguém tentou. **É H1.**

Se a resposta for (b), o projeto encolhe drasticamente e a seção 3.1 do briefing
("um adapter por tribunal") vira desnecessária para a maioria dos casos.

### D2 — "Todo o volume roda em HTTP paralelo com o token" é provavelmente falso.

**Discordo, com evidência.** O briefing assume:

```
certificado → token → volume em httpx paralelo
```

O código anterior diz o contrário, em comentário no ponto exato da implementação
(`taxmap/jusbr.py`, acima de `_JUSBR_API_FETCH_JS`):

> `# fetch executado DENTRO da pagina (Chrome autenticado): mesma origem, cookies`
> `# AWSALB automaticos, TLS/HTTP2 de navegador -> passa pelo WAF do PDPJ.`

Ou seja: portar o Bearer para `httpx` provavelmente **falha no WAF**, porque o que é
verificado não é só o token — é o cookie de load balancer (`AWSALB`) e a impressão
TLS/HTTP2 do cliente. Eles resolveram executando `fetch` de dentro da página via CDP,
com um hook que intercepta `fetch`/`XMLHttpRequest.setRequestHeader` para capturar o
`Authorization`.

Isso não é detalhe de implementação. Inverte o substrato de execução:

- se o WAF de fato barra, o volume roda em **N contextos de browser autenticados
  emitindo `fetch` in-page**, e `httpx` fica só para o que estiver fora do WAF;
- o teto de concorrência passa a ser **memória/CPU local por contexto**, não rede;
- Playwright sobe de "nível 4 de 5" para **transporte de primeira classe** — mas como
  transporte, nunca como scraper de DOM. A distinção importa: `page.evaluate(fetch)`
  é estável; `click` em seletor CSS não é. O briefing está certo em desconfiar do
  Playwright-como-scraper e eu mantenho essa desconfiança.

**Não estou decidindo isso agora.** É medição obrigatória (H2), e o contrato de
transporte precisa abstrair as duas respostas. Ver D3.

> Ressalva honesta: o comentário é uma afirmação do autor anterior, não uma prova.
> Pode ser folclore. Por isso H2 é teste, não premissa.

### D3 — O contrato precisa de uma camada que o briefing não tem: `Transport`.

O briefing define `TribunalAdapter` com cinco operações. Concordo com as cinco. Mas se
D2 se confirmar, cada adapter teria que saber se fala por `httpx` ou por browser — e a
decisão de transporte vazaria para 24 adapters.

Insiro uma camada abaixo:

```
TribunalAdapter  (o quê: authenticate, list_documents, request_download,
                        poll_download, fetch_artifact)
      ↓ usa
Transport        (como: get / post / fetch_bytes — httpx OU in-page fetch)
      ↓ carrega
Session          (identidade: token, cookies, validade, credencial de origem)
```

`Transport` tem duas implementações — `HttpxTransport` e `InPageFetchTransport` — com a
mesma assinatura. A escolha vem da `capabilities.yaml` por tribunal, medida, não
hardcoded. Isso deixa H2 ser respondida *depois* sem reescrever adapter nenhum, e
permite que um tribunal use um transporte e outro use o outro.

Esse é o contrato que eu escrevo pessoalmente. É onde um erro contamina tudo.

### D4 — O gargalo real hoje não é o tribunal. É a credencial.

O briefing dimensiona por "jobs concorrentes por sessão". Correto, mas incompleto.
Inventário real de certificados nesta máquina:

| Titular | AC | Expira | Situação |
|---|---|---|---|
| LARISSA A. R. F. DE ALMEIDA | Certisign RFB G5 | 2025-04-01 | **expirado** |
| CLARISSE DE SOUZA ROZALES | Safeweb RFB v5 | 2025-08-08 | **expirado** |
| RENATA PEREIRA ZANARDI | Safeweb RFB v5 | 2026-07-04 | **expirado** |
| RENATA PEREIRA ZANARDI | Certisign RFB G5 | **2027-05-27** | **válido** |

**Há exatamente uma credencial utilizável.** Todas A1 (CSP de software, exportável) — o
que é boa notícia para paralelismo de sessão e má notícia para distribuição de carga: a
seção 4 do briefing manda "distribuir a carga entre credenciais", e não há entre o quê
distribuir.

Com 10⁴–10⁵ processos numa única e-CPF, o rate limit por `(tribunal, credencial)` deixa
de ser higiene e passa a ser o dimensionador principal do cronograma. E levanta a questão
de legitimidade que virou a pergunta 1 do plano de fase 0.

São e-CPF (`AC ... RFB`), certificados de pessoa física — não e-CNPJ do escritório.

### D5 — Object storage antes da fase 5 é infraestrutura sem gargalo.

**Discordo parcialmente.** Postgres para estado: concordo, sem ressalva — `SKIP LOCKED`,
transação e a máquina de estados justificam. Mas S3/R2 na fase 1 não paga: em 10⁴–10⁵
PDFs a 200 KB–2 MB, falamos de dezenas a centenas de GB, que um disco local
content-addressed aguenta durante todo o desenvolvimento.

Proponho `Storage` como interface desde o dia 1, com `LocalCASStorage` implementado e
`S3Storage` adiado para a fase 5, quando houver volume real e necessidade de acesso
compartilhado. Mesmo argumento do briefing contra Kafka, aplicado ao storage.

### D6 — Python 3.14 é risco de toolchain.

A máquina tem **Python 3.14.3**. O briefing pede 3.12+, o que 3.14 satisfaz nominalmente,
mas `zeep`, `playwright`, `ocrmypdf` e `psycopg` têm histórico de atraso em wheels para
minor novos. Fixo o projeto em **3.12** (`requires-python = ">=3.12,<3.13"`). Não há `uv`
nem `poetry` na máquina — recomendo `uv`, é o que reduz mais atrito aqui.

---

## 3. Arquitetura resultante

```
[seed]        CNJs — DataJud, CSV do cliente, carteira própria (OAB)
   ↓
[triagem]     via preferida ← capabilities.yaml
              descarta processo sem movimento relevante (economia de job)
   ↓
[sessão]      pool por (tribunal, credencial); single-flight; TTL; renovação proativa
              handshake: certificado A1 → SSO Keycloak → token + cookies
   ↓
[transport]   HttpxTransport | InPageFetchTransport   ← decidido por H2, por tribunal
   ↓
[submit]      Via 0 direto | pedido de download filtrado pelos 5 tipos
   ↓
[poll]        Área de Download / resposta SOAP — backoff, deadline, dead-letter
   ↓
[fetch]       binário
   ↓
[split]       separa PDF consolidado, quando vier consolidado
   ↓
[classify]    5 classes; tipoDocumento → posição no fluxo → keywords.yaml → LLM (desempate)
   ↓
[store]       content-addressed sha256 (local na fase <5, S3 depois) + metadados no Postgres
   ↓
[ocr]         fila separada, só sem camada de texto
```

Máquina de estados, storage, dedup e classificação: como no briefing (seções 3.3–3.6).
Sem divergência.

### Camadas e propriedade do código

| Camada | Arquivo | Quem escreve |
|---|---|---|
| Contratos (`TribunalAdapter`, `Transport`, `Session`, `Storage`) | `core/contracts.py` | **eu** |
| Esquema e migrations | `migrations/` | **eu** |
| Matriz de capacidade (schema) | `capabilities.yaml` | **eu** + medição |
| Adapter Via 0 (PDPJ nacional) | `adapters/pdpj.py` | Codex, com spec fechada |
| Adapter genérico PJe 2.x | `adapters/pje2x.py` | Codex, com spec fechada |
| Cliente MNI/SOAP | `adapters/mni.py` | Codex |
| Storage, fila, retry, circuit breaker | `storage/`, `core/` | Codex |
| Classificador | `classify/` | Codex; keywords do dono do projeto |
| Análise de HAR/WSDL | `research/` | Antigravity |
| Scaffolding, fixtures, CI, docs | vários | OpenCode |

---

## 4. As duas hipóteses que travam tudo

A fase 0 existe para responder isto. Ambas são falsificáveis e testáveis **hoje**, nesta
máquina, com o certificado válido, sem escrever código de produção.

### H1 — A API PDPJ v2 entrega o binário do documento

> Autenticado no PDPJ, existe endpoint sob `api/v2` que devolve o PDF de um documento
> (não só a lista de documentos), identificado a partir da resposta do processo.

- **Como testar:** Portal do Maestri → login por certificado no PDPJ → `portal evaluate`
  com `fetch` num processo conhecido → inspecionar a resposta atrás de `documentos[]`,
  `hrefBinario`, `idOrigem` ou equivalente → tentar buscar um binário.
- **Verdadeira ⇒** Via 0 é a via principal. 24 adapters viram 1 + exceções. O projeto
  encolhe pela metade.
- **Falsa ⇒** cai para as vias 1–3 do briefing, e a seção 3.1 volta a valer integralmente.

### H2 — O WAF do PDPJ rejeita cliente não-browser portando o mesmo Bearer

> A mesma requisição, mesmo token, feita por `httpx` a partir do Python, recebe resposta
> diferente da feita por `fetch` dentro da página autenticada.

- **Como testar:** capturar Bearer + cookies no Portal; disparar a requisição idêntica
  pelos dois caminhos; comparar status e corpo.
- **Verdadeira ⇒** `InPageFetchTransport` é o substrato de volume. Concorrência limita-se
  por contexto de browser. O plano de capacidade muda inteiro.
- **Falsa ⇒** `HttpxTransport`, e o briefing estava certo na seção 2.3.

**Nenhuma linha de adapter antes de H1 e H2 respondidas.** É exatamente o risco que o
briefing descreve na seção 6 — construir três semanas de scraper e descobrir que não
precisava — e agora ele tem nome e teste.

---

## 5. Política de tráfego (ajustada ao achado D4)

Mantenho tudo da seção 4 do briefing, com uma correção e um acréscimo:

- **Correção:** "distribua a carga entre credenciais" é inexequível hoje — há uma só
  credencial válida. Até que isso mude, o rate limit tem que ser calibrado para uma
  identidade só, e o cronograma de volume depende disso.
- **Acréscimo:** o log de auditoria registra também **qual certificado** originou a
  sessão e sua validade. Com o certificado válido vencendo em 2027-05-27, dentro do
  horizonte do projeto, expiração silenciosa é modo de falha real, não hipotético.

---

## 6. Riscos ordenados

| # | Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|---|
| 1 | H2 verdadeira e concorrência in-page ser baixa | média | **alto** — muda o cronograma | medir na fase 0 antes de dimensionar |
| 2 | Credencial única não suportar o volume, ou MFA reaparecer | média | alto | medir TTL de sessão; pedir mais certificados |
| 3 | H1 falsa e voltar a 24 adapters | média | alto | fase 5 já prevê; genérico PJe2x cobre a maioria |
| 4 | ~~Legitimidade do acesso~~ | — | — | **resolvido**: acesso por publicidade, sigilo imposto pela plataforma. ADR 004 |
| 5 | Certificado válido vence durante o projeto | certa (2027-05-27) | médio | alerta de expiração no pool de sessão |
| 6 | Wheels indisponíveis em 3.14 | alta se usar 3.14 | baixo | fixar 3.12 |

---

## 7. Pendências com o dono do projeto

P1 (vínculo) e P3 (palavras-chave) **respondidas** — ver `docs/fase-0/plano.md` §6 e ADR 004.
P2 (mais certificados?) segue aberta e continua sendo o dimensionador do cronograma.
