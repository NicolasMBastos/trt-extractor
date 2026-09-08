# Governança Conservadora de Volume

**Estado:** contrato operacional para L8. Este documento não implementa tráfego, não
altera `capabilities.yaml` e não autoriza medição nova.

## Propósito e fontes de verdade

Volume é acesso autenticado a processos públicos dentro dos limites impostos pela
plataforma. A recusa por sigilo é definitiva: não se tenta outra via, não há retry e o
job termina como `SIGILOSO`.

`capabilities.yaml` é a fonte de verdade da política operacional por tribunal: via,
transporte, estado de medição e limites. Seus `defaults` são um piso conservador de
segurança para tribunais não medidos, não uma estimativa de capacidade, SLA ou autorização
para aumentar tráfego. O rate limiter futuro deve ler a matriz em runtime; não pode embutir
limites, exceções ou valores de fallback próprios.

O banco é a fonte de verdade do trabalho durável e da auditoria. A migration define a
máquina de estados, tentativas, próxima tentativa, deadline e transições legais do job. O
limiter não reimplementa essas regras nem reabre estados terminais.

## Responsabilidades

| Responsável | Decisão ou dever |
| --- | --- |
| Titular da credencial | Realiza o handshake manual autorizado e interrompe a operação diante de questionamento, bloqueio ou sinal de uso indevido. |
| Responsável operacional | Autoriza uma rodada, confirma tribunal, credencial, finalidade e janela; decide suspender e aprova retomada. |
| Orquestrador futuro | Lê a matriz, aplica o limite por chave, agenda retry e circuit breaker, e persiste estado e auditoria no banco. |
| Adapter e transporte | Executam somente a operação autorizada; reportam resultado, status e erro sem contornar controles. Não escolhem nem elevam limites. |
| Responsável pela matriz | Altera `capabilities.yaml` apenas após evidência sanitizada, registrada e aprovada. |

## Escopo do limite

Cada decisão de tráfego é independente por **`(tribunal, credencial)`**. Uma credencial
não deve compensar limite, falha ou bloqueio de outra; tampouco se distribui carga entre
identidades para escapar de controle. `jobs_concorrentes_por_sessao` limita trabalho por
sessão, e `req_por_minuto` limita requisições para essa chave. Ambos vêm exclusivamente da
entrada `limites` do tribunal ou dos defaults herdados.

Os campos de latência, TTL e limiar de download da matriz informam agendamento e observação
quando houver evidência. Campo ausente ou `null` não permite inferência: a operação mantém a
postura conservadora e pode ser suspensa se não houver condição segura de prosseguir.

Não há limite global derivado por soma de tribunais, nem paralelismo implícito por processo,
via ou worker. Qualquer coordenação futura preserva essa chave e consulta a configuração em
vez de assumir que tribunais semelhantes se comportam igual.

## Retry, backoff e circuit breaker

Falhas classificadas como transitórias devem voltar à máquina de estados pela transição já
permitida, com `proxima_tentativa` calculada por backoff exponencial com jitter. A fórmula,
o teto e o número de tentativas são parâmetros operacionais a definir e registrar antes da
implementação; este documento não estabelece números.

O retry respeita `deadline`, não ocupa slot enquanto aguarda e nunca é aplicado a
`SIGILOSO`, `INEXISTENTE` ou outro terminal. Um erro permanente segue a transição de
dead-letter prevista na migration; a única retomada de `FALHA_PERMANENTE` é o
reenfileiramento humano já modelado no banco.

O circuit breaker é por tribunal, nunca global. Sinais repetidos de indisponibilidade,
resposta de limitação, falha de autenticação ou comportamento inesperado devem abrir o
breaker para novas operações daquele tribunal. Enquanto aberto, o orquestrador não envia
tráfego novo; registra o motivo e exige decisão operacional para a próxima tentativa. O
critério numérico de abertura e a janela de recuperação só podem ser definidos junto da
implementação, mediante evidência autorizada.

## Auditoria mínima

Cada tentativa de `authenticate`, `list`, `submit`, `poll` ou `fetch` deve criar registro em
`auditoria` com `credencial_id`, tribunal, CNJ quando aplicável, grau, tipo de documento,
via, ação, resultado, status HTTP e duração quando disponíveis. `detalhe` pode conter a
classificação sanitizada do erro e a decisão de limiter ou breaker, mas nunca token, cookie,
senha, chave privada, PIN ou conteúdo processual.

Os campos do job (`tentativas`, `proxima_tentativa`, `deadline` e `ultimo_erro`) são o
histórico operacional do item; a auditoria é o histórico de cada interação. `v_taxa_erro`
preserva a distinção entre falha e terminais legítimos, portanto `SIGILOSO` e `INEXISTENTE`
não podem ser convertidos em erro para fins de volume.

## Suspensão e retomada

Suspender imediatamente novas operações para a chave afetada quando houver bloqueio,
desafio de controle, negativa de acesso, indício de sigilo mal classificado, erro de
autenticação não explicado, manutenção anunciada ou comportamento que não corresponda à
evidência registrada. Suspender o tribunal inteiro quando o sinal não puder ser isolado à
credencial ou à sessão.

Suspensão não é motivo para contorno: são proibidos proxy, rotação de IP, rotação ou
imitação de User-Agent, troca de identidade para evitar limite, captcha bypass e teste de
estresse. A resposta é aguardar, usar apenas uma via legítima já autorizada ou escalar para
o responsável operacional.

A retomada requer registro do motivo da suspensão, confirmação de que a causa cessou ou foi
compreendida, validação da credencial pelo titular e autorização do responsável operacional.
O trabalho pendente retorna pela máquina de estados do banco, sem duplicar jobs ou blobs.

## Alteração de limites e evidência

Nenhum limite sobe por analogia, urgência ou sucesso isolado. Para mudar uma entrada em
`capabilities.yaml`, a proposta deve identificar tribunal, credencial ou classe de
credencial, via e transporte; declarar o valor atual e o pretendido; e anexar evidência
sanitizada de execução autorizada que registre período, finalidade, operações, resultados,
latência, erros, respostas de limitação e eventos de sessão.

A evidência deve demonstrar que não houve evasão de controles, que não houve acesso a
conteúdo sigiloso e que a auditoria permite reconciliar cada interação. Deve também explicar
o efeito sobre concorrência, taxa, backoff e breaker, mesmo que a conclusão seja manter o
default. O responsável pela matriz aprova e registra a medição em `testado_em`, `har` ou
evidência equivalente e `notas`; sem isso, o tribunal continua não medido e herda os
defaults conservadores.

## Separação entre teste e produção

Testes locais usam fixtures, mocks e o PostgreSQL descartável. Eles não autenticam em
tribunal, não consomem limites e não produzem evidência para elevar capacidade. Testes de
integração contra plataforma só ocorrem sob autorização explícita, escopo limitado e
observação humana; não são teste de carga.

Produção usa somente a configuração aprovada e o handshake manual do titular. Credenciais,
sessões e material de autenticação permanecem fora do repositório. A implementação futura
de limiter, fila ou coordenação não introduz Redis, serviço externo ou uma segunda fonte de
verdade para estado ou limites sem uma decisão arquitetural posterior.
