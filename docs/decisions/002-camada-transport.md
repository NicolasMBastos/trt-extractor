# 002 — Separar `Transport` do `TribunalAdapter`

**Data:** 2026-09-03 · **Estado:** aceita

## Contexto

O briefing assume, na seção 2.3, que o volume roda em HTTP paralelo comum:

```
certificado (1x, lento) → access_token → volume em httpx paralelo → renova
```

O código de produção do projeto irmão contradiz isso, em comentário no ponto exato da
implementação (`taxmap/jusbr.py`, sobre `_JUSBR_API_FETCH_JS`):

> `# fetch executado DENTRO da pagina (Chrome autenticado): mesma origem, cookies`
> `# AWSALB automaticos, TLS/HTTP2 de navegador -> passa pelo WAF do PDPJ.`

Ou seja: portar o Bearer para `httpx` pode falhar no WAF, porque o que é verificado não
é só o token — é o cookie de load balancer e a impressão TLS/HTTP2 do cliente. A solução
deles foi executar `fetch` de dentro da página via CDP, com hook em
`fetch`/`XMLHttpRequest.setRequestHeader` para capturar o `Authorization`.

Isso é uma afirmação do autor anterior, não uma prova — pode ser folclore. Mas se for
verdade, muda o substrato de execução do projeto inteiro, e a decisão de qual cliente
HTTP usar não pode ficar espalhada por 24 adapters.

## Decisão

Inserir uma camada entre o adapter e a rede:

```
TribunalAdapter  (o quê: authenticate, list_documents, request_download,
                        poll_download, fetch_artifact)
      ↓ usa
Transport        (como: request / fetch_bytes)
      ↓ carrega
Session          (quem: token, cookies, validade, credencial de origem)
```

Duas implementações de `Transport`, mesma assinatura:

- `HttpxTransport` — cliente HTTP assíncrono normal, paralelizável.
- `InPageFetchTransport` — executa `fetch` dentro da página autenticada, herdando
  cookies de load balancer e a impressão TLS/HTTP2 do browser.

A escolha vem de `capabilities.yaml` (`transporte:`), **por tribunal, medida**. Default
`desconhecido` até H2 responder.

`fetch_bytes` existe separado de `request` porque o caminho in-page precisa serializar
bytes de volta do JS (base64) em vez de devolver o corpo cru. Esconder isso dentro de
`request` faria a interface mentir.

## Alternativas descartadas

- **Assumir `httpx` e corrigir depois.** Descartada: se H2 for verdadeira, o retrabalho
  atinge todos os adapters de uma vez, exatamente na fase em que já existem vários.
- **Assumir browser sempre.** Descartada: joga fora paralelismo real onde o WAF não
  barra, e Playwright em todo lugar é caro em memória e frágil de operar.
- **Deixar cada adapter escolher.** Descartada: é a decisão vazando para 24 lugares.
  Um adapter deve saber falar com *seu* tribunal, não decidir política de transporte.

## Consequências

- H2 pode ser respondida **depois** de os contratos estarem escritos, sem reescrever
  adapter nenhum. É o que permite a fase 0 não bloquear a escrita de contratos.
- Tribunais diferentes podem usar transportes diferentes, o que é provável: o WAF do
  PDPJ nacional e o de um TRT pequeno não têm por que se comportar igual.
- O teto de concorrência passa a ser propriedade do transporte, não do adapter:
  `httpx` limita por rede, `in_page_fetch` limita por memória/CPU de contexto. O plano
  de capacidade tem que ler os dois.
- Playwright sobe de "nível 4 de 5" para transporte de primeira classe — **mas como
  transporte, nunca como scraper de DOM**. `page.evaluate(fetch)` é estável; `click` em
  seletor CSS não é. O briefing está certo em desconfiar do Playwright-como-scraper, e
  essa desconfiança fica mantida.

---

## Adendo — 2026-09-03: a hipótese estava mal formulada

A análise estática do TaxMap (ver `docs/fase-0/capacidade.md` §5) mostrou que H2 tratava
como um canal só o que são **dois**, com respostas diferentes:

- **Download de binário:** `taxmap/pdpj_selenium.py:1409` (`_baixar_url_http`) baixa o PDF
  com `requests.get(pdf_url, cookies=cookies)` — cliente HTTP do Python, só com cookies
  do browser, sem fetch in-page. **Em produção.** Logo, `HttpxTransport` serve para
  `fetch_artifact`, que é a operação de maior volume do pipeline.
- **API JSON (`api/v2/processos`):** é a essa chamada que o comentário sobre WAF se
  refere. Continua não medida.

**A decisão não muda — ela se confirma.** A camada `Transport` existia justamente para
permitir que a resposta fosse diferente por canal e por tribunal. O cenário provável
agora é **misto**: `InPageFetchTransport` para a API JSON, `HttpxTransport` para o
binário. Um adapter que tivesse a escolha embutida teria que ser reescrito; com a camada,
é configuração.

Consequência prática: o teto de concorrência do download volta a ser de rede, não de
memória por contexto de browser. O plano de capacidade da fase 6 melhora
substancialmente — mas só depois de H2.2 ser medida de fato.
