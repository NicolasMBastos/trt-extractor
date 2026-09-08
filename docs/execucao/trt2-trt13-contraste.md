# Protocolo de Contraste TRT2/TRT13

**Estado:** planejamento autorizado, não executado  
**Escopo:** contraste posterior, de baixa taxa, para um caso autorizado em cada tribunal  
**Baseline:** TRT4 e Via nacional PDPJ  
**Não altera:** `capabilities.yaml`, adapters, migrations ou código

## 1. Propósito e limites

Este documento define como uma futura rodada poderá observar TRT2 e TRT13 sem tratar a
observação como capacidade de produção. Os dois tribunais permanecem `nao_testado` até
que exista evidência sanitizada e revisão autorizada.

O contraste responde somente se o fluxo nacional já comprovado no baseline se comporta
de forma equivalente para um caso público e autorizado de cada tribunal. Não é um plano
para testar os 24 TRTs, nem autoriza inferência entre tribunais.

Regras vinculantes:

- Via nacional primeiro; uma diferença local não justifica começar por uma via local.
- Autorização e evidência sanitizada vêm antes de qualquer código ou alteração de
  configuração.
- Nenhuma hipótese deve ser escrita em `capabilities.yaml` como se fosse observação.
- Não executar rede nesta tarefa e não usar proxy, browser automation, evasão ou
  fingerprint forjada.
- Não coletar nem versionar credencial, cookie, JWT, HAR bruto, corpo, PDF real ou URL
  de documento.

## 2. Pré-condições para uma rodada futura

Antes de qualquer consulta, o responsável deve obter e registrar fora do repositório:

- autorização explícita para o tribunal, finalidade, escopo da consulta e referência de
  processo autorizada;
- confirmação de que o processo é público ou de que há habilitação expressa para o
  responsável; segredo de justiça nunca é objeto de contraste;
- titular/credencial autorizada para o login manual, sem que certificado A1, chave privada,
  senha ou PIN sejam entregues ao processo;
- responsável, data, janela de execução e destino local protegido para a ficha
  sanitizada;
- baseline nacional já encerrado para o mesmo tipo de observação, sem reutilizar segredo
  ou evidência bruta do baseline;
- limite de uma consulta inicial por tribunal, sem paralelismo, com o default conservador
  vigente até haver medição específica.

Se alguma pré-condição faltar, a rodada não começa. A autorização não pode ser deduzida
de publicidade genérica, de um CNJ fornecido por terceiros ou do fato de outro tribunal
ter funcionado.

## 3. Consulta autorizada de baixa taxa

O procedimento abaixo é um roteiro futuro, não uma execução realizada:

1. Confirmar manualmente a autorização e selecionar uma única referência de processo
   permitida. Na evidência versionável, representar o identificador somente de forma
   mascarada ou por categoria; nunca registrar CNJ completo.
2. Usar o handshake humano autorizado e a Via nacional. A sessão fica fora do repositório
   e não é copiada para a ficha.
3. Fazer uma única consulta de listagem/consulta do processo, sem baixar documentos e sem
   construir URL de documento a partir de campos inferidos.
4. Registrar apenas status, método/via, headers não sensíveis previamente permitidos,
   content-type, tamanho, nomes e tipos das chaves JSON, códigos/categorias sanitizados e
   tempos arredondados. Não registrar valores de URL, query, headers de autenticação,
   cookies, JWT, corpo, título pessoal, texto ou binário.
5. Se a listagem autorizada fornecer uma referência documental pública e a autorização
   cobrir o download, fazer no máximo uma leitura do binário original. Registrar somente
   assinatura/formato, content-type, tamanho e SHA-256 do corpo; descartar o corpo antes
   de produzir a ficha.
6. Encerrar a rodada após essa observação. Qualquer nova tentativa requer nova autorização
   explícita e justificativa, não um retry automático.

O objetivo é comparar comportamento e contrato, não medir throughput. Uma resposta não
confirmada continua não confirmada mesmo que se pareça com o TRT4.

## 4. Critérios de parada imediata

Qualquer condição abaixo encerra a rodada para o tribunal afetado:

- `401`: sessão recusada; não repetir nem renovar dentro da rodada;
- `403`: acesso negado ou ambíguo; não inferir permissão, sigilo ou capacidade e não trocar
  de via;
- `429`: limite do servidor; não aplicar backoff para continuar o contraste;
- CAPTCHA, desafio adicional, bloqueio ou resposta que sugira controle de acesso;
- sigilo explícito, ausência de autorização ou dúvida sobre publicidade;
- redirecionamento inesperado, schema não reconhecido ou resposta que exija adivinhação;
- qualquer vazamento ou presença acidental de segredo, URL de documento, CNJ completo,
  corpo, PDF ou HAR bruto;
- necessidade de browser automation, proxy, alteração de fingerprint ou outra forma de
  evasão;
- divergência que não possa ser descrita apenas por dados sanitizados.

Parada significa preservar apenas o fato sanitizado de que a rodada parou e o motivo
classificado. Não é convite a fallback, retry, consulta individual ou tentativa de
contornar a fronteira imposta pela plataforma. `SIGILOSO` é terminal conforme ADR 004.

## 5. Evidência sanitizada

A ficha versionável deve conter somente:

- tribunal (`TRT2` ou `TRT13`), ambiente classificado e data;
- identificador do protocolo e responsável, conforme política local, sem identidade
  pessoal desnecessária;
