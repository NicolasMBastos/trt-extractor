# Fase 0 — plano executável

**Alvo primário: TRT4 (Rio Grande do Sul).** É onde o escritório atua e onde está o
volume real — definido pelo dono do projeto em 2026-09-03.

Alvos de contraste, só para validar generalização depois que o TRT4 fechar:
**TRT2** (grande, SP capital) e **TRT13** (pequeno, PB). Nada de 24 de uma vez, e
nada de TRT2/TRT13 antes do TRT4 estar ponta a ponta.

Critério de saída: `docs/fase-0/capacidade.md` completo + HARs sanitizados em
`research/har/` + tipo de certificado documentado + **H1 e H2 respondidas**.

**Nenhuma linha de adapter antes de H1 e H2.** É o risco central do projeto:
construir três semanas de scraper e descobrir que a API nacional resolvia.

---

## 0. Pré-requisitos (bloqueiam tudo)

| # | Item | Estado | Responsável |
|---|---|---|---|
| 0.1 | Maestri: recrutar Codex, Antigravity, OpenCode e conectar | ⬜ | eu |
| 0.2 | Python 3.12 instalado (a máquina tem 3.14 — ver arquitetura D6) | ⬜ | eu |
| 0.3 | Processo-teste conhecido, com petição inicial acessível pela credencial válida | ⬜ | **dono do projeto** |
| 0.4 | ~~Confirmar legitimidade de acesso~~ | ✅ | resolvido — ADR 004 |
| 0.5 | Titular faz login manual com certificado no Portal (H1/H2) | ⬜ | **titular do certificado** |

> **0.3 e 0.5 travam H1 e H2.** Sem um processo-alvo real e sem o login do titular, não
> há o que medir. As demais frentes (MNI, análise de arte prévia, scaffolding) já estão
> rodando em paralelo e não dependem disso.

---

## 1. As duas hipóteses (prioridade máxima)

Testadas manualmente, no Portal do Maestri, com DevTools. Sem código de produção.

### H1 — a API PDPJ v2 entrega o binário do documento

> Autenticado no PDPJ, existe endpoint sob `api/v2` que devolve o **PDF**, e não só
> a lista de documentos.

| # | Passo | Como | Resp. |
|---|---|---|---|
| 1.1 | Abrir `portaldeservicos.pdpj.jus.br/consulta` no Portal | `maestri portal create` | eu |
| 1.2 | Login por certificado (RENATA / Certisign, válido até 2027-05-27) | manual, PJeOffice Pro | dono |
| 1.3 | Capturar o Bearer | `portal evaluate` com hook em `fetch`/`setRequestHeader` | eu |
| 1.4 | `GET api/v2/processos/{cnj}` — inspecionar a resposta | `portal evaluate` | eu |
| 1.5 | Procurar `documentos[]`, `hrefBinario`, `idOrigem`, `arquivo`, `_links` | leitura do JSON | Antigravity |
| 1.6 | Tentar buscar um binário pelo href encontrado | `portal evaluate` | eu |
| 1.7 | Registrar veredito em `capacidade.md` e em `capabilities.yaml` | — | eu |

**Verdadeira ⇒** Via 0 vira a via principal; 24 adapters viram 1 + exceções.
**Falsa ⇒** seguir para as vias 1–3 e a seção 3.1 do briefing volta a valer inteira.

### H2 — o WAF rejeita cliente não-browser com o mesmo Bearer

> A mesma requisição, mesmo token, por `httpx`, responde diferente da feita por
> `fetch` dentro da página.

| # | Passo | Resp. |
|---|---|---|
| 2.1 | Capturar Bearer **e** cookies (incl. `AWSALB`) do contexto autenticado | eu |
| 2.2 | Disparar a requisição idêntica via `portal evaluate` (in-page) — anotar status | eu |
| 2.3 | Disparar a mesma via `httpx` no Python, mesmos headers e cookies — anotar status | Codex |
| 2.4 | Comparar status, corpo e headers de resposta | eu |
| 2.5 | Repetir após 5 min (descarta token expirado como explicação) | eu |
| 2.6 | Gravar `transporte:` do tribunal em `capabilities.yaml` | eu |

**Verdadeira ⇒** `InPageFetchTransport` é o substrato de volume; concorrência passa a
ser limitada por contexto de browser, e o plano de capacidade muda inteiro.
**Falsa ⇒** `HttpxTransport`, e o briefing estava certo na seção 2.3.

> A evidência de partida é um comentário no código do TaxMap, não uma prova. Pode ser
> folclore. Por isso é teste.

---

## 2. As 8 perguntas do briefing, por tribunal

Marcar por tribunal. `n/a` é resposta válida; em branco não é.

