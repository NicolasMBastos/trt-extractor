# Proposta de ADR 008 — o transporte é propriedade do canal, e o portal é a fonte

**Data:** 2026-09-08 · **Estado:** proposta. `docs/decisions/` é do Maestro; promova este
arquivo a `docs/decisions/008-...` se aceitar.
**Motivo:** duas medições de 2026-09-08 e uma decisão de estratégia do dono do projeto
contradizem parcialmente a ADR 002.

---

## 1. O que a ADR 002 dizia, e o que ela não cobria

A ADR 002 (adendo 2) mediu, no PDPJ nacional: `httpx` HTTP/1.1 sem UA → **403**;
`httpx` `http2=True` + UA de browser → **200**, em listagem e binário. Conclusão registrada:
`HttpxTransport` faz todo o volume, sem fazenda de browser.

**Isso continua verdadeiro — para o PDPJ.** O que a ADR não disse é que a conclusão vale
para *aquele canal*, não para o projeto.

## 2. A medição que força a revisão

Em 2026-09-08, no FALCÃO (`jurisprudencia.jt.jus.br`, jurisprudência nacional da JT), com a
API pública `no-auth` descoberta lendo as XHR da SPA:

| Cliente | Resultado |
|---|---|
| `httpx` HTTP/2 + UA de Chrome + Referer | **403** `{"userMessage":"Tentativa inválida de acesso ao sistema"}` |
| `fetch` de dentro da página | **responde** (e depois **429**, limitador ativo — paramos ali) |

Exatamente o inverso do PDPJ. Dois canais públicos brasileiros, dois transportes
incompatíveis, mesma máquina, mesma hora.

## 3. Decisão

**3.1 — O transporte é propriedade do canal, medido por canal, nunca herdado.**
`capabilities.yaml` já tem o campo; o que muda é a regra: nenhum canal novo herda o
transporte de outro, nem por analogia, nem por "é tudo `jus.br`". Canal sem medição fica
`desconhecido` e não roda em volume.

Isto **não** é uma correção da ADR 002 — é o reconhecimento de que ela é uma medição do
PDPJ, e de que o `Transport` ser um `Protocol` separado do `Adapter` (ADR 002) já era a
decisão certa por esta exata razão. O contrato estava à frente da evidência.

**3.2 — A fonte de aquisição é o portal autenticado, e é ele que dá "tudo".**
Decisão de estratégia do dono do projeto, e ela casa com o que já está provado:
`portaldeservicos.pdpj.jus.br` devolve, para um CNJ, os metadados **e a lista completa de
documentos**, cada um com `hrefBinario`, `tipo.codigo` nacional e `nivelSigilo` por
documento. Um login alcança os 24 TRTs (ADR 001). A petição inicial já saiu de lá.

Consequência: **os canais públicos deixam de ser linha de aquisição** e passam a ser o que
mediram ser (`docs/canais-publicos/via-sem-autenticacao.md`):

| Canal | Papel após esta ADR |
|---|---|
| PDPJ autenticado | **aquisição. As 5 classes. Linha principal.** |
| DataJud | seed e triagem, fora da credencial |
| DJEN | sinal tipado de existência de peça + feed incremental, fora da credencial |
| FALCÃO | acórdão de graça, quando casar; nunca obrigatório |
| Consulta pública PJe | fora de escopo (captcha; ADR 004/005) |

**3.3 — Navegador é obrigatório, e não para raspar DOM.**
O handshake por certificado (PJeOffice Pro → Keycloak) é ato do titular e só existe em
browser. Depois dele, a página está autenticada — e é de dentro dela que se busca o
conteúdo, via `InPageFetchTransport`.

**Raspar o DOM está descartado**, e a razão é prática, não estética: o portal já entrega a
lista de documentos tipada e com link direto do binário. Raspar a mesma informação da tela
dá os mesmos bytes, mais devagar, e quebra a cada mudança de layout — além de perder
`tipo.codigo` e `nivelSigilo`, que são justamente o que faz a classificação camada 1 e o
respeito ao sigilo funcionarem.

`api/v2/...` **não é "API externa"**: é o backend do próprio portal, a mesma chamada que a
página faz ao clicar. Usá-la é raspar o portal corretamente.

**3.4 — Lentidão é requisito, não concessão.**
O dono do projeto declarou que tempo não é restrição. Isso é aproveitado como política:
ritmo humano, jitter, teto por hora abaixo do medido, horário comercial. O recurso escasso
não é tempo — é a credencial do advogado titular (ADR 007). Ir devagar protege o recurso
escasso.

## 4. O que isto muda no código

Nada de novo em contrato. O que faltava era implementação:

- `core/inpage_transport.py` — `InPageFetchTransport`, implementado em 2026-09-08.
  O `Protocol Transport` já o nomeava; `Via.BROWSER` já existia; `playwright>=1.44` já estava
  em `[project.optional-dependencies] browser`. O slot estava desenhado e vazio.
- Propriedades que ele garante, e que rodar dentro da página não dá de graça:
  uma identidade por página (recusa `Session` de outra credencial), cabeçalho controlado pelo
  browser recusado em vez de ignorado em silêncio, bytes por base64 sem perda, resposta opaca
  de redirect não passando por sucesso vazio, e mensagem de erro sem URL nem token.
- Paridade deliberada de tradução de status com `HttpxTransport`: o adapter não muda de
  comportamento ao trocar de transporte.
- 34 testes, sem browser e sem rede (página é um duplo). Suíte: 202 passed, 1 skipped.
  Ruff, format e mypy limpos.

## 5. O que esta proposta NÃO decide

- **Onde vive a chave do `storage_state`.** É decisão humana de segredo e modelo de ameaça
  (tarefa 5 do relatório final). **Bloqueia a fase 1**, que esta estratégia torna prioridade.
- **Teto de taxa do FALCÃO.** Sabemos que existe (429). Valor seguro exige o protocolo L4/L5,
  não tentativa e erro.
- **Endpoint exato do PDF de inteiro teor do FALCÃO.** A rota do frontend se chama
  `pdfInteiroTeor` e há uma rota de "Validação de PDF" — o artefato é PDF, o endpoint dos
  bytes não foi capturado.
- **Como casar CNJ → acórdão com segurança.** O FALCÃO acha por **texto**, não por chave: a
  rota `/pesquisa/numero/{cnj}` chama o mesmo `no-auth/pesquisa?texto=<cnj>`. A busca pelo CNJ
  do processo-teste devolveu **2 resultados, um deles de outro processo**. Portanto: casar por
  igualdade exata no campo de número do resultado, nunca por ranking; zero casamento é
  terminal legítimo; e vários acórdãos do mesmo processo não se desempatam em silêncio.
- `capabilities.yaml` não foi alterado.