- autorização: referência interna não secreta, escopo e decisão de parada;
- referência de processo mascarada ou classe sintética, nunca CNJ completo;
- via nacional e etapa observada;
- status HTTP categorizado, content-type, tamanho, hash do corpo descartado e schema de
  chaves/tipos sem valores;
- categorias como `listagem_disponivel`, `sem_documento`, `sigiloso`, `sessao_recusada`,
  `acesso_negado`, `limite_servidor`, `captcha`, `schema_desconhecido` ou `erro`;
- comparação explícita com TRT4: `equivalente`, `diferente` ou `inconclusivo`, sempre com
  observação limitada ao que foi medido;
- decisão sobre próxima ação: encerrar, repetir somente com autorização, ou especificar
  uma investigação futura.

Não é evidência versionável: token, cookie, credencial, CPF, JWT, URL de documento,
query com identificador, corpo JSON/HTML, texto, PDF, HAR, screenshot autenticado ou
dump de rede. A ficha deve ser revisada antes de entrar no repositório.

## 6. Matriz de observações

As células começam como `não observado`. Preencher somente após a rodada autorizada;
`hipótese` não é resultado e não altera capacidade.

| Dimensão | TRT2 | TRT13 | Regra de registro |
|---|---|---|---|
| Estado atual | não observado | não observado | Permanece `nao_testado` |
| Via nacional para consulta | não observado | não observado | Uma consulta autorizada, sem inferência |
| Listagem e schema | não observado | não observado | Somente nomes/tipos de chaves |
| Documento público referenciado | não observado | não observado | Sem URL, CNJ completo ou valores pessoais |
| Leitura de binário autorizada | não observado | não observado | No máximo uma; só metadados, assinatura e hash |
| Transporte aceito | não observado | não observado | Não preencher `httpx`/`in_page_fetch` por analogia |
| Sessão/validade | não observado | não observado | Não registrar token ou cookie |
| Filtro por tipo | não observado | não observado | Registrar rótulo sanitizado, se houver |
| Sigilo/CAPTCHA | não observado | não observado | Parada, nunca fallback |
| Resposta 401/403/429 | não observado | não observado | Parada classificada |
| Desvio comprovado do baseline | não observado | não observado | Exigir evidência sanitizada |
| Decisão de adapter | não aplicável | não aplicável | Só depois dos critérios da seção 7 |

Até o preenchimento, qualquer consumidor deve usar os defaults conservadores existentes
e não tratar o documento como configuração operacional.

## 7. Criar ou recusar adapter específico

### Recusar adapter

Recusar a criação de adapter específico quando:

- a Via nacional entregar o comportamento necessário sem diferença contratual comprovada;
- a diferença for apenas de dados, classe, região, latência ou conteúdo, sem protocolo
  de transporte/semântica próprio;
- a evidência for hipótese, analogia com TRT4 ou uma única resposta ambígua;
- a única resposta for 401, 403, 429, CAPTCHA ou sigilo;
- resolver a diferença exigiria evasão, browser automation não autorizada ou acesso a
  material não sanitizado.

Nesse caso, manter TRT2/TRT13 como `nao_testado` ou `parcial` somente se a medição
sanitizada realmente justificar o estado, sem promover capacidade não medida.

### Considerar adapter

Somente abrir uma especificação de adapter quando houver, cumulativamente:

- autorização documentada para o caso e a via;
- evidência sanitizada reproduzível de uma divergência de contrato, não apenas uma
  diferença de payload;
- definição clara da operação afetada (`list_documents`, download, polling ou transporte);
- confirmação de que a Via nacional foi tentada primeiro e é insuficiente para o caso;
- nenhum requisito de copiar certificado/chave privada, usar segredo versionado, contornar
  CAPTCHA/sigilo/WAF ou alterar identidade;
- fixture sintética/contract test que reproduza a divergência sem rede e sem dados reais;
- revisão humana autorizando o custo e o escopo do adapter para aquele tribunal.

Mesmo aprovado, o adapter é específico para o comportamento comprovado. Não pode ser
generalizado para TRT2, TRT13 ou os demais TRTs sem evidência própria.

## 8. Registro de decisão

Para cada tribunal, a rodada futura deve terminar com exatamente uma decisão:

- `sem contraste`: pré-condição ausente ou rodada não autorizada;
- `parado`: condição de parada encontrada;
- `equivalente ao baseline`: nenhuma divergência contratual comprovada;
- `divergência documentada`: há diferença sanitizada, ainda sem autorização para código;
- `adapter autorizado para especificação`: todos os critérios da seção 7 foram satisfeitos.

Nenhuma dessas decisões, por si só, edita `capabilities.yaml`. A matriz de produção só
pode ser atualizada em tarefa posterior, com medição registrada, `testado_em` e revisão
correspondente ao esquema existente.

## 9. Estado desta tarefa e bloqueios

- Nenhuma consulta de rede foi executada.
- Nenhuma credencial, cookie, JWT, HAR, PDF, corpo ou URL de documento foi coletado.
- Nenhum valor foi promovido a `capabilities.yaml`.
- Nenhum adapter, fixture de produção, migration ou alteração de código foi criado.

Bloqueios para a execução futura:

- autorização humana específica para TRT2 e TRT13;
- referência pública/autorizada e mascarável para um único caso por tribunal;
- responsável e destino protegido para evidência sanitizada;
- revisão da ficha antes de versionamento;
- decisão humana posterior sobre criar ou recusar qualquer adapter.
