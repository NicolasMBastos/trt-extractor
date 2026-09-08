# 007 — Modelo de segurança: o que uma requisição expõe do certificado e da conta

**Data:** 2026-09-03 · **Estado:** aceita (medido) + decisão de governança pendente

Escrito para responder, com evidência, a pergunta: fazer requisições autenticadas em
volume põe em risco o certificado, ou expõe a conta do advogado do setor de tecnologia?

Medido ao vivo, decodificando o próprio JWT da sessão. Nenhum dado pessoal gravado aqui.

## 1. O certificado NÃO viaja na requisição

O certificado (chave privada A1) é usado **uma única vez**, **localmente**, pelo
PJeOffice, para assinar o desafio de login do SSO. Só a **assinatura** cruza a rede — a
chave privada nunca. Depois do login, toda requisição carrega um **Bearer JWT**; o
certificado não é tocado de novo até a sessão expirar.

**Conclusão:** uma requisição de API **não pode vazar nem desgastar o certificado**,
porque o certificado não está nela. Fazer 30 ou 30.000 requisições é idêntico para o
certificado — ele foi usado zero vezes em todas elas. O risco do certificado está **em
repouso** (o arquivo `.pfx` + senha, o PIN), não no tráfego — e disso o projeto não
encosta: nunca carregamos chave privada em código (ADR 003).

## 2. O que a requisição EXPÕE: a identidade, por inteiro

A requisição não é um anônimo "autenticado". O JWT identifica o portador
explicitamente. Claims presentes (medidos):

| Claim | Conteúdo |
|---|---|
| `name` / `given_name` | nome completo do advogado titular |
| `preferred_username` | **CPF** do titular |
| `email` | e-mail corporativo do titular |
| `sub` | id estável do usuário no Keycloak |
| `sid` / `session_state` | id da sessão |
| `realm_access.roles` | papéis do usuário |
| `corporativo` | vínculo institucional |

**Conclusão:** cada requisição é **atribuível, no servidor, a essa pessoa específica**.
Não existe camada de anonimato. 30 requisições/hora = 30 atos registrados como sendo
daquele advogado. O certificado (serial, chave pública) **não** vai na requisição — mas a
**identidade que ele autenticou** vai, completa.

## 3. O que é server-side, o que é nosso risco

- **Validação da auth:** server-side. O SSO valida a assinatura do JWT contra a chave
  pública dele. Não temos como forjar.
- **Trilha de auditoria:** server-side, no CNJ/tribunal. Cada acesso é logado (quem, o
  quê, quando) independentemente de nós. Não vemos nem controlamos esse log — ele existe.
- **Nosso risco a guardar:** o **JWT vivo**. Se vazar, alguém age como o advogado até
  expirar. Medido: **8 horas no PDPJ nacional**, 60 min no TRT4. No dia a dia, o token
  vivo é o segredo mais sensível do sistema — mais que o certificado, que fica no SO.

## 4. Volume: o risco real é atribuição, não o certificado

30 req/hora é **trivial** tecnicamente — um advogado navegando consultas faz mais. Não há
preocupação de rate limit nesse patamar. O risco não é a taxa baixa; é **volume sustentado
e anômalo** (milhares/dia) com padrão de robô, atribuído a uma pessoa física.

Consequências realistas, do menos ao mais grave — **nenhuma criminal por si só, mas todas
recaem sobre o advogado**, porque é o ato dele:

1. **Suspensão da credencial** pelo CNJ/tribunal ao detectar automação — bloqueia o
   acesso legítimo do próprio advogado ao PJe. É o resultado mais provável e o mais
   disruptivo para a operação de vocês.
2. **Notificação/apuração** sobre acesso automatizado, sob os termos de uso da PDPJ e
   resoluções do CNJ sobre acesso a sistemas.
3. Em cenário extremo e sustentado, questionamento sobre uso indevido de credencial
   profissional para extração em massa.

## 5. Agravante de governança (o ponto que precisa de decisão humana)

O certificado é **do advogado do setor de tecnologia**, de uso compartilhado pelo setor —
não do operador. Isso não muda a técnica, muda a responsabilização: **todo acesso é,
juridicamente, ato daquele advogado**, mesmo feito por outra pessoa, mesmo automatizado.

Isto **não é decisão de engenharia.** É decisão do próprio advogado titular + compliance/
jurídico do escritório, e precisa ser tomada explicitamente **antes** de qualquer volume,
não depois de um bloqueio. Ver a decisão pendente abaixo.

## 6. O caminho certo se isto virar operação de volume

A resposta correta para volume real **não** é otimizar o uso da credencial de uma pessoa —
é obter **acesso programático autorizado** em nome do escritório:

- **MNI com convênio/credenciamento** junto ao TRT/CNJ (Q4d) — o canal oficial para
  acesso automatizado, em nome da instituição, não de um indivíduo.
- Verificar se a **PDPJ oferece programa de acesso a API** para pessoa jurídica/escritório.

É o princípio "subir de nível" do briefing aplicado à segurança: se a saída parecer ser
espremer a credencial de uma pessoa, a saída certa é institucionalizar o acesso.

## Decisões

**Técnicas (já no projeto, reforçadas por esta ADR):**
- Rate limit por `(tribunal, credencial)`, default conservador. Um número como 30/hora é
  seguro; o teto real vem da medição (Q6c), sempre com margem folgada.
- Auditoria local espelhando a identidade (`auditoria.credencial_id`) — para provar
  legitimidade e reconstruir o que foi feito, em nome de quem.
- Circuit breaker por tribunal; renovação de sessão single-flight (nunca N logins
  concorrentes — é o padrão que dispara alarme).
- **O JWT vivo é o segredo mais protegido:** só em memória/cifrado, TTL curto, nunca em
  log nem no git. `Session.__repr__` já não vaza token.

**De governança (PENDENTE — bloqueia escalar volume, não bloqueia continuar medindo):**
- [ ] O advogado titular e o compliance do escritório aprovam, por escrito, o uso da
      credencial dele para extração automatizada, com um teto de volume acordado?
- [ ] Vale abrir o canal institucional (convênio MNI / API PJ) antes de passar de
      dezenas para milhares/dia?

Enquanto isso não estiver resolvido, o projeto segue em **reconhecimento e volume baixo
de teste** (dezenas), não em produção de volume.
