# TRT4 — sessão autenticada, medida ao vivo (2026-09-03)

Login por certificado (PJeOffice → "Entrar com PDPJ" → SSO Keycloak) feito pelo
titular. Perfil retornado: **Advogado** (habilitado no PJe do TRT4). Medições sem
gravar dado pessoal.

## Arquitetura de auth do PJe TRT4 (pjekz)

Não é o mesmo shape do portaldeservicos nacional. O PJe do TRT4 tem API REST própria:

| Serviço | Papel |
|---|---|
| `pje-seguranca/api/token/perfis` | perfis/papéis do usuário logado |
| `pje-seguranca/api/token/permissoes/recursos` | permissões |
| `pje-comum-api/api/...` | processos, quadro de avisos, perícias, parâmetros |
| `pje-consulta-api/api/...` | consulta PÚBLICA — mantém captcha mesmo logado |

Cookies de sessão em `pje.trt4.jus.br`: **`access_token`** (JWT, legível por JS —
NÃO httpOnly), `Xsrf-Token`, `ASSINADOR_PJE`, `MO`.

## Validade da sessão — Q3b RESPONDIDA

```
JWT access_token:
  iss:  https://pje.trt4.jus.br/pje-seguranca/
  iat → exp:  exatamente 60 minutos
  refresh no token: NÃO (tem_refresh=false)
```

**A sessão dura 1 hora.** Sem refresh embutido no access_token — a renovação passa
pelo Keycloak (o SSO mantém sessão de dispositivo; ver MFA por dispositivo). Isso
define o ciclo de renovação do pool de sessão.

## H1 no caminho autenticado — resultado com nuance

O endpoint autenticado de processo existe e responde, mas a permissão é por
habilitação nos autos:

```
GET /pje-comum-api/api/processos?numeroProcesso=00208903920245040015
→ 500 ARQ-516 "Erro de permissão ao acessar o recurso"
```

O titular NÃO está habilitado no processo-teste (não tem vínculo — confirmado desde o
início). Logo, a via `pje-comum-api` (autos completos) exige habilitação, como esperado
para autos de 1º grau.

**Isso reforça a ADR 004 e a estratégia de vias:**
- Autos completos autenticados (`pje-comum-api`) → só onde o titular é parte/habilitado.
- Documento de processo público onde não há habilitação → volta para a via pública
  (`pje-consulta-api`), que tem captcha e portanto NÃO é via de volume.
- A via nacional `portaldeservicos.pdpj.jus.br/api/v2` (Via 0) ainda não foi testada
  autenticada — precisa de login naquele domínio, não neste. É o próximo teste de H1.

## Consequência para o escopo

Para processos SEM habilitação do titular, as vias autenticadas de autos completos
retornam permissão negada — e a única via pública tem captcha. Isso torna a pergunta
de escopo (quais processos, com qual vínculo) decisiva, não secundária. Ver seção de
pendências em docs/fase-0/capacidade.md.
