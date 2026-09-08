# Matriz dos canais públicos — 24 TRTs

**Data:** 2026-09-08 · **Método:** um `GET` por host, sequencial, pausa de 1,5 s, sem
autenticação, **sem consultar nenhum processo e sem tocar em captcha**. Só a página/bundle
de entrada, para saber qual sistema atende cada TRT.
**Escopo do que isto prova:** alcançabilidade HTTP e identificação do sistema. **Não** prova
captcha por tribunal, **não** prova disponibilidade de inteiro teor em PDF.

---

## 1. Consulta processual pública — o padrão é UNIFORME nos 24

```
https://pje.trt{N}.jus.br/consultaprocessual/      N = 1..24
```

| TRT | HTTP | SPA Angular detectada | TRT | HTTP | SPA Angular detectada |
|---|---|---|---|---|---|
| 1 | 200 | sim | 13 | 200 | sim |
| 2 | 200 | sim | 14 | 200 | sim |
| 3 | 405¹ | — | 15 | 200 | sim |
| 4 | 200 | sim | 16 | 200 | sim |
| 5 | 202² | — | 17 | 200 | sim |
| 6 | 200 | sim | 18 | 200 | sim |
| 7 | 200 | sim | 19 | 200 | sim |
| 8 | 200 | sim | 20 | 200 | sim |
| 9 | 202² | — | 21 | 200 | sim |
| 10 | 200 | sim | 22 | 200 | sim |
| 11 | 200 | sim | 23 | 200² | — |
| 12 | 200 | sim | 24 | 200 | sim |

¹ TRT3 respondeu 405 (Method Not Allowed) nas duas variantes tentadas — anomalia isolada,
a investigar. Não é indício de ausência do sistema.
² 202 / 200 sem os marcadores do bundle: provável página intersticial de WAF ou desafio JS.
Não confirmado o que é. Não insistimos.

**Consequência:** **21 de 24 confirmadamente servem a mesma SPA de Consulta Pública do PJe**,
no mesmo caminho. Isso repete, na trilha pública, o achado da ADR 001 na trilha autenticada:
**não são 24 integrações, é uma.**

**E é uma integração que não serve ao projeto.** A ADR 005 mediu ao vivo, no TRT4, que a API
desta SPA (`pje-consulta-api`) devolve `tokenDesafio` + captcha ao abrir o processo, e só libera
a lista de documentos depois de resolvido. Como o artefato servido é o mesmo nos 24, a barreira
é estrutural, não local. **Não medimos o captcha nos outros 23 e não vamos medir**: a conclusão
operacional já está tomada (canal fora de escopo, ADR 004 e ADR 005), e sondar captcha em 23
tribunais seria exatamente o comportamento que a Resolução CSJT 139/2014 quer coibir.

## 2. Jurisprudência — existe um portal NACIONAL

**Achado principal:** `https://jurisprudencia.jt.jus.br/` responde 200 e se identifica como
**"FALCÃO — Sistema de busca de jurisprudência"** (SPA Angular). O host `juris.trt8.jus.br`
**redireciona para ele** — indício forte de consolidação nacional em andamento.

**MEDIDO em 2026-09-08 pelo navegador real (portal do Maestri).** Confirmado:
`/jurisprudencia-nacional/`, v2.15.3, feito pelo TRT9, **busca sem login**, e a busca pelo CNJ
do processo-teste **resolveu para o acórdão**, com relatoria, turma, data de juntada, ementa e
botões de inteiro teor. API pública descoberta lendo as XHR da SPA:
`/jurisprudencia-nacional-backend/api/no-auth/pesquisa?colecao=acordaos&tribunais=&page=&size=`.

**Acórdão vira uma integração nacional, sem autenticação** — não 24. Ressalvas medidas:
`httpx` puro recebe **403** ("tentativa inválida de acesso"), e o `fetch` in-page recebeu
**429** após poucas chamadas. Detalhe completo em `via-sem-autenticacao.md`, Canal 4.
Formato do inteiro teor e cobertura por tribunal seguem **não confirmados**.

Padrões por tribunal que responderam (`<400`):

| Padrão | TRTs |
|---|---|
| `https://pje.trt{N}.jus.br/jurisprudencia/` | 2, 6, 7, 10, 13, 16, 17, 18, 19, 20, 22, 23, 24 |
| `https://jurisprudencia.trt{N}.jus.br/` | 15 |
| `https://juris.trt{N}.jus.br/` → **redireciona para o nacional** | 8 |
| nenhum dos 4 padrões testados | 1, 3, 4, 5, 9, 11, 12, 14, 21 |

A linha "nenhum dos padrões" significa **que os 4 padrões que eu testei não respondem** — não
que o tribunal não tenha sistema de jurisprudência. TRT1, TRT3 e TRT9 têm sistema público
documentado, em host fora desses padrões. Fica `desconhecido`, não `inexistente`.

**Nada aqui prova inteiro teor em PDF sem login.** Isso precisa de um clique num resultado real,
por tribunal, e é a medição seguinte.

## 3. Diário — não há mais 24, há um

O DEJT foi substituído pelo **DJEN** em 2024-08-01 (acervo histórico do DEJT via portal do CSJT;
o DEJT saiu do ar em 2026-08-18). O DJEN é nacional, com API aberta:

```
GET https://comunicaapi.pje.jus.br/api/v1/comunicacao        # sem autenticação
```

Detalhes, campos e as ambiguidades abertas: `docs/canais-publicos/via-sem-autenticacao.md` §2,
Canal 2. **A coluna "diário por TRT" desta matriz não precisa ser preenchida** — o canal
nacional a torna obsoleta para os nossos fins.

## 4. O que esta matriz NÃO prova

- **Captcha por tribunal.** Medido só no TRT4 (ADR 005). Nos outros 23 é inferência estrutural
  (mesmo artefato servido), declarada como inferência.
- **Inteiro teor em PDF sem login.** Nenhum tribunal verificado. Zero downloads feitos.
- **Cobertura do FALCÃO.** Não sabemos se são 24 TRTs, quais períodos, nem se há API.
- **TRT3 (405) e TRT5/9/23 (interstício).** Anomalias registradas, não explicadas.
- `capabilities.yaml` não foi alterado. Nada daqui foi promovido a configuração de produção.

## 5. Próximas medições, em ordem de alavanca

1. **FALCÃO**: cobre os 24? serve inteiro teor? tem API? — portal do Maestri (navegador real),
   uma busca, um resultado. Colapsa 24→1 para acórdão, ou não.
2. **DJEN**: `link` e `/{hash}/certidao` devolvem peça ou certidão? — decide sentença/acórdão.
3. **DataJud**: os 24 aliases respondem à busca por CNJ? — fecha o seed nacional.
4. TRT3, TRT5, TRT9, TRT23: o que são aquelas respostas.

Protocolo sanitizado de 2 e 3: `docs/execucao/probe-canais-publicos.md` (a escrever — a tarefa
foi atribuída, o agente caiu por quota).
