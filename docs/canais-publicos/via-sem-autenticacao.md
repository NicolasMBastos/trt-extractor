# Extração sem autenticação — o que dá e o que não dá

**Data:** 2026-09-08 · **Estado:** investigação documental concluída; medição ao vivo NÃO executada
**Pergunta do dono do projeto:** *dá para extrair via API sem autenticar? De todos os TRTs?
Quais são os canais oficiais, quais arquivos precisamos, e quanto % do trabalho dá para
fazer sem autenticar?*

Este documento responde no nível **documental** (normativo + especificação oficial de API).
Onde a resposta depende de bater na rede, está marcado `NÃO CONFIRMADO` e o probe está
especificado em `docs/execucao/probe-canais-publicos.md`.

---

## 1. Resposta curta

**Sem autenticar dá para fazer 100% da triagem e ~0% da petição inicial.**

O entregável do projeto é o **binário PDF de 5 classes**. A petição inicial — a classe que dá
nome ao repositório — **não existe em nenhum canal público**, em nenhum TRT, por desenho
normativo. Nenhuma engenharia resolve isso: é ausência de publicidade, não obstáculo técnico.

O que a via pública entrega de verdade é outra coisa, e é valiosa:

1. **seed e triagem completos** — quais processos existem, em que grau, com que movimentos;
2. **acórdãos** — o **FALCÃO** (`jurisprudencia.jt.jus.br`) é nacional, resolve CNJ → acórdão e
   oferece inteiro teor **sem login**. Medido. Formato do arquivo ainda não confirmado;
3. **um feed incremental diário tipado** — o DJEN, sem autenticação nenhuma, por OAB do
   escritório, com `tipoDocumento` nacional dizendo **qual classe de peça existe e quando**.

O item 3 é o achado com maior consequência arquitetural deste levantamento: ele substitui
*polling* de processo por *stream* de evento, e faz isso **fora** da credencial do advogado.
O item 2 é o único que entrega binário de peça sem autenticar.

## 2. Os cinco canais, e o que cada um é

### Canal 1 — API Pública do DataJud (CNJ) · CONFIRMADO (documentação)

```
POST https://api-publica.datajud.cnj.jus.br/api_publica_trt{N}/_search     N = 1..24
Authorization: APIKey <chave pública publicada pelo CNJ na datajud-wiki>
corpo estilo Elasticsearch, com paginação
```

- **Os 24 TRTs têm alias próprio.** Confirmado na wiki de endpoints do CNJ.
- A "autenticação" é uma **chave pública, publicada em página aberta** pelo DPJ/CNJ, rotativa
  a critério do CNJ. Não é credencial pessoal, não é certificado. **Isso a coloca inteiramente
  fora do modelo de risco da ADR 007** — nenhum acesso por aqui é atribuível ao advogado titular.
- Entrega **metadado**: capa processual + movimentos, aderente à Portaria CNJ 160/2020.
- **Entrega ZERO documento. ZERO binário. ZERO do entregável.**

**Serve para:** seed de CNJs, triagem (descartar processo sem peça-alvo antes de gastar sessão
autenticada), reconciliação. Exatamente o papel que a seção 7 do `Continua_codex` já reservava
ao DataJud — agora com endpoint e forma de acesso confirmados.

### Canal 2 — DJEN / Comunicações Processuais · PARCIALMENTE CONFIRMADO

Sucessor do DEJT desde **2024-08-01** (o DEJT saiu do ar em 2026-08-18; acervo histórico via CSJT).

```
GET https://comunicaapi.pje.jus.br/api/v1/comunicacao
GET https://comunicaapi.pje.jus.br/api/v1/comunicacao/{hash}/certidao
```

**Sem autenticação, sem cadastro, sem token.** Confirmado na especificação OpenAPI oficial
(`cnj/pcp/1.0.0`): apenas `POST` e `DELETE` declaram `security: Bearer` — são as rotas de
*inserção* usadas pelos tribunais. O `GET` de consulta e o `GET` da certidão não declaram
segurança nenhuma.

Parâmetros de consulta: `numeroOab` + `ufOab`, `nomeAdvogado`, `nomeParte`, `numeroProcesso`,
`dataDisponibilizacaoInicio`, `dataDisponibilizacaoFim`.

Cada item devolve, entre outros campos:

