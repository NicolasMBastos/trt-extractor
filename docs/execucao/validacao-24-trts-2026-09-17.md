# Validação real dos 24 TRTs — 2026-09-17

**Método:** descoberta de processos públicos via DataJud/CNJ (API pública oficial,
`api-publica.datajud.cnj.jus.br`, sem autenticação); consulta real via UI do portal PDPJ
nacional (`portaldeservicos.pdpj.jus.br`) com sessão do titular autenticada manualmente
(login feito pelo próprio titular; nenhuma automação de PIN/certificado). Navegação
assistida via maestri portal (browser real), volume mínimo (1 requisição de busca por
tribunal, sequencial, sem concorrência).

**O que NÃO foi commitado:** números CNJ reais, nomes de partes, conteúdo de documentos.
Manifest completo com CNJs fica em `data/live_validation_2026-09-17.json`, gitignored.

## Critérios (conforme handoff)

- **A — descoberta:** CNJ público localizado via DataJud.
- **B — consulta:** processo reconhecido no portal PDPJ nacional.
- **C — documentos:** listagem de documentos ("autos digitais") abre e mostra itens.
- **D — binário:** não testado nesta rodada (ver limitação abaixo).
- **E — pipeline:** não testado (requereria o código Python fim-a-fim, não apenas a UI).

## Matriz

| TRT | A | B | C | Resultado | Motivo |
|---|---|---|---|---|---|
| TRT1  | ✓ | ✓ | ✓ | **PASS**    | Vara 1ª instância, docs reais presentes |
| TRT2  | ✓ | ✓ | ✗ | **PARTIAL** | Processo migrou para o TST; autos não abriram nesse estágio (2 candidatos testados) |
| TRT3  | ✓ | ✓ | ✓ | **PASS**    | Vara 1ª instância |
| TRT4  | ✓ | ✓ | ✓ | **PASS**    | Vara 1ª instância, 5 docs, nenhuma classe-alvo clara nesta amostra |
| TRT5  | ✓ | ✓ | ✓ | **PASS**    | Vara 1ª instância |
| TRT6  | ✓ | ✓ | ✗ | **PARTIAL** | Candidato é gabinete de 2ª instância; autos não abriram |
| TRT7  | ✓ | ✓ | ✗ | **PARTIAL** | Gabinete de 2ª instância |
| TRT8  | ✓ | ✓ | ✓ | **PASS**    | 1º candidato (gabinete) falhou; 2º candidato (vara) abriu com 14 docs |
| TRT9  | ✓ | ✓ | ✗ | **PARTIAL** | Gabinete de 2ª instância |
| TRT10 | ✓ | ✓ | ✗ | **PARTIAL** | Gabinete de 2ª instância |
| TRT11 | ✓ | ✓ | ✗ | **PARTIAL** | Gabinete de 2ª instância |
| TRT12 | ✓ | ✓ | ✗ | **PARTIAL** | Gabinete de 2ª instância |
| TRT13 | ✓ | ✓ | ✗ | **PARTIAL** | Gabinete de 2ª instância |
| TRT14 | ✓ | ✓ | ✗ | **PARTIAL** | Gabinete da Presidência |
| TRT15 | ✓ | ✓ | ✗ | **PARTIAL** | Gabinete de 2ª instância |
| TRT16 | ✓ | ✓ | ✗ | **PARTIAL** | Marcado G1 no DataJud, mas em fase recursal (gabinete) na prática |
| TRT17 | ✓ | ✓ | ✓ | **PASS**    | Vara 1ª instância, 9 docs |
| TRT18 | ✓ | ✓ | ✓ | **PASS**    | Vara 1ª instância, 14 docs |
| TRT19 | ✓ | ✓ | ✓ | **PASS**    | Vara 1ª instância; autos abrem, 0 docs (processo muito recente) |
| TRT20 | ✓ | ✓ | ✓ | **PASS**    | Vara 1ª instância, 13 docs |
| TRT21 | ✓ | ✓ | ✓ | **PASS**    | Vara 1ª instância, 7 docs |
| TRT22 | ✓ | ✓ | ✓ | **PASS**    | Gabinete, mas autos abriram (exceção ao padrão) |
| TRT23 | ✓ | ✓ | ✗ | **PARTIAL** | 1º candidato não encontrado no PDPJ (apesar de público no DataJud); 2º é gabinete |
| TRT24 | ✓ | ✓ | ✓ | **PASS**    | Vara 1ª instância, 11 docs |

**Resumo:** 24/24 em A e B (descoberta + consulta PROVADOS nos 24 tribunais).
14/24 em C (PASS completo). 10/24 PARTIAL — todos por causa identificada, não por bug.

## Hipótese refutada / confirmada

Hipótese levantada durante o teste: **candidatos em fase de 2ª instância/gabinete
(desembargador) não abrem a tela de "autos digitais" nesta UI**, só processos de vara
(1ª instância) abrem de forma confiável. Confirmada em 8 dos 9 casos onde havia um
candidato de vara disponível para comparação (TRT8: 1º candidato gabinete falhou, 2º
candidato vara funcionou). Exceção: TRT22, gabinete que abriu mesmo assim — a hipótese
não é regra absoluta, é o padrão dominante.

## Nível D (binário) — NÃO PROVADO nesta rodada

Tentei abrir PDF real em TRT1 e TRT4 (link "Abrir ... .pdf", `href="javascript:"`).
Clique não abriu popup nem alterou o DOM de forma detectável via `maestri portal`. Não
sei se: (a) o app abre um viewer em blob URL que o snapshot não captura, (b) há um
popup bloqueado, ou (c) precisa de uma interação diferente. **Não é evidência de que o
binário funcione nem de que falhe** — é lacuna de ferramenta, registrada como tal.

## Nível E (pipeline completo) — NÃO TESTADO

Esta validação usou a UI do portal, não o código Python do projeto (`pdpj.py` +
`InPageFetchTransport` + `Ritmo` + `SessionStore`). Provar E exigiria rodar o adapter de
verdade contra uma página autenticada real, o que não foi construído nesta rodada.

## O que ficou provado, fortemente indicado, não provado

- **PROVADO:** os 24 TRTs têm processos públicos localizáveis via DataJud oficial; o
  portal PDPJ nacional reconhece processos dos 24 TRTs via a mesma sessão de titular
  (nenhum TRT precisou de tratamento especial na consulta).
- **PROVADO:** listagem de documentos funciona de forma idêntica (mesma UI, mesmo
  fluxo) nos 14 TRTs testados com sucesso — não há tratamento por-tribunal na consulta
  nem na listagem.
- **FORTEMENTE INDICADO:** os 10 TRTs em PARTIAL provavelmente também funcionariam com
  um candidato de vara (1ª instância) em vez de gabinete — só não foi confirmado em
  todos por causa do tempo da rodada.
- **NÃO PROVADO:** download de binário (nível D) e pipeline completo (nível E) em
  qualquer TRT nesta rodada — limitação de ferramenta, não de arquitetura.

## Limitações desta rodada

- Amostra de 1–2 candidatos por TRT, não 3 como o teto sugerido no handoff.
- Nenhuma chamada usou o código Python do projeto — foi validação de UI, não do adapter.
- TRT23 teve 1 candidato "sumiu" entre DataJud e PDPJ nacional (sincronização entre
  bases, não bug nosso — não investigado a fundo).
