# Handoff — runbook do orquestrador

**Data:** 2026-09-10 · **Para:** quem assumir a orquestração deste projeto.

`Continua_codex.md` é o mapa do **projeto** (o que é, o que foi decidido, o que falta).
Este arquivo é o runbook de **como o trabalho acontece aqui**: o estado do canvas, quais
agentes funcionam de verdade, as armadilhas de ambiente que já queimaram turnos, e o
padrão de delegação. Leia os dois; este é mais curto e evita repetir erro conhecido.

---

## 1. Regra zero

**Nada de peça, nada de credencial, nada de tribunal sem autorização explícita do dono do
projeto, por rodada.** Autorização de ontem não vale hoje, e autorização para um canal não
vale para outro. Quando em dúvida, pergunte — o custo de perguntar é um turno; o custo de
errar é a credencial de um advogado real.

Os invariantes estão em `Continua_codex.md` §6. Os dois que mais aparecem na prática:

- **`429`, `403`, captcha, MFA inesperado → PARE.** Sem retry, sem backoff para insistir,
  sem trocar sessão, sem tentar outra via. Já aconteceu no FALCÃO em 2026-09-08 e a
  execução parou ali. **Faça igual.**
- **Zero evasão.** Não resolver captcha, não forjar fingerprint, não rotacionar UA/IP.
  Se a saída parece evasão, pare e escale.

---

## 2. Estado do canvas (2026-09-10)

```
maestri list
```

| Nó | Tipo | Estado real |
|---|---|---|
| **Claude Code** | maestro | você |
| **Prisma** | OpenCode · GPT-5.6 Sol Fast | ⚠️ **usage limit** em 2026-09-08 |
| **Molde** | OpenCode · GPT-5.6 Terra | ⚠️ **usage limit** em 2026-09-08 |
| **Sonda** | OpenCode · GPT-5.6 Luna | ⚠️ **usage limit** em 2026-09-08 |
| **Cinzel** | Antigravity · Gemini 3.7 Flash | ❌ **crash interno** |
| **Vitral** | Antigravity · Gemini 3.7 Flash | ❌ **crash interno** |
| **Comporta** | OpenCode · Nemotron 3.5 Lightning Free | ✅ roda, mas é modelo fraco |
| **PDPJ** | portal | aponta para `portaldeservicos.pdpj.jus.br`. **Pode segurar sessão autenticada — não navegue para fora** |
| **FALCAO** | portal | `jurisprudencia.jt.jus.br` |
| **TRT-EXTRACTOR ESTADO** | nota | estado compartilhado. **Leia antes de perguntar; atualize quando algo mudar** |

CLI do Maestri: `ca7315b` (`docs/maestri-cli.md` foi levantado na `a69cff4` — confira
antes de confiar num flag).

### Confiabilidade medida dos agentes

- **Antigravity (AGY) não é confiável nesta máquina.** 4 falhas registradas: 2 na sessão
  do Codex (backlog, 2026-09-08) e 2 na de 2026-09-10, ambas
  `Agent execution terminated due to error`. **Não gaste tarefa crítica nele.** Se quiser
  tentar de novo, dê uma tarefa descartável primeiro.
- **OpenCode pago (GPT-5.6) entrega bem** — as revisões e protocolos bons do repo saíram
  dele. Mas a quota estoura, e quando estoura o `--batch` volta com
  `The usage limit has been reached` **sem criar arquivo nenhum**.
- **OpenCode free (Nemotron) roda mas é fraco.** Serve para tarefa verificável e limitada.
  **Não dê a ele código de durabilidade, concorrência ou segurança** — em 2026-09-10 ele
  entrou em laço de permissão duas vezes num erro trivial de path.
- **Verifique sempre com `maestri check "<nome>"`**, não pela resposta do `ask`. Um agente
  pode responder e não ter feito nada. Confira o `git status`.

---

## 3. Armadilhas de ambiente — todas já custaram turno

### 3.1 Acento no diretório (a mais cara)

O projeto vive em `...\Projetos\Extrator-Petição`. Os agentes montam o caminho **sem
acento**, caem fora do projeto e travam num prompt de permissão. Queimou turnos em duas
sessões.

**Já corrigido na raiz:** existe uma junction
`...\Projetos\Extrator-Peticao` → `...\Projetos\Extrator-Petição`. Os dois caminhos
funcionam. Se ela sumir, recrie:

```powershell
New-Item -ItemType Junction -Path "C:\Users\nicolas.bastos\Desktop\Projetos\Extrator-Peticao" `
         -Target "C:\Users\nicolas.bastos\Desktop\Projetos\Extrator-Petição"
```

Mesmo assim: **mande os agentes usarem caminho relativo.** Eles já começam na raiz.

### 3.2 Python 3.12, não o 3.14 do sistema

Sempre `.venv/Scripts/python.exe`. A máquina tem 3.14; wheels atrasam (arquitetura §2 D6).
Diga isso no preâmbulo de toda tarefa — agente esquece.

### 3.3 Docker instalado, daemon parado

`docker --version` responde (29.4.3) e `docker ps` falha. **Não é falta de Docker, é o
Docker Desktop desligado.** Bloqueia a fase 3 inteira (L10). Peça ao dono para subir.

### 3.4 `ruff format` pode duplicar import

Em 2026-09-10, ao mover `from ctypes import wintypes` para dentro de um guard de
plataforma, o formatador deixou **as duas cópias** — a do topo quebraria o CI Linux.
`ruff check` não pegou. **Depois de formatar, leia o diff.** Há um teste em
`tests/test_session_store.py` que prova estaticamente que esse import não voltou.

### 3.5 `maestri note edit` e crase no bash

Crase em string de shell vira **substituição de comando** e come o conteúdo. Aconteceu:
`` `link` `` sumiu da nota. Use aspas simples, ou escreva o texto sem crase.

### 3.6 `maestri ask --batch` com prompt grande

Escreva o JSON num arquivo e passe `--batch "$(cat arquivo.json)"`. Escapes são **JSON
padrão** (`\n` é newline). Rode em background e ajuste o timeout ao mais lento do lote.

### 3.7 `WebFetch` está bloqueado por hook

Um hook redireciona `WebFetch` para o MCP `context-mode`, que **falha ao conectar** nesta
máquina. `WebSearch` funciona. Para buscar documentação, use o venv:

```python
import httpx   # UA de browser, timeout, follow_redirects=True
```

Isso é leitura de página institucional pública — **não** confunda com bater em tribunal.

---

## 4. Como delegar aqui

### Preâmbulo (cole em toda tarefa)

> Leia `maestri note read "TRT-EXTRACTOR ESTADO"`, `Continua_codex.md` (§6, §7, §12) e
> `docs/execucao/relatorio-final-2026-09-08.md` antes de começar. Você **já está** na raiz
> do projeto: use **caminhos relativos**. Python: `.venv/Scripts/python.exe` (3.12), nunca
> o 3.14 do sistema.
> **Invariantes:** SIGILOSO é terminal legítimo; ZERO evasão de controle (se a saída
> parecer evasão, PARE e escale); nenhuma requisição a tribunal de produção; não commitar,
> não push.
> **NÃO edite:** `core/contracts.py`, `capabilities.yaml`, `migrations/`, `docs/decisions/`.
> Toque só nos arquivos listados na tarefa.
> Ao terminar responda: 1) resumo, 2) arquivos alterados, 3) decisões, 4) **o que NÃO foi
> provado**, 5) bloqueios.

### Contrato de tarefa

Nunca "implemente o scraper". Sempre: **objetivo, entrada, saída, arquivos permitidos
(lista fechada), critério de aceite, e o que NÃO fazer.** Se o agente puder inventar
semântica, ele vai inventar — feche a porta na especificação.

Duas exigências que pegaram bug de verdade:

- **"Se não conseguir, diga que não conseguiu."** Peça explicitamente para declarar
  não-executado em vez de afirmar sucesso. Já evitou "os testes passaram" sem ter rodado.
- **"Se estiver correto, diga que está correto."** Sem isso, revisor inventa achado para
  parecer útil.

### Depois que o agente responde

1. `maestri check "<nome>"` — leia o terminal, não só a resposta.
2. `git status` / `git diff` — confira que ele tocou **só** o que podia.
3. Rode o portão você mesmo (§6). Não aceite o relatório dele como prova.

---

## 5. Medição contra serviço real

Protocolos escritos, use-os em vez de improvisar:

- `docs/execucao/l4-l5-medicao-autorizada.md` — duração de sessão e teto de concorrência.
- `docs/execucao/l3-href-texto.md` — probe do `hrefTexto`.
- `docs/canais-publicos/via-sem-autenticacao.md` §5 — o que falta medir nos canais públicos.

**Telemetria sanitizada, sempre.** Registre schema de chaves, status, content-type,
tamanho, sha256, categoria. **Nunca** token, cookie, CPF, nome de parte, CNJ completo, URL
de documento, corpo ou texto integral. Os scripts de probe de 2026-09-10 seguem esse
formato — copie o estilo (eles ficaram no scratchpad da sessão, não no repo, porque probe
não é código de produção).

**Descoberta de rota:** leia as chamadas XHR da SPA no navegador real
(`maestri portal evaluate ... performance.getEntriesByType('resource')`), como a ADR 005 e
o achado do FALCÃO. **Não chute path.** Os servidores são estritos e chutar gera ruído
inútil no log deles.

---

## 6. O portão, antes de dizer que terminou

```powershell
.venv\Scripts\python.exe -m pytest              # 224 passed, 2 skipped
.venv\Scripts\python.exe -m ruff check src tests
.venv\Scripts\python.exe -m ruff format --check src tests
.venv\Scripts\python.exe -m mypy                # 13 arquivos
```

E antes de qualquer commit, o guarda de segredos do CI, rodado local:

```bash
padrao='\.(pfx|p12|pem|key|crt|cer|der|jks|keystore|pdf)$|(^|/)\.env($|\.)|storage_state|pjeoffice-pro\.config'
git ls-files | grep -v '^\.env\.example$' | grep -Ei "$padrao"   # tem que não achar nada
git diff --cached | grep -nE "eyJ[A-Za-z0-9_-]{10,}|APIKey [A-Za-z0-9+/=]{20,}"
```

O CI roda em **`ubuntu-latest`**, e a máquina de dev é Windows. Código específico de
plataforma precisa de guard (`if sys.platform == "win32"`) — ver `core/session_store.py`.
`[tool.mypy] platform = "win32"` faz os dois mypy concordarem.

---

## 7. Por onde continuar

Ordem completa em `Continua_codex.md` §11. O resumo operacional:

| # | O quê | Precisa de |
|---|---|---|
| 1 | **Handshake** (L9) — fecha a fase 1 | `playwright install chromium` + **um login manual do titular**. Sem isto nada roda ponta a ponta |
| 2 | **Postgres** (L10) — destrava a fase 3 | dono subir o Docker Desktop |
| 3 | **Revisão adversarial** (L11) do adapter/transporte/pool | um agente confiável — já falhou 2x |
| 4 | L2, L3, L7 | rodada autorizada, depois que houver sessão |
| 5 | Fase 4 — camadas 2-4 do classificador | nada; é offline |

**Paralelizável agora, sem credencial nenhuma:** o adapter DataJud de seed
(contrato em `Continua_codex.md` §3.2) e o L12 (1 clique no FALCÃO para descobrir o
endpoint do PDF).

**Decisões pendentes do dono, não suas:**

1. Promover `docs/execucao/proposta-adr-008-transporte-por-canal.md` a
   `docs/decisions/008-...`.
2. Governança para volume (ADR 007 / L8): aprovação escrita do titular e do compliance.
3. Canal institucional — Codex do CNJ exige convênio, avaliação técnica e custeio
   (Res. CNJ 574/2024 e 647/2025). É ofício, não requisição.

---

## 8. Erros já cometidos aqui — não repita

| Erro | O que fazer |
|---|---|
| Delegar tarefa crítica ao AGY | Não. 4 falhas. |
| Dar código de concorrência/segredo a modelo free fraco | Não. Faça você, ou use agente pago. |
| Confiar no relatório do agente | `maestri check` + `git diff` + rodar o portão. |
| Escrever caminho absoluto com acento no prompt | Caminho relativo. |
| Afirmar "os testes passaram" sem rodar | Cole a saída real. |
| Insistir depois de `429` | Pare. Registre. Escale. |
| Formatar e commitar sem ler o diff | O `ruff format` já duplicou um import. |
| Preencher `capabilities.yaml` por analogia | Só com medição autorizada e revisada. |
| Tratar `api/v2` do PDPJ como "API externa" | É o backend do próprio portal. Usá-la **é** raspar o portal do jeito certo. |
| Assumir que o transporte de um canal vale para outro | Medido: PDPJ e FALCÃO se comportam ao contrário. |
