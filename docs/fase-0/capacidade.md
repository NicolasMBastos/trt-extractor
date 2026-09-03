# Fase 0 — relatório de capacidade

**Status: parcial.** Atualizado 2026-09-03.
**Alvo primário: TRT4 (Rio Grande do Sul).** TRT2 e TRT13 são contraste, depois.

Cada afirmação abaixo tem evidência. Onde não tem, está marcado `⬜ não medido` — e
`⬜` não é resposta, é dívida.

---

## 1. Certificado ✅ RESPONDIDO

Não depende de tribunal. Detalhe e evidência em `docs/decisions/003`.

| Pergunta | Resposta |
|---|---|
| A1 ou A3? | **A1**, todos os 4. CSP de software, chave exportável |
| A3 configurado? | **não** — `list.a3=` vazio no PJeOffice |
| App de gestão | **PJeOffice Pro**, `C:\Program Files\PJeOffice Pro`, ativo (config de 2026-09-01) |
| Repositório | `MSCAPI` (store do Windows) |
| Estratégia | `auth.strategy=ONE_TIME` |
| Credenciais válidas | **1 de 4** (Certisign RFB G5, vence 2027-05-27). As outras 3 expiraram |

**Consequência:** emissão de sessão é paralelizável — o certificado sai do caminho
crítico de throughput. O gargalo mudou para a credencial única.

---

## 2. Superfície de login do PDPJ ✅ MEDIDO AO VIVO

`https://portaldeservicos.pdpj.jus.br/consulta` redireciona para o SSO:

```
sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/auth
  ?client_id=portalexterno-frontend
  &redirect_uri=https://portaldeservicos.pdpj.jus.br
  &response_type=code&response_mode=fragment&scope=openid
```

Título da página: *"JUSBR - Justiça em um só lugar"*.

Formas de entrada oferecidas na tela:

| Elemento | O que é |
|---|---|
| input CPF/CNPJ + input Senha + submit "Entrar" | **login por CPF/senha** |
| link "Entrar com **gov.br**" → `/broker/acessogo` | federado gov.br |
| — | **nenhum botão de certificado visível nesta tela** |

**Q2 — CPF/senha existe como via de login.** Isso é relevante: se ela servir para
consulta *e* download, o certificado sai inteiramente do caminho crítico, que é o que o
briefing mandava testar antes de construir qualquer coisa em cima do certificado.

⬜ **Não medido:** se a sessão obtida por CPF/senha tem o mesmo alcance da obtida por
certificado. **Não fiz login** — a autenticação é ato do titular (ADR 004).

`client_id=portalexterno-frontend` é dado útil para reproduzir o fluxo OAuth2.

---

## 3. TRT4 — estrutura ✅ MEDIDO AO VIVO

`https://pje.trt4.jus.br/consultaprocessual/` — *"Consulta Processual Unificada"*.

| Superfície | URL |
|---|---|
| Busca por número de processo | `/consultaprocessual/` (campo público, sem login) |
| **Consulta Cidadão** | `/consultaprocessual/consulta-cidadao` |
| Consulta de pautas | `/consultaprocessual/pautas` |
| Sessão de Julgamento | `/consultaprocessual/sessao-julgamento` |
| **Acesso restrito** | `/consultaprocessual/login` |
| **PJe 1º grau** | `https://pje.trt4.jus.br/primeirograu` |
| **PJe 2º grau** | `https://pje.trt4.jus.br/segundograu` |

**Confirma a premissa do briefing:** 1º e 2º grau são sistemas separados. A chave
`(numero_cnj, grau)` do esquema está correta.

Também valida o endpoint que o probe MNI ataca: `/primeirograu/intercomunicacao?wsdl`
casa com a estrutura real de paths do TRT4.

---

## 4. H1 — a API PDPJ entrega o binário? ⬜ EM ABERTO

**Continua a pergunta mais importante da fase.**

Evidência levantada (análise estática de `TaxMap-main`, 5.346 linhas):

| Termo procurado | Ocorrências em `jusbr.py` + `pdpj_selenium.py` + `config.py` |
|---|---|
| `hrefBinario` | **0** |
| `href_binario` | **0** |
| `/binario` | **0** |
| `/documentos` | **0** |
| `idOrigem` | **0** |
| `documentos[` | **0** |

