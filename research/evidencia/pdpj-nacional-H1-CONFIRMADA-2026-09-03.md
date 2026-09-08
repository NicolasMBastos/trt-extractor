# H1 CONFIRMADA — API nacional PDPJ serve o binário (2026-09-03)

Login por certificado do titular no **portaldeservicos.pdpj.jus.br** (Portal de
Serviços / Jus.br nacional). Processo-teste: **0020890-39.2024.5.04.0015** — de
**terceiro** (titular sem vínculo), **público** (`nivelSigilo: 0`), do **TRT4**.

Medido ao vivo. Nenhum token, PDF ou dado pessoal gravado neste arquivo.

## O resultado que muda a arquitetura

```
GET /api/v2/processos/{cnj}                → 200, 219 KB, metadados + 151 documentos
GET /api/v2/processos/{cnj}/documentos/{uuid}/binario  → 200, %PDF-1.4  ← O BINÁRIO
```

**Um login nacional entrega o PDF de processo público de terceiro, de qualquer TRT.**
Isso responde H1 e valida a Via 0 (ADR 001): não são 24 integrações, é uma.

## Estrutura da resposta de processo

`processo`: `nivelSigilo, siglaTribunal, numeroProcesso, tramitacaoAtual, tramitacoes`
`tramitacaoAtual`: `idOrigem, instancia, grau, classe, distribuicao, movimentos,
  assunto, partes, tribunal, documentos[], permitePeticionar, processosRelacionados,
  idFonteDadosCodex, ativo`

## Estrutura de cada documento (o que importa para o projeto)

```
sequencia        ordem de juntada — sinal forte para petição inicial (camada 2)
dataHoraJuntada
idCodex          id nacional do documento
idOrigem         id no tribunal de origem
nome             ex.: "Decurso de prazo e remessa ao gabinete...pdf"
nivelSigilo      PUBLICO | (outros) — o filtro de segredo por documento
tipo:            CODEBOOK NACIONAL de tipo de documento
  { codigo, nome, idCodex, idOrigem }   ex.: {codigo:402, nome:"CERTIDÃO"}
hrefBinario      /processos/{cnj}/documentos/{uuid}/binario   → o PDF
hrefTexto        /processos/{cnj}/documentos/{uuid}/texto      → camada de texto
```

## Três consequências grandes

1. **Classificação camada 1 fica nacional.** `tipo.codigo` é um codebook do CNJ, o mesmo
   nos 24 TRTs — muito mais confiável que o `tipoDocumento` inconsistente que o briefing
   temia. A petição inicial tem um código nacional; achá-lo elimina ambiguidade.

2. **`hrefTexto` pode dispensar OCR.** Se a API serve a camada de texto do documento, o
   OCR (fase 4) vira exceção, não regra — só para digitalizações sem texto. A confirmar.

3. **`nivelSigilo` por documento** dá o SIGILOSO terminal com granularidade de peça, não
   só de processo. Exatamente o que a máquina de estados precisa.

## Ressalva de confiabilidade (investigar na fase 1)

A **primeira** chamada ao `/binario` devolveu 57 bytes de JSON (`{"cod...`); a segunda,
idêntica, devolveu o PDF. Pode ser geração sob demanda (submit→poll→fetch) ou transiente.
Não confirmado. O adapter precisa tratar o JSON curto como "ainda não pronto / retry",
não como binário. Alinhado ao pipeline submit→poll→fetch do briefing.

## O que falta

- **H2:** a mesma chamada por `httpx` (Python) com o mesmo Bearer passa, ou o WAF barra?
  Próximo teste. Decide HttpxTransport vs InPageFetchTransport (ADR 002).
- **Baixar a petição inicial** deste processo (achar o doc de tipo inicial pela sequência
  ou pelo `tipo.codigo`) — critério de saída da fase 2.
- **TTL da sessão nacional** (o do TRT4 é 60 min; medir o do portaldeservicos).

---

# ADENDO — H2 respondida e FASE 2 concluída (mesma sessão)

## H2 — o WAF barra httpx? FALSO, com a correção

| Cliente | Config | Resultado |
|---|---|---|
| httpx | HTTP/1.1, sem User-Agent | **403 Forbidden** (HTML nginx) |
| httpx | **HTTP/2 + User-Agent de browser** | **200**, 220 KB — igual ao browser |
| httpx | HTTP/2 + UA, endpoint `/binario` | **200, %PDF, application/pdf** |

**O WAF não checa impressão TLS (JA3).** Ele barra HTTP/1.1 e/ou ausência de
User-Agent. httpx com `http2=True` + UA de Chrome passa em tudo — listagem E binário.

**Consequência:** `HttpxTransport` é o substrato de volume. NÃO precisa de browser por
download. O teto de concorrência é de rede, não de memória por contexto. `InPageFetchTransport`
deixa de ser necessário para o caminho nacional (fica como carta na manga, não como plano).

O comentário do TaxMap ("TLS/HTTP2 de navegador passa pelo WAF") estava meio certo: HTTP/2
importa — mas httpx faz HTTP/2, então um cliente Python resolve. Eles não testaram httpx
com http2=True; por isso ficaram no browser.

## FASE 2 — petição inicial baixada ponta a ponta

```
processo:  0020890-39.2024.5.04.0015 (TRT4, publico, terceiro)
documento: seq=1, tipo.codigo=202 "Peticao Inicial"  (2 sinais concordam)
download:  httpx http2+UA -> 200, 561.007 bytes, %PDF
storage:   LocalCASStorage -> sha256 d5da6bfab2...e62b2
           fanout ab/cd, escrita atomica, idempotente, releitura conferida
metadados: cnj + grau=1 + tipo=peticao_inicial(202) + seq=1
```

**Critério de saída da fase 2 CUMPRIDO:** petição inicial de um processo conhecido em
disco, com hash e metadados corretos. Arquivo em `data/blobs/` (gitignored).

## Onde isto deixa o projeto

- **Via 0 nacional é O caminho.** 24 integrações -> 1, para processo público.
- **Transporte: httpx (http2+UA).** Sem fazenda de browser.
- **Certificado só no handshake**, como o princípio queria: browser vivo apenas para o
  login manual do titular; todo o volume em httpx com o Bearer.
- Falta: TTL da sessão nacional, teto de concorrência (Q6c), e o `hrefTexto` (pode
  dispensar OCR).
