# Protocolo Autorizado de Medição L4/L5

**Estado:** preparação, não executado  
**L4:** duração operacional da sessão  
**L5:** teto seguro de concorrência por sessão  
**Escopo:** preparar medições controladas, sem teste de carga e sem alterar configuração

## 1. Objetivo e fontes de verdade

Este protocolo separa duas perguntas que não podem ser confundidas:

- **L4:** por quanto tempo uma sessão emitida no handshake humano continua utilizável e
  renovável silenciosamente;
- **L5:** quantos trabalhos simultâneos uma única sessão suporta sob uma taxa conservadora,
  sem sinal de bloqueio, degradação ou atribuição anormal.

O TTL observado no baseline nacional e no TRT4 é evidência histórica do token observado,
não um teto operacional universal. A duração da sessão de dispositivo, o comportamento de
renovação e o teto de concorrência precisam de autorização e medição próprias.

`capabilities.yaml` permanece a fonte de configuração operacional. Seus defaults são piso
de segurança, não resultado de capacidade. Nenhum valor deste documento deve ser copiado
para a matriz sem a revisão prevista na seção 9.

## 2. Princípios vinculantes

- O handshake é manual e realizado pelo titular autorizado; certificado A1, chave privada,
  senha e PIN nunca entram no processo de medição.
- Usar exatamente uma credencial por rodada. Não distribuir carga, comparar identidades ou
  usar uma segunda credencial para compensar falha, limite ou expiração.
- Via nacional primeiro e somente operações previamente autorizadas. Este protocolo não
  autoriza explorar vias locais, endpoint de documento ou tribunal adicional.
- Medição de tribunal não é teste de carga: não há stress test, paralelismo agressivo,
  ramp-up aberto, repetição automática, proxy ou evasão.
- O valor medido vale somente para a combinação observada de tribunal, via, transporte,
  credencial/classe de credencial e janela de execução.
- Auditoria deve permitir reconciliar cada interação, sem conter segredo ou conteúdo
  processual.
- Resultado inconclusivo mantém os defaults conservadores e o estado não testado/parcial.

## 3. Separação entre software local e tribunal

### 3.1 Preparação local, sem rede

Antes de pedir qualquer autorização de rede, testar apenas com `Session` sintética,
relógio controlado e renovador falso:

- `SessionPool.get` compartilha uma única renovação entre consumidores concorrentes;
- cancelamento de um consumidor não cancela a renovação compartilhada;
- `renew_before` impede entregar sessão próxima da expiração;
- sessão sem `expira_em`, sem timezone válido, de tribunal divergente ou de credencial
  divergente é rejeitada;
- `put` e `invalidate` avançam a geração e uma renovação obsoleta não sobrescreve sessão
  nova nem invalidação;
- falha de renovação pausa somente a chave `(tribunal, credencial_id)` e não expõe o erro
  original;
- nenhum teste local imprime token, cookie, CPF ou outro segredo.

Essa etapa valida comportamento do software, não duração real, capacidade do tribunal,
rate limit ou validade de certificado. Seus resultados não atualizam `capabilities.yaml`.

### 3.2 Medição contra tribunal, futura e autorizada

Somente após a preparação local passar, uma rodada humana pode observar o serviço. Ela
deve manter a mesma sessão e a mesma credencial durante a medição, sem fazer volume para
“descobrir o limite”. L4 e L5 devem ser executados em rodadas separadas para que uma
observação não contamine a outra.

## 4. Pré-condições de autorização

O responsável deve registrar fora do repositório, antes da rodada:

- aprovação escrita do titular da credencial e do responsável operacional, incluindo
  tribunal, finalidade, via nacional, janela e teto conservador inicial;
- confirmação de que o uso automatizado de baixo volume é permitido e de que os processos
  consultados são públicos ou expressamente autorizados;
- identificação da única credencial autorizada, sem registrar CPF cru, token ou cookie;
- responsável observador, canal de interrupção e destino protegido para telemetria
  sanitizada;
- horário de emissão manual e relógio de referência para comparar validade;
- plano explícito de encerramento, sem retry automático nem fallback;
- autorização separada caso seja necessário renovar manualmente ou relogar.

Ausência de qualquer item impede a rodada. Sucesso prévio de TRT4, de outra credencial ou
de outra janela não é autorização nem evidência para o tribunal atual.