> **Ordem de preenchimento: TRT4 primeiro, coluna inteira.** TRT2 e TRT13 só depois,
> e só para medir o quanto o adapter genérico generaliza. Se o TRT4 não fechar, medir
> os outros dois é desperdício.

### 2.1 Certificado — **já respondido, sem depender de tribunal**

| Pergunta | Resposta | Evidência |
|---|---|---|
| A1 ou A3? | **A1** (todos) | CSP de software (`Microsoft Enhanced`/`Strong Cryptographic Provider`), exportáveis |
| Qual app gerencia? | **PJeOffice Pro** | `C:\Program Files\PJeOffice Pro` |
| PJeOffice instalado? | **sim**, ativo | config salva em 2026-09-01 |
| Versão | *"Auto Updatable"* — sem número no registro | ⬜ confirmar em `pjeoffice-pro.jar` |
| A3 configurado? | **não** — `list.a3=` vazio | `~/.pjeoffice-pro/pjeoffice-pro.config` |
| Repositório | `MSCAPI` (store do Windows) | idem |
| Estratégia de auth | `ONE_TIME` | idem |
| SSO alvo | `sso.cloud.pje.jus.br/auth/realms/pje` | idem |

**Consequência:** emissão de sessão é paralelizável; certificado sai do caminho crítico
de throughput. Mas **há uma só credencial válida** (arquitetura §2, D4) — o gargalo
mudou de lugar, não desapareceu.

⬜ **Pendente:** o `pjeoffice-pro.config` guarda um blob de credencial do SSO. Já está
no `.gitignore` e há guarda no CI. Não copiar para lugar nenhum.

### 2.2 Checklist por tribunal

| # | Pergunta | **TRT4** | TRT2 | TRT13 | Resp. |
|---|---|---|---|---|---|
| Q2 | CPF/senha funciona para consulta **e** download, ou o certificado é obrigatório? | ⬜ | ⬜ | ⬜ | eu + dono |
| Q3a | MFA exigido a cada login ou uma vez por dispositivo? | ⬜ | ⬜ | ⬜ | eu |
| Q3b | Quanto dura a sessão? (medir com relógio, não estimar) | ⬜ | ⬜ | ⬜ | Codex |
| Q4a | WSDL do MNI responde? | ⬜ | ⬜ | ⬜ | Codex |
| Q4b | `consultarProcesso` funciona? | ⬜ | ⬜ | ⬜ | Codex |
| Q4c | `incluirDocumentos=true` retorna base64 **de verdade**? | ⬜ | ⬜ | ⬜ | Codex |
| Q4d | Exige convênio/credenciamento? | ⬜ | ⬜ | ⬜ | dono |
| Q5a | "Download autos do processo" existe? | ⬜ | ⬜ | ⬜ | eu |
| Q5b | Aceita filtro por tipo? | ⬜ | ⬜ | ⬜ | eu |
| Q5c | Quais tipos aparecem na lista? (grafia do tribunal, sem traduzir) | ⬜ | ⬜ | ⬜ | Antigravity |
| Q6a | Limiar de tamanho para download síncrono | ⬜ | ⬜ | ⬜ | eu |
| Q6b | Tempo até aparecer na Área de Download (p50 e p95) | ⬜ | ⬜ | ⬜ | Codex |
| Q6c | **Teto de jobs simultâneos antes de degradar ou recusar** | ⬜ | ⬜ | ⬜ | eu |
| Q7 | HAR completo do fluxo, sanitizado | ⬜ | ⬜ | ⬜ | eu → Antigravity |
| Q8 | WAF/Cloudflare no caminho? Rate limit observável? | ⬜ | ⬜ | ⬜ | eu |

> **Q6c é a métrica mais importante da fase.** Se o teto for 3 jobs por sessão, mais
> paralelismo de rede é desperdício — o que falta é sessão, não worker. Medir subindo
> de 1 em 1 e parando **no primeiro sinal de degradação ou recusa**. Nunca empurrar até
> o bloqueio: o objetivo é achar o teto operacional, não provocar o tribunal.

### 2.3 Método de Q7 (HAR) — obrigatório

1. Navegador oficial, DevTools aberto, **"Preserve log"** ligado.
2. Percorrer manualmente: login → autos → submit download → Área de Download → fetch.
3. Exportar HAR para `research/har/<TRIBUNAL>-<fluxo>-<AAAA-MM-DD>.har`.
4. **Sanitizar antes de versionar** (`scripts/sanitizar_har.py`, a escrever):
   remover `Authorization`, `Cookie`, `Set-Cookie`, corpos de resposta com conteúdo de
   processo, CPF e nomes de parte. Salvar como `*.sanitized.har`.
