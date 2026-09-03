# 003 — Certificados são A1; o gargalo é a credencial, não o certificado

**Data:** 2026-09-03 · **Estado:** aceita (fato medido)

## Contexto

O briefing (seção 2.3) manda descobrir A1 vs A3 antes de dimensionar qualquer coisa,
porque a resposta muda o teto de throughput:

- **A3** (token/smartcard): sessão PKCS#11, assinatura serializada, hardware físico.
  Paralelizar workers não aumenta throughput. O teto é a taxa de emissão de sessão.
- **A1** (arquivo `.pfx`/`.p12`): sessões emitidas em paralelo.

## Medição

Repositório de certificados do Windows (`Cert:\CurrentUser\My`):

| Titular | AC | Expira | Situação | Provider |
|---|---|---|---|---|
| LARISSA A. R. F. DE ALMEIDA | Certisign RFB G5 | 2025-04-01 | expirado | MS Enhanced Crypto Provider v1.0 |
| CLARISSE DE SOUZA ROZALES | Safeweb RFB v5 | 2025-08-08 | expirado | MS Strong Crypto Provider |
| RENATA PEREIRA ZANARDI | Safeweb RFB v5 | 2026-07-04 | expirado | MS Enhanced Crypto Provider v1.0 |
| RENATA PEREIRA ZANARDI | Certisign RFB G5 | **2027-05-27** | **válido** | MS Enhanced Crypto Provider v1.0 |

**Todos A1.** Os providers são CSPs de **software** — um token A3 apresentaria CSP do
fabricante (SafeSign, Watchdata, eToken, Gemalto). Todos com chave exportável.

Confirmação independente, do próprio PJeOffice Pro
(`~/.pjeoffice-pro/pjeoffice-pro.config`, salvo em 2026-09-01):

```
list.a3=                      ← vazio: nenhum A3 configurado
default.repository=MSCAPI     ← store do Windows
auth.strategy=ONE_TIME
list.server=PJe;https://sso.cloud.pje.jus.br/auth/realms/pje;<blob>;true
```

## Decisão

1. **Dimensionar assumindo A1.** Emissão de sessão é paralelizável e sai do caminho
   crítico de throughput. Não construir fila de assinatura serializada nem sessão
   PKCS#11 — seria resolver um problema que não existe.
2. **Tratar a credencial como recurso escasso e rastreado.** A tabela `credencial`
   existe no esquema, e `job.credencial_id` e `auditoria.credencial_id` registram qual
   identidade originou cada requisição.
3. **Alertar sobre expiração.** `credencial.certificado_expira_em` é monitorada. O único
   certificado válido vence **2027-05-27**, dentro do horizonte do projeto: expiração
   silenciosa é modo de falha real, não hipotético. Três dos quatro já venceram — o
   padrão de falha já se manifestou.
4. **Nunca armazenar material criptográfico.** `Credencial` guarda thumbprint e validade;
   a chave fica no repositório do SO. `Credencial.__repr__` e `Session.__repr__` são
   sobrescritos para não vazar CPF nem token em log ou traceback. `cpf_hash` no banco,
   nunca o CPF cru.

## Consequência que contraria o briefing

A seção 4 do briefing manda: *"se houver múltiplas credenciais/certificados, distribua a
carga entre elas e escalone os horários"*.

**Não há entre o quê distribuir.** Há uma credencial utilizável. Com volume-alvo de
10⁴–10⁵ processos numa única e-CPF de pessoa física, o rate limit por
`(tribunal, credencial)` deixa de ser higiene operacional e passa a ser **o dimensionador
principal do cronograma**.

O gargalo mudou de lugar: não é mais o certificado (A1 resolveu), não é ainda o tribunal
(a medir na fase 0) — é a identidade única.

Isso virou as perguntas P1 (legitimidade do vínculo) e P2 (haverá mais certificados?) em
`docs/fase-0/plano.md` §6. P1 é bloqueante para a fase 1.

## Alternativas descartadas

- **Exportar o `.pfx` e usar `client_certificates` do Playwright para mTLS
  desassistido.** Tecnicamente viável (as chaves são exportáveis) e registrado como
  possibilidade — mas **descartado por ora**: tira o material criptográfico do
  repositório do SO e o coloca no caminho do processo, o que piora a postura de
  segurança sem ganho comprovado enquanto o MFA por dispositivo já mantém a sessão viva.
  Reavaliar só se a emissão de sessão virar gargalo medido.
- **Assumir A3 por segurança.** Descartado: mediu-se, não é. Dimensionar para um gargalo
  inexistente custaria complexidade real.