## 5. Telemetria sanitizada

Registrar apenas metadados necessários para reconstituir a medição:

- tribunal, via, transporte aprovado, identificador interno da rodada e classe de
  credencial, sem CPF ou identidade pessoal desnecessária;
- início/fim, duração arredondada, relógio monotônico e resultado categorizado;
- estado da sessão (`emitida`, `utilizável`, `renovação_solicitada`, `renovada`,
  `expirada`, `pausada`, `invalidada`), sem valores de token ou cookie;
- quantidade de consumidores e operações autorizadas em cada passo, latência agregada
  ou faixas, sem payload;
- status HTTP categorizado, content-type quando não sensível, tamanho e códigos de erro
  sanitizados;
- eventos de single-flight, espera, renovação, pausa, invalidação e parada;
- finalidade, autorização interna, decisão final e responsável pela revisão.

Não registrar ou versionar:

- token, JWT, cookie, header de autenticação, `storage_state` ou material de sessão;
- CPF, nome, e-mail, `sub`, `sid`, CNJ completo, URL de documento, query ou corpo;
- PDF, texto, HAR bruto, screenshot autenticado, dump de rede ou traceback com segredo;
- qualquer detalhe que permita reconstruir uma requisição autenticada.

A auditoria deve registrar a chave lógica `(tribunal, credencial_id)` de forma autorizada
e sanitizada. A telemetria não substitui o registro de auditoria da operação.

## 6. L4: duração operacional da sessão

### Perguntas

Medir separadamente:

1. validade do token/sessão de acesso emitida;
2. validade efetiva dos cookies e storage necessários ao transporte;
3. se uma renovação proativa antes da margem configurada realmente estende o acesso;
4. duração da sessão de dispositivo que permite renovar sem novo login;
5. comportamento após expiração, invalidação e falha de renovação.

Não assumir que a duração do JWT é a duração da sessão de dispositivo. Não decodificar nem
registrar claims reais na evidência; usar somente o horário de emissão e o resultado
observado pelo fluxo autorizado.

### Roteiro controlado

1. Emitir uma sessão por handshake manual e confirmar a autorização da rodada.
2. Fazer somente a operação nacional mínima autorizada e de baixo custo, em cadência
   conservadora já aprovada. Não consultar documentos nem aumentar taxa para acelerar a
   expiração.
3. Antes da margem de renovação configurada, executar uma única renovação proativa do
   fluxo aprovado e observar se a sessão continua utilizável.
4. Repetir somente os pontos de observação previstos no plano aprovado, nunca até provocar
   falha ou bloqueio. O objetivo é confirmar duração, não encontrar o limite do servidor.
5. Se a renovação silenciosa falhar, pausar a chave, auditar e notificar o titular. Nova
   emissão manual exige autorização nova.
6. Encerrar ao primeiro resultado suficiente para classificar L4, ao expirar a janela
   autorizada ou ao ocorrer qualquer critério de parada.

### Resultado L4

Classificar como `confirmado`, `parcial` ou `inconclusivo`, sempre especificando se o
resultado é sobre token, cookies/storage ou sessão de dispositivo. Uma observação isolada
de expiração, renovação ou erro não autoriza generalização.

## 7. L5: teto seguro de concorrência

### Preparação

O ponto de partida é o limite já configurado para tribunal não medido, sem tratá-lo como
capacidade comprovada. A rodada deve usar uma única sessão, uma única credencial e a menor
concorrência autorizada. Não há rampa automática nem tentativa de alcançar saturação.

### Roteiro controlado

1. Selecionar uma operação nacional mínima, pública e autorizada, sem baixar PDF ou corpo
   processual desnecessário.
2. Executar uma observação serial para estabelecer comportamento básico e telemetria.
3. Se a autorização permitir, testar incrementos pequenos e previamente enumerados de
   consumidores, mantendo a taxa total conservadora e a mesma chave lógica. Os valores
   dos incrementos são decisão operacional da rodada, não definidos neste documento.
4. Manter cada consumidor dentro da operação autorizada e observar latência, erros,
   respostas de limitação, fila de espera e integridade da sessão.
5. Encerrar antes de qualquer condição de degradação ou de limite. O maior nível observado
   sem incidente não é automaticamente o teto: aplicar margem de segurança aprovada.