| Campo | Descrição na especificação oficial |
|---|---|
| `texto` | **"Teor da Comunicação"** |
| `link` | **"Link para o inteiro teor da comunicação"** |
| `tipoDocumento` | tipo do documento que gerou a comunicação |
| `tipoComunicacao` | citação ou intimação |
| `numero_processo`, `siglaTribunal`, `nomeOrgao`, `nomeClasse`, `codigoClasse` | chaveamento |
| `hash` | chave da rota `/certidao` |
| `destinatarios[]`, `destinatarioadvogados[]` | nome, polo, OAB |

### RESPONDIDO — medido ao vivo em 2026-09-08, com autorização do dono do projeto

Processo-teste público da fase 0 (TRT4, `segredoJustica=false`). Sem autenticação nenhuma.
Telemetria sanitizada; nenhum texto, nome de parte, OAB ou URL de documento registrado.

| Chamada | Resultado medido |
|---|---|
| `GET /comunicacao?numeroProcesso=...` | **200**, `application/json`, **17 comunicações**. Sem token, sem chave, sem cadastro. |
| `tipoDocumento` dos itens | `"Acórdão"` (×2), `"Notificação"` (×3), `"Distribuição"` — **tipado, e nacional** |
| `texto` | 380 a 860 chars. É o teor da **intimação**, não da peça. |
| `link` | **HTML de 4993 bytes**, `title="Processo Judicial Eletrônico"`, 8 scripts, sem form de login → é o **shell da SPA do pjekz**, não um documento |
| `GET /{hash}/certidao` | **200, `application/pdf`, 59.833 bytes, PDF válido** |

E o que há dentro daquele PDF:

| Medida | Valor |
|---|---|
| páginas | 2 |
| texto extraído | 1.873 chars |
| contém o `texto` da comunicação, literal | **sim** |
| marcadores de certidão (`certid`, `disponibiliza`, `diário`, `publica`) | **presentes** |
| marcadores de peça (`acordam`, `ementa`, `vistos`, `voto`, `dispositivo`, `isto posto`) | **ausentes** |
| razão chars_pdf / len_texto | 2,79 — moldura de certidão em volta da intimação |

**Veredito: `/certidao` é a certidão da publicação, não a peça. O `link` devolve ao PJe do
tribunal — ou seja, à trilha que a ADR 005 já mediu como barrada. O DJEN entrega ZERO binário
das 5 classes-alvo.**

**Mas ele entrega uma coisa que vale muito, e que ninguém tinha:** um **sinal de triagem
tipado, nacional, sem autenticação**. `tipoDocumento="Acórdão"` + `data_disponibilizacao`
diz, de graça, **que aquele CNJ tem um acórdão e desde quando** — antes de gastar uma única
requisição autenticada. Combinado com o DataJud, a triagem fecha 100% fora da credencial do
titular. Era exatamente o volume repetitivo que ameaçava a suspensão dela.

Ganhos confirmados do canal: seed, **sinal de existência de peça por classe**, feed
incremental diário por OAB, e um PDF de certidão com valor probatório próprio.
Não-ganho confirmado: aquisição de peça.

**Um cuidado normativo, não técnico:** o parâmetro `nomeParte` existe na API nacional, mas
buscar reclamante por nome é precisamente o que a **Resolução CSJT 139/2014** manda dificultar
na Justiça do Trabalho — a norma que fundamenta o captcha do Canal 3. Uso legítimo aqui é por
**`numeroOab` da carteira do escritório** ou por `numeroProcesso`. Busca varrendo `nomeParte`
não entra neste projeto.

### Canal 3 — Consulta processual pública do PJe · FECHADO, e continua fechado

Já medido ao vivo no TRT4 (ADR 005, `research/evidencia/trt4-consulta-api-2026-09-03.md`):
`GET /processos/{id}` devolve `tokenDesafio` + imagem de **captcha**; a lista de documentos só
abre depois de resolver.

A especificação do CSJT confirma o desenho: a Consulta Pública tem trilha pública (sem
autenticação) e trilha restrita, e **documento sigiloso ou em segredo de justiça nunca é
exibido**, exceto à própria parte logada.

