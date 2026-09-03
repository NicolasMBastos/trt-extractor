# Maestri CLI — mapa desta versão

Levantado em 2026-09-03. **Versão do CLI: `a69cff4`.** Binário:
`C:\Users\nicolas.bastos\AppData\Local\Programs\Maestri\resources\cli\maestri.exe`

Regenerar com `maestri help` e `maestri <cmd> --help`.

---

## 0. Estado da malha nesta sessão

```
maestri list
→ You: name "Claude Code", maestro: true
→ No connected agents, notes, or portals.
```

**Não há nenhum agente conectado ainda.** Codex / Antigravity / OpenCode precisam ser
recrutados (`maestri recruit`) e conectados antes de qualquer delegação. Isso é
pré-requisito da fase 0, não detalhe de setup.

Workspace único: `"EXTRATOR-PETIÇÕES-INICIAIS"` → `C:\Users\nicolas.bastos\Desktop\Projetos\Extrator-Petição`.

### Presets disponíveis (`maestri preset list`)

| Preset | Papel neste projeto (seção 8.2 do briefing) |
|---|---|
| `Claude Code` | eu — arquitetura, contratos, revisão, integração |
| `Codex` | implementação de módulos com spec fechada |
| `Antigravity` | análise de artefatos grandes (HAR, WSDL, HTML) |
| `OpenCode` | scaffolding, fixtures, docs, migrations, CI |
| `Shell` | terminal cru, sem agente |

Os quatro papéis do briefing têm preset real. Nenhum precisa de substituto.

---

## 1. Comunicação entre agentes

| Comando | Uso |
|---|---|
| `maestri list` | lista agentes, notas e portais conectados |
| `maestri ask "Nome" "prompt"` | envia mensagem e aguarda resposta |
| `maestri ask --batch '{"A":"p1","B":"p2"}'` | **paralelo**; devolve array JSON quando todos terminam |
| `maestri ask "Nome" --raw "2\n"` | input cru no terminal do agente (menus interativos). Escapes: `\n` Enter, `\t` Tab, `\e` ESC, `\xNN` byte (`\x03` = Ctrl-C), `\e[A` seta cima, `\e[Z` Shift-Tab |
| `maestri check "Nome"` | **lê a saída atual do terminal do agente** |
| `maestri notify "msg"` | notificação de sistema ao usuário (só Maestro) |

> `--batch` é o mecanismo que dá o ganho de paralelismo do briefing (seção 8.3).
> `check` é o que resolve o protocolo de "erro falso de crédito": ele lê o terminal,
> não a mensagem de erro do agente.

## 2. Notas (estado compartilhado entre agentes)

| Comando | Uso |
|---|---|
| `maestri note create ["conteúdo"] [--name "Nome"] [--stack ["Fichário"]]` | cria e vincula a este terminal; devolve o nome atribuído |
| `maestri note read "Nome" [offset] [limit]` | lê (faixa de linhas opcional) |
| `maestri note write "Nome" "conteúdo"` | substitui integralmente |
| `maestri note edit "Nome" "antigo" "novo"` | substitui trecho |
| `maestri note stack/unstack "Nome" ["Fichário"]` | arquiva / libera |
| `maestri note delete "Nome"` | destrutivo — só a pedido explícito |

Uso previsto: `capabilities.yaml`, contratos de interface e decisões vivem em notas,
para os agentes lerem em vez de perguntar (seção 8.4).

## 3. Portal (browser real na máquina do certificado)

Criação e navegação: `portal create URL ["Nome"] [--size WxH]`, `portal edit`,
`portal navigate`, `portal close`, `portal info`, `portal resize`, `portal ua [preset]`.

Inspeção: `portal snapshot` (árvore de acessibilidade com refs `@e1`…), `portal check`
(screenshot), `portal screenshot`, `portal text @e1`, `portal html`, `portal evaluate "js"`,
`portal wait @e3 [ms]`.

Interação: `click`, `fill`, `type`, `key`, `focus`, `select`, `check`/`uncheck`,
`selectall`, `clear`, `scroll`, `scrollintoview`, `hover`, `drag`.

Console: `portal logs-start` (uma vez, após navigate) → `portal logs` (lê e limpa buffer).

Android: `portal devices`, `portal create --simulator ID`, `tap`, `swipe`, `button`,
`home`, `lock`, `launch PACKAGE`, `terminate PACKAGE`, `a11y`.

> **`portal evaluate "js"` é a peça crítica da fase 0.** É o que permite executar
> `fetch` de dentro da página autenticada do PDPJ — exatamente a técnica que o
> projeto anterior usa para passar pelo WAF. Ver `docs/decisions/002`.

## 4. Gestão de equipe (só Maestro)

| Comando | Uso |
|---|---|
| `maestri recruit "Nome" [--preset P] [--role R] [--floor F] [--command C] [--dir PATH]` | cria teammate já conectado a mim |
| `maestri recruit "Novo" --preset P --replace "Antigo"` | troca o agente mantendo conexões, posição e rotinas |
| `maestri dismiss "Nome"` | remove teammate |
| `maestri connect "De" "Para"` | liga dois nós (agente ou nota) |
| `maestri preset list` / `role list` / `role show` | inventário |
| `maestri role create/write/edit/assign/delete` | papéis reutilizáveis (`--scope current\|global`) |

## 5. Rotinas agendadas (só Maestro)

`routine list/show/create/edit/enable/disable/run/delete`.
Agendas: `--every 30m`, `--daily 09:00`, `--weekly mon,fri@09:00`, `--once "2026-06-20 15:00"`.
Opções: `--terminal "Nome"`, `--reminder`, `--count N`, `--until DATE`, `--pre-run "..."`,
`--no-notify`, `--disabled`. A saída de `--pre-run` entra no placeholder `{{output}}`.

> Uso previsto: poll da Área de Download do PJe e verificação de janelas de manutenção.

## 6. Workspace e floors (só Maestro)

`workspace create "Nome" --dir PATH [--from "Origem"] [--group G] [--folder F]`,
`workspace move`, `workspace list`.
`floor create "Nome" [--branch B] [--existing-branch] [--no-git] [--copy-ground]`, `floor list`.

> Floors são clones isolados por git. É o mecanismo certo para dar a cada agente
> uma área do código sem conflito de merge (seção 8.4).

## 7. Diagnóstico

`maestri debug` — devolve Terminal ID, `MAESTRI_PIPE`, versão do CLI, PID e detalhe de token.
`maestri help [command]` / `maestri <command> --help`.

---

## 8. Divergências do briefing

| Briefing supunha | Realidade medida |
|---|---|
| `maestri ask "<nó>" "<prompt>"` | ✅ confirmado |
| `maestri check "<nó>"` | ✅ confirmado |
| `maestri note read\|write` | ✅ confirmado, mais `create/edit/stack/unstack/delete` |
| `maestri portal navigate\|snapshot\|click\|fill` | ✅ confirmado, mais ~25 subcomandos |
| `maestri list` | ✅ confirmado |
| **"Maestri roda em macOS"** | ❌ **Windows 10 Pro 19045**, MINGW64. Ver `docs/decisions/001` |
| agentes já disponíveis | ❌ malha vazia; recrutar antes de delegar |

Não documentado no briefing e útil: **`ask --batch`** (paralelismo real em uma chamada),
**`recruit --replace`** (troca de agente sem perder fiação) e **`floor create`**
(isolamento git por agente).
