# 010 — Ritmo inicial de produção (decisão operacional)

**Data:** 2026-09-17 · **Estado:** **aceita**, autorizada pelo dono do projeto na
mesma sessão em que a evidência foi apresentada.

**Não altera `capabilities.yaml`.** Os 24 tribunais continuam com
`req_por_minuto: 6` (piso conservador, não medido individualmente por tribunal).
Esta decisão é sobre **disciplina operacional agregada**, uma camada acima do que
`Ritmo`/`capabilities.yaml` já impõem por `(tribunal, credencial)`.

## Contexto e evidência (conforme exigido por `governanca-volume.md` §"Alteração de
limites e evidência")

- **Tribunal/credencial:** todos os 24 TRTs, uma única credencial (titular, ADR
  003/004/007).
- **Via/transporte:** `PDPJ_API` nacional, `InPageFetchTransport` (ADR 009).
- **Período de execução:** 2026-09-17, rodada única de validação.
- **Finalidade:** provar nível D/E (binário + pipeline completo) e mapear
  classificação de tipo de documento nos 24 TRTs.
- **Operações realizadas:** `list_documents` + `request_download` → `poll_download`
  → `fetch_artifact` (1 documento por processo) em 24 processos reais, sequencial,
  pausa de 15s entre qualquer duas chamadas HTTP (acima do piso de 10s = 6 req/min
  da matriz).
- **Resultados:** 22/24 sucesso completo (PDF real, sha256 conferido no CAS
  local); 1 grau inexistente (candidato de gabinete, esperado); 1 falha real
  (envelope de erro upstream do TRT1, já corrigido — ver commit
  `fix(pdpj): reconhece envelope de erro upstream com HTTP 200`).
- **Latência medida:** `list_documents` média 0,16s; `fetch_artifact` média 0,43s.
- **Respostas de limitação:** nenhuma. Zero `403`/`429` em 24 tribunais, ~50
  requisições totais na rodada completa (descoberta + validação + pipeline).
- **Eventos de sessão:** 1 handshake manual (login do titular), 1 captura de
  Bearer via hook (ver ADR de referência abaixo), sessão reaproveitada em todos os
  24 tribunais sem re-autenticação.
- **Evasão de controles:** nenhuma. Sem paralelismo, sem rotação de identidade,
  sem alteração de fingerprint. Registrado em
  `docs/execucao/validacao-24-trts-2026-09-17.md`.

Esta evidência prova que o mecanismo funciona e não gerou nenhum sinal de bloqueio
— **não prova que um volume sustentado (horas, dias) seja seguro**. É teste único,
curto, não é teste de carga (`governanca-volume.md` §"Separação entre teste e
produção").

## Decisão

**Início de produção no ritmo de 20-30 processos por hora**, agregado — ou seja,
independente de quantos tribunais distintos a credencial toca na mesma hora,
soma-se o total.

1. **Não é um limite por tribunal.** `capabilities.yaml` continua valendo por
   `(tribunal, credencial)` como já é, sem mudança. Este número é um teto adicional
   que o **orquestrador/operador** aplica na hora de decidir quantos processos
   agendar por hora, cruzando tribunais.
2. **Não é o teto técnico.** A matriz permitiria, somando os 24 tribunais a 6
   req/min cada, uma ordem de grandeza muito maior. Escolhido deliberadamente
   abaixo do que a plataforma tecnicamente tolera, porque o risco (ADR 009) é
   auditoria de uso da credencial, não detecção — esse risco não confunde com "1
   tribunal" nem "24 tribunais", é a mesma pessoa, o mesmo certificado, o mesmo
   dia.
3. **2 requisições por processo** (list + 1 fetch) é a unidade de referência. Buscar
   mais de 1 documento por processo consome a cota proporcionalmente — o teto é de
   processos, não de documentos.
4. **Horário comercial, dias úteis** (já imposto por `JanelaOperacional`,
   `capabilities.yaml`).

## O que este número NÃO autoriza

- Não autoriza subir `req_por_minuto` de nenhum tribunal em `capabilities.yaml`.
- Não autoriza concorrência entre tribunais nem entre processos.
- Não autoriza operar fora da janela comercial.
- Não é permanente: é o ponto de partida. Subir exige nova evidência — volume
  sustentado observado, taxa de erro, resposta da plataforma — não repetição do
  teste desta rodada nem urgência de prazo (`governanca-volume.md`: "Nenhum limite
  sobe por analogia, urgência ou sucesso isolado").

## Responsabilidades (herdadas de `governanca-volume.md`)

| Responsável | Decisão ou dever nesta rodada |
| --- | --- |
| Titular da credencial | Autorizou o handshake que gerou a evidência; interrompe a operação diante de qualquer bloqueio ou questionamento. |
| Responsável operacional (dono do projeto) | Autorizou esta decisão em 2026-09-17, com a evidência acima. |
| Implementação futura do orquestrador | Deve aplicar o teto agregado de 20-30 processos/hora como parâmetro de agendamento, lendo de configuração — não hardcoded neste ADR nem no `capabilities.yaml` (que não modela agregado). |

## Retomada e revisão

Revisar esta decisão após observação real em produção (dias, não uma sessão),
com: taxa de erro, qualquer resposta de limitação, qualquer contato do tribunal
ou da CNJ, e volume total processado. Só então considerar subir o teto — com
evidência nova, registrada da mesma forma que esta.

## Referências

- `docs/execucao/validacao-24-trts-2026-09-17.md` — evidência completa da rodada.
- `docs/decisions/009-transporte-in-page-e-ritmo.md` — por que ritmo é o controle
  principal.
- `docs/execucao/governanca-volume.md` — contrato operacional que esta decisão
  cumpre.