**Este canal é 0% para o projeto, e é decisão, não limitação.** Resolver o captcha
programaticamente é evasão de controle — vedado pela ADR 004 e pelo invariante 2. O motivo
normativo do captcha é a Resolução CSJT 139/2014 (impedir a montagem de listas de empregados
reclamantes). Contorná-lo não é atalho técnico: é agir contra a finalidade expressa da norma.
Registrado que não fazemos, e por quê.

### Canal 4 — FALCÃO, jurisprudência NACIONAL · MEDIDO 2026-09-08, com autorização

```
https://jurisprudencia.jt.jus.br/jurisprudencia-nacional/
https://jurisprudencia.jt.jus.br/jurisprudencia-nacional-backend/api/no-auth/pesquisa
https://jurisprudencia.jt.jus.br/jurisprudencia-nacional-backend/api/no-auth/autocompletar
https://jurisprudencia.jt.jus.br/jurisprudencia-nacional-backend/api/no-auth/pesquisa/filtros
```

**FALCÃO — Sistema de busca de jurisprudência**, v2.15.3, desenvolvido pelo TRT9.
Rotas descobertas lendo as chamadas XHR da SPA no navegador real (portal do Maestri) —
mesma técnica da ADR 005, não por chute. **A API se chama literalmente `no-auth`.**

Parâmetros: `texto`, `colecao=acordaos|precedentes`, `tribunais=` (filtro multi-tribunal,
vazio = todos), `pesquisaSomenteNasEmentas`, `page`, `size`, `sessionId`.

**O que foi medido, na interface, sem login:**

| Pergunta | Resultado |
|---|---|
| CNJ → acórdão resolve? | **SIM.** Busca pelo CNJ do processo-teste → "Foram encontrados 2 resultados de Acórdãos (2,096 s)", com o processo-teste entre eles |
| Metadado por resultado | tribunal, classe (ROT), **relatoria, turma, data de juntada aos autos**, ementa completa |
| Inteiro teor disponível? | **SIM** — botões "Abrir Inteiro Teor", "Copiar Inteiro Teor", "Ler inteiro teor", além de "Copiar Ementa", "Citar" e "Buscar Similares" |
| Login exigido? | **não.** Existe "Fazer Login", mas a busca e o inteiro teor abrem sem ele |
| Nacional? | sim — `jurisprudencia-nacional`, com filtro `tribunais=` |

**E aqui o transporte se comporta ao contrário do PDPJ:**

| Cliente | Resultado medido |
|---|---|
| `httpx` puro (HTTP/2 + UA de Chrome + Referer) | **403** `{"userMessage":"Tentativa inválida de acesso ao sistema"}` |
| `fetch` de dentro da página (in-page, sessão real) | **429** `Too Many Requests` |

**Duas conclusões duras:**

1. **A ADR 002 não generaliza.** No PDPJ, `httpx` com http2+UA resolveu tudo (H2 medida
   falsa). No FALCÃO, `httpx` é rejeitado com "tentativa inválida de acesso". O transporte é
   **propriedade do canal, não do projeto** — e é por isso que `Transport` é um Protocol
   separado do Adapter. O contrato já previa exatamente isto.
2. **O canal tem limitador ativo.** O `fetch` in-page recebeu **429 depois de meia dúzia de
   chamadas**. Conforme o critério de parada (ADR 004, protocolo L4/L5 §8), **paramos ali**:
   sem retry, sem backoff para insistir, sem trocar sessão, sem rodar de novo. Fica registrado
   como limite conhecido, não como obstáculo a vencer.

**Isto não foi medido e continua aberto:** se o "Inteiro teor" serve **PDF** ou HTML; a
cobertura real por tribunal e por período; o teto de taxa do `no-auth`; e se o `sessionId`
tem validade própria. Fechar isso exige nova rodada autorizada, em ritmo conservador.

### Canal 4b — Jurisprudência por tribunal · matriz em `matriz-24-trts.md`

Cada TRT mantém sistema público de consulta de acórdãos, **sem login**, com inteiro teor em
PDF (confirmado em TRT1, TRT3, TRT9 entre outros; matriz completa dos 24 em
`docs/canais-publicos/matriz-trt01-12.md` e `matriz-trt13-24.md`).

**É a única via pública que entrega binário de peça de verdade.** Limites honestos:

