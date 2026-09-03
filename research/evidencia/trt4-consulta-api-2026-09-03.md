# TRT4 — API da consulta pública, medida ao vivo (2026-09-03)

Processo-teste: **0020890-39.2024.5.04.0015** (fornecido pelo dono do projeto).
Método: Portal do Maestri, hook em fetch/XHR + leitura do bundle JS. Sem quebrar nada.

## Base da API
```
https://pje.trt4.jus.br/pje-consulta-api/api
```
Descoberta via performance.getEntriesByType('resource'), não por chute.

## Endpoints confirmados (status real)

| Endpoint | Método | Header | Status | Devolve |
|---|---|---|---|---|
| `/processos/nrprocesso/{cnj-formatado}` | GET | — | 200 (pela UI) | lista com graus disponíveis |
| `/processos/dadosbasicos/{cnj-digitos}` | GET | `X-Grau-Instancia: 1` | **200** | `[{id, numero, classe, codigoOrgaoJulgador, segredoJustica, juizoDigital}]` |
| `/processos/{id}` | GET | `X-Grau-Instancia: 1` | **200** | `{tokenDesafio, imagem}` — **CAPTCHA** |
| `/captcha?idProcesso={id}` | GET | — | (UI) | imagem do captcha |

Sem o header `X-Grau-Instancia`, `dadosbasicos` responde **500 ARQ-012 "Grau da
instância não definido"**. Path errado responde **404 ARQ-013** com JSON estruturado.
O servidor é estrito: não há como adivinhar path, tem que vir do bundle ou da UI.

## Dados reais do processo (1º grau)
```json
[{"id":2131802,"numeroIdentificacaoJustica":504,"numero":"0020890-39.2024.5.04.0015",
  "classe":"ATOrd","codigoOrgaoJulgador":"0015","segredoJustica":false,"juizoDigital":false}]
```
- **id interno do processo: 2131802** (é ele, não o CNJ, que as rotas de detalhe usam)
- **segredoJustica: false** — processo público
- Existe em **1º grau (ATOrd)** e **2º grau (ROT)** — bom caso para provar dedup

## Endpoints de binário existem no bundle (H1)
Extraídos do JS da SPA:
```
/processos/nrprocesso/     /processos/dadosbasicos/     /processos/{id}
/documentos/idUnico/       /documentos/conteudo         /documentos/
documentoPDF  documentoHTML  document o-pdf  consultarDocumento
```
`/documentos/conteudo` e `documentoPDF` são o canal de binário. **A API serve
documento, não só metadados.** H1 respondida no nível estrutural.

## A fronteira: CAPTCHA no caminho público
Abrir o processo (`/processos/{id}`) devolve `tokenDesafio` + imagem base64 de captcha.
A lista de documentos só libera depois de resolver o captcha. É controle anti-automação
deliberado, citando a Resolução 139/2014 do CSJT na própria tela.

**Consequência dura:** o caminho público NÃO é via de volume. Resolver captcha
programaticamente seria evasão de controle — proibido pela ADR 004 e pelo invariante 2.
Não fizemos e não faremos.
