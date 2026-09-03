# 006 — Preservação de sessão

**Data:** 2026-09-03 · **Estado:** aceita (design; implementação na fase 1)

## Contexto

Medido ao vivo no TRT4 (`research/evidencia/trt4-sessao-autenticada-2026-09-03.md`):

- A sessão autenticada é um **JWT `access_token`** em cookie de `pje.trt4.jus.br`,
  legível por JS (não httpOnly).
- **Validade: 60 minutos exatos.** Sem refresh token embutido.
- A renovação depende do SSO Keycloak, que mantém sessão de dispositivo — é isso que
  torna o login por certificado + MFA um evento raro (uma vez por dispositivo), e não a
  cada hora.
- O download de binário funciona por `requests`/`httpx` só com os cookies da sessão
  (provado no TaxMap, ADR 002 adendo). Ou seja: **a sessão é portável para fora do
  browser** depois de emitida.

O problema que o dono do projeto levantou: como não obrigar o titular a logar toda hora,
e como manter N workers rodando sobre uma sessão que vive 1 hora.

## Decisão

Modelo em três camadas, na ordem em que serão construídas (fase 1):

### 1. Emissão — cara, manual, rara

```
titular → certificado (PJeOffice) → SSO Keycloak (+MFA 1x/dispositivo)
        → cookies de sessão (access_token JWT, Xsrf-Token, ...)
```

É ato do titular, feito no browser real. **Nunca automatizado** — o certificado e o PIN
não entram no processo (ADR 003, ADR 004). Acontece uma vez por dispositivo enquanto o
Keycloak mantiver a sessão de dispositivo viva.

### 2. Captura e persistência — uma vez por emissão

Depois do login, capturar o **`storage_state`** (cookies + storage) do contexto —
via Playwright `context.storage_state()` ou CDP `Network.getAllCookies`. É o mesmo que o
TaxMap faz (`extract_pdpj_session`).

Persistir com estas regras:
- **Cifrado em repouso.** A sessão é credencial viva; vazá-la é vazar o acesso do
  titular. Nunca em texto puro, nunca no git (`.gitignore` já cobre `storage_state*`,
  `cookies*`, `session*`).
- **Escopo por `(tribunal, credencial)`** — a chave do pool. Um `storage_state` por par.
- **Com metadados de validade:** `emitido_em`, `expira_em` (do `exp` do JWT), `credencial_id`.

### 3. Uso e renovação — barato, paralelo, proativo

- Os workers **replayam a sessão** com `httpx` (cookie jar), sem browser, para a maior
  parte do volume (download de binário). Um browser vivo fica só para o que exigir
  `InPageFetchTransport` (ADR 002).
- **Renovação proativa:** um único guardião renova a sessão **antes** de `expira_em`
  (margem de ~10 min sobre os 60), tocando um endpoint autenticado leve
  (`pje-seguranca/api/token/perfis`) para forçar o Keycloak a reemitir o `access_token`,
  e recaptura o `storage_state`. Se o Keycloak ainda tem sessão de dispositivo, isso é
  silencioso; se não, cai para (4).
- **Single-flight na renovação:** enquanto um guardião renova, os workers esperam a nova
  sessão — nunca N renovações concorrentes da mesma credencial (é o que dispara alarme de
  "credencial pedindo volume anormal").
- **TTL curto no cache de sessão** e checagem de `exp` antes de cada lote.

### 4. Reautenticação — quando a renovação falha

Se a renovação silenciosa falhar (sessão de dispositivo do Keycloak expirou, ou o
certificado venceu), o pool **pausa aquela credencial**, registra na auditoria e
**notifica o titular** para relogar. Não tenta contornar. Com uma credencial só (ADR 003),
isso pausa o pipeline daquele tribunal — o que reforça a pergunta P2 (mais certificados).

## O que medir na fase 1 para calibrar

- Se tocar `perfis` de fato **estende** o `exp`, ou se a renovação exige refresh explícito
  no Keycloak (`grant_type=refresh_token` no endpoint de token do SSO).
- Quanto dura a **sessão de dispositivo** do Keycloak (o teto real entre logins manuais) —
  é diferente dos 60 min do access_token. Pode ser dias.
- Se o mesmo `storage_state` serve para `httpx` puro contra a API (H2 no caminho
  autenticado), ou se algum endpoint exige a impressão do browser.

## Alternativas descartadas

- **Exportar o `.pfx` e reautenticar por mTLS a cada expiração, sem o titular.**
  Descartado (ADR 003/004): tira o certificado do repositório do SO e o põe no processo,
  piorando a segurança, para resolver um problema que a sessão de dispositivo do Keycloak
  já ameniza.
- **Sessões descartáveis (relogar por job).** Inviável: o MFA por dispositivo torna cada
  login um evento com fricção humana. A sessão persistente é justamente o que o MFA
  permite e recompensa.
- **Guardar o JWT cru e reusar.** Insuficiente: expira em 1h e vários endpoints conferem
  o cookie `Xsrf-Token` junto. Persistir o `storage_state` inteiro, não só o token.

## Critério de saída (fase 1, do briefing)

> 50 sessões emitidas e renovadas em sequência sem intervenção manual.

Com uma credencial e sessão de dispositivo viva, isto vira: 50 ciclos de
renovação/replay do `storage_state` sem novo login manual — medível assim que a fase 1
começar.
