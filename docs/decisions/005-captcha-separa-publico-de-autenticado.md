# 005 — O captcha separa o caminho público do autenticado

**Data:** 2026-09-03 · **Estado:** aceita (medido ao vivo)

## Contexto

Com o processo-teste `0020890-39.2024.5.04.0015` do TRT4, medi ao vivo a API da
consulta pública (`pje.trt4.jus.br/pje-consulta-api/api`). Evidência completa em
`research/evidencia/trt4-consulta-api-2026-09-03.md`.

Dois fatos novos e firmes:

1. **A API serve binário.** O bundle expõe `/documentos/conteudo`, `/documentos/idUnico/`
   e `documentoPDF`. Não é uma API só de metadados. Isso responde H1 no nível estrutural:
   existe endpoint de conteúdo de documento.
2. **O caminho público é barrado por captcha.** Abrir o processo (`/processos/{id}`)
   devolve `tokenDesafio` + imagem de captcha; a lista de documentos só abre depois de
   resolver. A própria tela cita a Resolução 139/2014 do CSJT. É controle anti-automação
   explícito.

## Decisão

**Há dois caminhos, e eles não se misturam:**

| Caminho | Identidade | Captcha? | Serve para volume? |
|---|---|---|---|
| Consulta pública (`pje-consulta-api`) | anônima | **sim** | **não** |
| Autenticado (PDPJ / PJe restrito) | certificado/login | não | **sim** — é a via do projeto |

O captcha existe *porque* o caminho público é anônimo. O caminho autenticado não o tem,
porque a identidade já está estabelecida — é esse o ponto de autenticar. Logo:

1. **O caminho público está fora do escopo de aquisição em volume.** Não porque não
   sirva tecnicamente, mas porque a única forma de escalá-lo seria resolver captcha
   automaticamente, e isso é evasão de controle — proibido pela ADR 004 e pelo
   invariante 2. Não faço, e registro que não faço.
2. **A via de volume é a autenticada.** O `X-Grau-Instancia` e o padrão de rotas
   (`/processos/{id-interno}`, `/documentos/...`) medidos aqui são provavelmente os
   mesmos na API autenticada — mas isso é a próxima medição (H1 no caminho autenticado),
   e depende do login do titular.
3. **O id interno do processo importa.** As rotas de documento usam o id interno
   (`2131802`), não o CNJ. `list_documents` do adapter tem que resolver CNJ → id interno
   antes de pedir documento. O contrato já suporta isso (`DocumentoRef.id_origem`), mas o
   adapter do TRT4 precisa do passo de resolução.

## O que isto faz com H1 e H2

- **H1 (a API serve binário?):** **sim**, comprovado no bundle e pela existência de
  `/documentos/conteudo`. Falta só confirmar o retorno de bytes reais no caminho
  autenticado — não é mais dúvida de arquitetura, é confirmação de campo.
- **H2 (WAF rejeita não-browser?):** as chamadas a `dadosbasicos` e `/processos/{id}`
  funcionaram por `fetch` in-page com credenciais de sessão anônima. Ainda não testei
  `httpx` puro contra elas. Mas some com o drama: como o caminho de volume é o
  autenticado e o download de binário já se provou funcionar por `requests`+cookies no
  TaxMap (ADR 002, adendo), o cenário `httpx` para binário segue de pé.

## Consequência para o roadmap

A fase 0 tem agora **um alvo real, público, sem segredo de justiça, com 1º e 2º grau** —
ideal para a fase 2 (um processo ponta a ponta) e para provar dedup na fase 3, assim que
o caminho autenticado abrir.

O bloqueio remanescente é único e conhecido: **login do titular**, para medir a API
autenticada e fechar H1/H2 no caminho que o projeto de fato vai usar.