- cobre **acórdão** (2º grau). Não cobre petição inicial, acordo nem laudo.
- **sentença de 1º grau raramente entra** em base de jurisprudência.
- a chave de busca é ementa/assunto/período, **não necessariamente CNJ arbitrário** — a
  resolução CNJ→acórdão por este canal precisa ser confirmada por tribunal.
- são **24 sistemas diferentes**, sem padrão nacional. É exatamente o problema de "24
  integrações" que a ADR 001 evitou ao escolher a via nacional autenticada. Aqui ele volta.

### Canal 5 — Codex (CNJ) · o canal institucional certo, e o mais promissor

O **Codex** é a base nacional do CNJ que consolida, nas palavras do próprio CNJ, *"tanto os
dados estruturados, também chamados de metadados dos processos, como os dados não estruturados
(**conteúdo de peças e de documentos**)"*.

É o único canal que combina escala nacional com conteúdo de peça. Não é aberto: é regulado.

**Resolução CNJ 574/2024** (altera a Res. 121/2010) define o caminho:

| Artigo | O que impõe |
|---|---|
| art. 1º | o CNJ **poderá** oferecer acesso a dados judiciais públicos por instrumento próprio |
| art. 1º §1º | a Presidência regulamenta as condições de acesso ao **data lake via API** |
| art. 1º §2º | o **DTI avalia a capacidade técnica do consumidor** (infra, uptime, gestão de identidades) |
| art. 2º | cabe aos tribunais atribuir corretamente segredo/sigilo ao que mandam **para o Codex** |
| art. 3º | CNJ/CJF/**CSJT** e tribunais podem **limitar ou bloquear** acesso por "comportamento inautêntico ou consumo abusivo" |
| art. 4º | **cobrança** limitada ao custo efetivo, exigível de quem consome |
| art. 4º §2º | ensino e pesquisa **podem ser dispensados** do custeio |
| art. 4º §3º | o CNJ pode condicionar o acesso a devolver o produto desenvolvido, sem ônus, na PDPJ-Br |

**Resolução CNJ 647/2025** trata do compartilhamento de dados pessoais sob custódia do CNJ:
entidade privada (art. 2º, IV) acessa **somente por convênio, contrato ou instrumento
congênere** (art. 19), com finalidade declarada, e com repasse possível de custos (art. 12, III).

Um escritório de advocacia é entidade privada. Portanto o caminho para o Codex é
**convênio/contrato + finalidade declarada + avaliação técnica pelo DTI + custeio** — não é
cadastro nem chave pública. É lento e é institucional. É também exatamente o "canal
institucional" que a seção 6, item 7 do `Continua_codex` já apontava como o caminho certo para
volume, em vez de espremer a credencial de uma pessoa.

### Canal 6 (para constar) — MNI por convênio

Já sondado: `scripts/probe_mni.py` achou que **o TRT4 exige convênio**. Segue como fallback por
tribunal, com o custo que a ADR 001 já descartou (24 negociações).

## 3. Quanto % dá para fazer sem autenticar

Por classe de documento, que é a única medida honesta — o entregável é o binário:

| Classe | Sem autenticar | Por qual canal | Estado |
|---|---|---|---|
| **Petição inicial** | **0%** | nenhum | **confirmado** — não é publicada em diário, não entra em jurisprudência, e a consulta pública é barrada por captcha |
| **Acórdão** | **alto** | Canal 4 (FALCÃO, nacional) | **medido**: CNJ resolve, inteiro teor disponível sem login. Falta confirmar formato (PDF?) e cobertura |
| **Sentença** | **~0%** | — | **medido e fechado**: o DJEN entrega certidão, não a peça; 1º grau não entra em jurisprudência |
| **Acordo** | **~0%** | nenhum | confirmado por desenho — o termo é peça dos autos; só a homologação é publicada |
| **Laudo / perícia** | **0%** | nenhum | confirmado por desenho |

**Resultado das medições de 2026-09-08:** a via pública entrega **1 das 5 classes (acórdão)**
e **o sinal de existência das demais**. A linha "sentença", que era a maior incerteza, fechou
para baixo — o DJEN não serve peça.

Por etapa do pipeline (seção 7 do `Continua_codex`):

| Etapa | Sem autenticar | Canal |
|---|---|---|
| `[seed]` CNJs | **100%** | 1 e 2 |
| `[triagem]` descartar processo sem peça-alvo | **100%** | 1 |
| `[sessão]` | não se aplica — **é o ganho**: nenhuma sessão gasta na triagem | — |
| `[submit]` / `[fetch]` binário das 5 classes | **1 de 5 classes, com ressalva** | 4 |
| `[classify]` camada de texto | **parcial** — `texto` do DJEN é conteúdo real | 2 |
| `[incremental]` (fase 6) | **100%**, e melhor que o plano autenticado | 2 |

**Portanto:** a via sem autenticação **não substitui** a via autenticada da ADR 001. Ela
**protege** a via autenticada — tira dela todo o trabalho de descoberta, triagem e
acompanhamento, que era justamente o volume repetitivo que ameaçava a credencial do titular.
O acesso autenticado passa a ser gasto só onde é insubstituível: buscar a peça.

Esse é o ganho real, e ele é grande em risco, não em percentual de arquivos.

## 4. Arquivos e insumos que precisamos

| Insumo | Onde vive | Estado |
|---|---|---|
| Chave pública do DataJud | `.env` (nunca no repo, mesmo sendo pública — o repo não guarda credencial, sem exceção de categoria) | disponível na wiki do CNJ |
| Nada para o DJEN | — | canal aberto, sem credencial |
| Lista de OAB do escritório | `.env` / config | **pedir ao escritório** |
| CNJs semente | DataJud, CSV do cliente, carteira própria | já previsto |
| Convênio Codex | processo institucional com o CNJ | **não iniciado** |
| Aprovação titular + compliance | fora do repo | **pendente (ADR 007, L8)** |

## 5. O que medir para fechar (nada disto foi executado)

Ordenado por quanto muda a resposta. Os dois primeiros da lista anterior **já foram medidos**
em 2026-09-08 e estão respondidos acima.

1. **O "Inteiro teor" do FALCÃO é PDF?** Um clique, num acórdão, no navegador real. Se for PDF,
   acórdão fecha ponta a ponta sem autenticar. **Maior alavanca agora.**
2. **Cobertura do FALCÃO:** quais dos 24 tribunais, e desde quando. Filtro `tribunais=` responde,
   em ritmo conservador — o canal já mostrou limitador (429).
3. **Teto de taxa do `no-auth`.** Já sabemos que existe. Precisa de valor operacional seguro,
   pelo protocolo L4/L5, **não** por tentativa e erro.
4. **DJEN por `numeroOab` da carteira** entrega histórico ou só janela recente? Decide backfill
   vs. só incremental.
5. **DataJud: os 24 aliases respondem à busca por CNJ?** Fecha o seed nacional.
6. **Codex: qual o instrumento concreto** para um escritório, e o custo. Pergunta institucional,
   não técnica — vai por ofício, não por requisição.

Protocolo sanitizado: `docs/execucao/probe-canais-publicos.md` (a escrever).

## 6. O que este levantamento NÃO provou

**Foi medido ao vivo, com autorização, em 2026-09-08:** o DJEN (listagem, `link`, `/certidao`,
mais a extração de texto do PDF da certidão) e o FALCÃO (busca por CNJ na interface, descoberta
das rotas `no-auth`, `httpx` puro, `fetch` in-page). Nada além disso.

**Não foi medido, e não deve ser tratado como sabido:**

- **Formato do "Inteiro teor" do FALCÃO.** PDF ou HTML — não sabemos. É a próxima medição.
- **Cobertura do FALCÃO** por tribunal e por período. Nenhuma generalização a partir do TRT4.
- **Teto de taxa do `no-auth`.** Sabemos que existe (429 após poucas chamadas). O valor seguro
  não foi determinado, e não vai ser por tentativa e erro.
- **Captcha nos outros 23 TRTs.** Medido só no TRT4 (ADR 005). Nos demais é inferência
  estrutural (mesmo artefato servido), declarada como inferência.
- **DataJud.** Nenhuma requisição feita. Só documentação.
- **Codex.** Nenhum contato institucional iniciado.
- **Nenhum binário foi baixado e nada foi arquivado.** O único PDF buscado foi a certidão do
  DJEN, para medir seu conteúdo, e ele não foi versionado.
- `capabilities.yaml` não foi alterado. Nada daqui foi promovido a configuração de produção.
