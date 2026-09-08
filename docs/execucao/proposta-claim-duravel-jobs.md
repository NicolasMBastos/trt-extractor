# Proposta separada: claim duravel para `job`

Estado: NAO APLICADA. Requer decisao arquitetural e nova migration; a migration
`001_inicial.sql` permanece congelada.

## Incompatibilidade observada

A migration possui indice de fila e permite `SELECT ... FOR UPDATE SKIP LOCKED`,
mas a tabela `job` nao possui `claim_id`, `claimed_at`, `claim_expira_em` ou
estado de execucao. O lock de linha desaparece ao encerrar a transacao. Portanto,
o padrao abaixo e inseguro:

1. transacao seleciona uma linha com `SKIP LOCKED`;
2. transacao faz commit;
3. worker chama o tribunal fora da transacao.

Outro worker pode selecionar a mesma linha entre os passos 2 e 3. Manter a
transacao aberta durante uma chamada externa tambem e inadequado: prende conexoes,
nao sobrevive a queda do processo e nao fornece retomada auditavel.

## Patch minimo proposto

Criar uma migration posterior que acrescente apenas:

- `job.claim_id uuid NULL`;
- `job.claimed_at timestamptz NULL`;
- `job.claim_expira_em timestamptz NULL`;
- referencia de auditoria a `job_id` e `claim_id`, para relacionar claim, renovacao,
  vencimento e retomada ao trabalho afetado;
- indice parcial para jobs prontos sem claim valida ou com claim vencida.

O claim atomico atualizaria esses tres campos dentro da mesma instrucao/tx que
usa `FOR UPDATE SKIP LOCKED`; o worker receberia a linha e o `claim_id`. Cada
transicao posterior exigiria `WHERE id = :id AND claim_id = :claim_id`, para que
um worker morto ou atrasado nao grave sobre uma retomada mais nova.

Ao reiniciar, somente claims vencidas voltariam a ser candidatas. A retomada deve
ser auditada. Nao se cria estado terminal novo, nao se altera a tabela de
transicoes e nao se reabre `ARQUIVADO`, `SIGILOSO` ou `INEXISTENTE`.

## Efeito externo e reenfileiramento humano

Lease sozinho nao resolve queda entre uma operacao externa e a persistencia do
resultado. Por exemplo, o tribunal pode aceitar `request_download`, o processo
pode morrer antes de gravar `id_pedido` e uma retomada pode submeter de novo. A
especificacao posterior deve escolher uma estrategia comprovada de reconciliacao:
chave de idempotencia aceita pelo tribunal, consulta por handle previamente
persistido, ou estado de submissao auditavel que bloqueie reenvio ate revisao.
Nao e permitido assumir que o endpoint e idempotente sem evidencia.

Tambem ha uma divergencia entre comentario e enforcement atual: a migration diz
que `FALHA_PERMANENTE -> PENDENTE` e somente humano, mas o trigger aceita a
transicao sem registrar identidade, motivo ou aprovacao. A migration posterior
deve exigir campos/auditoria de reenfileiramento humano e fazer o repository
recusar a operacao automatica. Enquanto isso, nenhum worker pode executar essa
transicao.

## Decisoes necessarias

1. Duraçao do lease e regra de renovacao, configuraveis e sem numero magico.
2. Se uma chamada ao tribunal pode ocorrer somente apos claim persistido.
3. Campos minimos de auditoria para claim, renovacao, vencimento e retomada.
4. Politica para trabalho que excede o lease, sem aumentar concorrencia ou
   reenviar submissao de forma cega.
5. Estrategia de reconciliacao apos efeito externo antes de persistir `id_pedido`.
6. Identidade, motivo e autorizacao exigidos para `FALHA_PERMANENTE -> PENDENTE`.

## Criterio para implementar repository e restart

Somente apos a migration aprovada e aplicada em PostgreSQL descartavel:

- dois consumidores concorrentes obtêm jobs diferentes;
- um worker morto deixa claim expirar e outro retoma sem duplicar artefato;
- uma transicao com `claim_id` obsoleto nao altera a linha;
- queda apos submit nao causa segundo submit sem reconciliacao comprovada;
- reenfileiramento de dead-letter exige identidade humana, motivo e auditoria;
- terminal legitimo nunca retorna para a fila;
- `SIGILOSO` fica terminal e auditado, nao como erro;
- os testes usam somente PostgreSQL local, fixtures e mocks, sem tribunal.
