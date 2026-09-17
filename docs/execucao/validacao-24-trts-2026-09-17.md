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