**Conclusão:** o TaxMap **nunca tentou** obter documento pela API. Usa `api/v2/processos`
só para *listar* processos (`cpfCnpjParte`, `filter=classe.codigo in N`, `searchAfter`) e
volta ao DOM para o PDF.

Isso resolve a ambiguidade que eu tinha levantado em ADR 001: não é que a API não sirva
binário — é que **ninguém testou**. A hipótese (b) se confirma. H1 segue viva e vale ser
testada, porque o prêmio é colapsar 24 integrações em 1.

⬜ **Bloqueado por:** processo-teste real (item 0.3) + login do titular (item 0.5).

---

## 5. H2 — o WAF rejeita cliente não-browser? ⚠️ RESPOSTA PARCIAL, E BOA

**A hipótese estava mal formulada. São dois canais, com respostas diferentes.**

### 5.1 Download do binário: `requests` puro FUNCIONA

`taxmap/pdpj_selenium.py:1409` — `_baixar_url_http()`, em produção:

```python
cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
resp = requests.get(pdf_url, cookies=cookies, timeout=60, stream=True)
```

Cliente HTTP do Python, **só com cookies colhidos do browser**. Sem fetch in-page, sem
impressão TLS/HTTP2 de navegador. É o fallback de `tentar_download_direto` (`:1482`),
alimentado por hrefs reais colhidos do DOM (`:1588`, `:1616`, `:1725`).

**Consequência forte:** a operação de maior volume — baixar PDF — **não precisa de um
browser por download**. `HttpxTransport` é viável para `fetch_artifact`. O teto de
concorrência volta a ser de rede, não de memória por contexto.

### 5.2 API JSON: continua em aberto

O comentário sobre WAF (`jusbr.py`, sobre `_JUSBR_API_FETCH_JS`) refere-se à chamada
**JSON** de `api/v2/processos`, não ao download de binário. Para esse canal não há
evidência de tentativa com `httpx`, então segue não medido.

### 5.3 Efeito no projeto

Amenda a ADR 002 (ver adendo lá). A camada `Transport` continua certa — mas agora se
sabe que provavelmente é **mista**: `InPageFetchTransport` para a API JSON,
`HttpxTransport` para o binário. Era exatamente para isso que a camada existia.

---

## 6. MNI (Q4) ⬜ EM MEDIÇÃO

`scripts/probe_mni.py` entregue (332 linhas, um GET por tribunal, sem credencial, sem
chamar operação SOAP). Alvos:

- `https://pje.trt4.jus.br/primeirograu/intercomunicacao?wsdl` ← **primário**
- `https://pje.trt2.jus.br/primeirograu/intercomunicacao?wsdl`
- `https://pje.trt13.jus.br/primeirograu/intercomunicacao?wsdl`

Primeira execução deu `WinError 10061` nas três — recusa de conexão do sandbox do agente,
não resposta do tribunal. Reexecução com rede liberada em andamento.

Resultado vai para `research/mni-probe.md`.

---

## 7. Pendências, em ordem de impacto

| # | Pendência | Bloqueia | Quem |
|---|---|---|---|
| 1 | Número de processo-teste no TRT4, público, com petição inicial | H1, H2.2, Q5, Q6 | **dono do projeto** |
| 2 | Login do titular no Portal (certificado ou CPF/senha) | H1, H2.2, Q3 | **titular** |
| 3 | Resultado do probe MNI | Q4a–c | Codex, em execução |
| 4 | Mais certificados válidos? (P2) | plano de volume da fase 6 | **dono do projeto** |
| 5 | Laudo/perícia entra na fase 4 ou fica para depois? | escopo do classificador | **dono do projeto** |

---

## 8. Nota sobre a equipe

`AGY` (Antigravity) está **indisponível**: falha com *"Agent execution terminated due to
error"* em qualquer entrada, inclusive num prompt trivial de duas palavras. Três
tentativas, conforme o protocolo da seção 8.3 do briefing. Provável esgotamento da
*Antigravity Starter Quota*. A tarefa de análise de artefato foi absorvida por mim — o
resultado está nas seções 4 e 5 acima.

`Codex` e `OpenCode` operacionais.