6. Não testar múltiplas sessões, múltiplas credenciais ou distribuição de carga. Isso é
   outra decisão e está proibido nesta medição.

### Resultado L5

O resultado deve declarar, separadamente:

- maior concorrência observada sem sinal adverso;
- taxa conservadora efetivamente usada;
- margem aplicada, se aprovada;
- condições da sessão, via, transporte, operação e janela;
- se o resultado é `confirmado`, `parcial` ou `inconclusivo`.

Sem evidência suficiente para distinguir capacidade de acaso, classificar como
`inconclusivo` e manter o default.

## 8. Critérios de parada imediata

Encerrar a rodada, suspender novas operações e registrar apenas a categoria sanitizada
quando ocorrer qualquer um dos eventos abaixo:

- `401`: sessão recusada ou expirada;
- `403`: acesso negado, WAF ou significado não comprovado;
- `429`: limite do servidor;
- CAPTCHA, MFA inesperado, desafio adicional ou bloqueio;
- sigilo, falta de autorização ou dúvida sobre publicidade;
- timeout, 5xx repetido, redirecionamento, schema ou comportamento inesperado;
- aumento de latência, erro ou fila que indique degradação antes do nível planejado;
- qualquer sinal de que a sessão, credencial ou identidade pode ter sido exposta;
- necessidade de retry, fallback, proxy, browser automation, troca de User-Agent/IP,
  alteração de fingerprint ou outra evasão;
- encerramento da janela, do teto de taxa ou do orçamento de operações aprovado.

Parada não autoriza continuar em outra via, aumentar backoff para insistir, usar outra
credencial ou reiniciar com parâmetros mais agressivos. A retomada exige nova avaliação,
autorização e, quando aplicável, nova sessão do titular.

## 9. Atualizar ou manter `capabilities.yaml`

### Manter configuração

Manter defaults, `desconhecido`, `null` e `nao_testado`/`parcial` quando:

- a medição não foi autorizada ou não foi executada;
- houve qualquer parada antes de uma observação suficiente;
- o resultado é inconclusivo, isolado, ambíguo ou não reproduzível;
- a sessão não pôde ser separada entre TTL do token, cookies e dispositivo;
- não há margem operacional aprovada para converter observação em limite;
- a telemetria não permite reconciliar a auditoria sem segredo;
- a evidência depende de analogia com TRT4, outro tribunal ou outra credencial.

Manter o default é um resultado válido e preferível a inventar capacidade.

### Proposta de atualização futura

Somente propor atualização em tarefa posterior, nunca neste documento, se houver
cumulativamente:

- autorização humana e auditoria da rodada;
- evidência sanitizada revisada, sem token, cookie, CPF, URL de documento, corpo ou PDF;
- tribunal, via, transporte, única credencial/classe e janela identificados;
- distinção explícita entre TTL de acesso, renovação e sessão de dispositivo;
- L5 observado sem stress, sem parada e com margem conservadora aprovada;
- repetição ou evidência suficiente definida pelo responsável, sem usar sucesso isolado
  como verdade;
- justificativa do impacto sobre `jobs_concorrentes_por_sessao`, `req_por_minuto` e
  `auth.sessao_ttl_s`;
- revisão e aprovação do responsável pela matriz, com `testado_em` e referência à
  evidência sanitizada conforme o esquema existente.

Uma proposta pode atualizar somente o campo comprovado. Não preencher transporte, vias,
filtros, latências ou outros limites por consequência presumida. O valor aprovado é
específico da observação e não se propaga para outros TRTs.

## 10. Estado e bloqueios desta tarefa

- Nenhuma medição ou consulta de rede foi executada.
- Nenhum teste de carga, paralelismo agressivo ou limiter foi implementado.
- `capabilities.yaml` não foi alterado.
- Não foram coletados token, cookie, CPF, URL de documento, corpo, PDF ou HAR bruto.
- L4 e L5 permanecem abertos até autorização e medição controlada.

Bloqueios para uma rodada futura:

- aprovação do titular e do responsável operacional para a finalidade e a janela;
- definição da única credencial autorizada e do canal de handshake manual;
- operação mínima e taxa conservadora explicitamente aprovadas;
- responsável e destino protegido para telemetria sanitizada;
- critério humano de margem e de aprovação de eventual alteração da matriz;
- confirmação de que qualquer acesso institucional ou canal programático exigido foi
  resolvido antes de escalar volume.