5. Só o `.sanitized.har` entra no git — o CI barra o resto.

> HAR bruto contém token, cookies e peça processual. É o insumo mais valioso da fase e
> também o artefato mais perigoso de vazar.

---

## 3. Divisão pelos agentes

| Agente | Preset | Entrega nesta fase | Não toca |
|---|---|---|---|
| **eu** | Claude Code | H1/H2, Portal, Q5, Q6a/c, Q8, contratos, integração, veredito da matriz | — |
| **Codex** | Codex | Q3b, Q4a–c (cliente SOAP de teste), Q6b, lado `httpx` de H2 | `core/contracts.py`, `capabilities.yaml` |
| **Antigravity** | Antigravity | Análise de HAR e WSDL, extração de padrão de endpoint, Q5c | código de produção |
| **OpenCode** | OpenCode | `scripts/sanitizar_har.py`, fixtures, docs, migrations, CI | adapters, contratos |

**Regras.** Um agente por área — conflito de merge entre agentes é falha minha de
especificação, não deles. Tarefa por contrato: assinatura, entrada, saída, critério de
aceite, arquivos que pode tocar. Nunca "implemente o scraper do TRT2".

Estado compartilhado em notas do Maestri, não em pergunta: `capabilities.yaml`,
contratos e decisões.

**Erros falsos de crédito** (`opencode`/`agy` reportando "sem crédito"/"sem API key"):
é ruído conhecido, eles funcionam. Protocolo — reenviar uma vez; consultar
`maestri check "<nó>"` (o terminal, não a mensagem de erro); só considerar indisponível
após 3 polls sem nenhuma saída útil. **Nunca reatribuir para mim na primeira mensagem
de erro** — isso destrói o paralelismo, que é a razão do Maestri existir.

---

## 4. Ordem de execução

```
0.3 + 0.4 (dono)  ──┐
0.1 + 0.2 (eu)    ──┴─→  H1  ──→  H2  ──→  Q2,Q3,Q5,Q6,Q8 (3 tribunais)
                                    │                    │
                                    └─→ Q4 MNI (Codex,  ─┘
                                        em paralelo)     │
                                                         ↓
                                              Q7 HAR + análise (Antigravity)
                                                         ↓
                                              capacidade.md + capabilities.yaml
```

H1 antes de tudo: se for verdadeira, metade das perguntas por tribunal perde relevância
e a fase encurta muito.

---

## 5. Critério de saída (objetivo)

- [ ] H1 respondida, com evidência gravada
- [ ] H2 respondida, com os dois status lado a lado
- [ ] As 15 linhas de §2.2 preenchidas para TRT2, TRT4 e TRT13 — sem célula em branco
- [ ] 3 HARs sanitizados em `research/har/`
- [ ] `capabilities.yaml` com os 3 alvos fora de `nao_testado` e com `testado_em`
- [ ] `docs/fase-0/capacidade.md` escrito
- [ ] Tipo de certificado documentado ✅ (já feito — §2.1)

---

## 6. Três perguntas para o dono do projeto — RESPONDIDAS

### P1 — vínculo com os processos-alvo · ✅ RESOLVIDA

**Resposta:** certificado do titular do escritório; não há relação com os processos.

**Conclusão:** não é bloqueante. A base do acesso é a **publicidade** do processo, imposta
pela própria plataforma — não o vínculo processual. Processo público abre para qualquer
identidade autenticada; processo em segredo não abre, e essa recusa é a resposta correta.
Mesmo modelo do TaxMap, em produção no escritório, verificado. Registrado na **ADR 004**,
com os invariantes que passam a valer: sigilo é fronteira dura, zero evasão de controle,
autenticação é ato do titular.

### P2 — mais certificados válidos? · ⬜ ABERTA

Segue sendo o dimensionador do cronograma. Uma credencial válida (vence 2027-05-27),
três expiradas. Não bloqueia a fase 0; bloqueia o planejamento de volume da fase 6.

### P3 — palavras-chave · ✅ RESOLVIDA

**Resposta:** derivar das principais.

`config/keywords.yaml` preenchido, com procedência marcada por classe:

- `[PRODUÇÃO]` — `peticao_inicial`, `acordao`, `sentenca`: pesos transpostos sem alteração
  do TaxMap, em uso no escritório.
- `[DERIVADO]` — `acordo`, `laudo_pericia`: não existiam lá. Derivei por analogia, mesmo
  padrão. **Não validados** — precisam da amostra rotulada da fase 4.

Portão fechado: a suíte está verde. Uma pendência menor de escopo continua aberta —
**laudo/perícia entra na fase 4 ou fica para depois?** O briefing marcava como secundário.
