# Runbook — login do titular e teste da via autenticada

Portal preparado em **2026-09-03**. Quando você puder logar, o resto é meu.

---

## O que já está pronto

- **Portal "PDPJ"** aberto na tela de login do SSO
  (`sso.cloud.pje.jus.br/.../auth`, redireciona para `portaldeservicos.pdpj.jus.br`).
  A tela oferece **CPF/senha** e **Entrar com gov.br**.
- **Portal "TRT4"** limpo, na home da consulta pública (fallback).
- **`research/captura-pos-login.js`** — script que instala o hook de captura de token e
  lê o Bearer que o app guardar. Não envia credencial nenhuma; só observa.

---

## O que você faz (só isto)

1. No Portal "PDPJ" (janela do Maestri), **faça login** como titular do certificado —
   por CPF/senha, gov.br, ou certificado (PJeOffice Pro). É ato seu; eu não automatizo.
2. Quando a página estiver **autenticada** (você vê a consulta/painel do PDPJ, não mais
   a tela de login), me diga **"logado"**.

Só isso. Não precisa navegar para o processo nem clicar em nada — eu faço daí pra frente.

---

## O que eu faço quando você disser "logado"

Em sequência, tudo pela via autenticada, sem tocar em captcha:

1. **Capturo a sessão** — rodo `research/captura-pos-login.js` no Portal para pegar o
   Bearer (de memória ou do storage do Keycloak).

2. **Testo H1 na via nacional (Via 0)** — a maior aposta arquitetural:
   ```
   GET https://portaldeservicos.pdpj.jus.br/api/v2/processos/0020890-39.2024.5.04.0015
   ```
   Procuro na resposta: `documentos[]`, `hrefBinario`, `idOrigem`, `_links`. Se a API
   nacional listar os documentos com link de binário, **24 integrações viram 1**.

3. **Busco o binário** — pelo href que a resposta trouxer, confirmo que vem PDF de
   verdade (não metadado). Fecha H1 no caminho que o projeto vai usar.

4. **Testo H2** — a mesma requisição por `httpx` no Python, com o mesmo Bearer e cookies,
   comparada com o `fetch` in-page. Diz se o volume roda em HTTP paralelo ou precisa de
   browser.

5. **Se a via nacional não cobrir o TRT4**, caio para a API autenticada do próprio TRT4
   (`pje.trt4.jus.br`), usando o que já medi: id interno `2131802`, header
   `X-Grau-Instancia: 1`. O processo é público (`segredoJustica=false`) e tem 1º (ATOrd)
   e 2º (ROT) grau.

6. **Baixo a petição inicial** deste processo, com hash e metadados — que é o **critério
   de saída da fase 2**.

Tudo registrado em `research/evidencia/` e na `capabilities.yaml`.

---

## Limites que valem durante o teste

- **Nada de captcha.** Se a via autenticada, por algum motivo, cair num captcha, paro e
  te aviso — não resolvo (ADR 004/005).
- **Certificado/PIN não passam pelo meu processo.** Só capturo token e cookies de sessão.
- **Uma requisição por vez, sem paralelismo**, até medir o teto (Q6c). Este é teste de
  reconhecimento, não de volume.
- A sessão do PDPJ tem validade; se expirar antes de terminarmos, é só relogar.

---

## Se a sessão cair ou você quiser retomar depois

O Portal continua aberto entre nossas conversas. Se a página deslogar sozinha, refaça o
login e me diga "logado" de novo — o runbook é o mesmo.
