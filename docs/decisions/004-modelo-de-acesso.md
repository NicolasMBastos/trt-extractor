# 004 — Modelo de acesso: publicidade, não vínculo processual

**Data:** 2026-09-03 · **Estado:** aceita

## Contexto

Durante a fase 0 levantou-se a questão de qual é a base do acesso, já que o
certificado é do titular do escritório e os processos-alvo não são da carteira dele.

A objeção inicial — de que acesso sem vínculo processual equivaleria a acesso não
autorizado — estava errada, e o precedente em produção mostra por quê.

## Como o acesso realmente funciona

No PDPJ/Jus.br, o certificado autentica **identidade**; quem decide o que aquela
identidade pode ver é a **plataforma**, por nível de sigilo do processo:

- **Processo público** — visível a qualquer usuário autenticado. A base é a
  publicidade dos atos processuais (CF art. 93, IX), não a relação com o processo.
  É o mesmo fundamento sobre o qual operam Escavador, Jusbrasil e Digesto.
- **Processo em segredo de justiça** — não abre sem habilitação nos autos. A
  plataforma recusa, e a recusa é a resposta correta, não um obstáculo a contornar.

Ou seja: a fronteira é aplicada pelo sistema, não por nós. Nosso dever é respeitá-la
e nunca tentar movê-la.

## Precedente interno (verificado)

O projeto irmão `TaxMap`, em produção no mesmo escritório:

- autentica com **login manual do titular** no Chrome, PIN digitado à mão
  (`pdpj_selenium.py`: `wait_for_pdpj_login`, "Faça login manual no PDPJ");
- modela `segredo_justica` como campo de primeira classe
  (`consulta_processos_oab/consultar_processos.py:219`) e detecta segredo na
  observabilidade (`observability.py:181-182`);
- condiciona explicitamente a aquisição: *"Autos/inicial — sim quando autorizado e
  disponível"* (`SOURCE_MATRIX.md`);
- proíbe expansão sem base: *"não criar scrapers sem contrato"*, e
  *"`não confirmado` não pode virar capacidade de produção sem fixture/contract test
  ou canary autorizado"*;
- encerra a rodada de estabilização com *"não houve tentativa de evasão de controles"*
  (`FINAL_REPORT.md`).

## Decisão

O `trt-extractor` adota o mesmo modelo, e ele é vinculante:

1. **A base do acesso é a publicidade do processo**, verificada e imposta pela
   plataforma. Não presumimos autorização em lugar algum.
2. **`SIGILOSO` é fronteira dura.** Estado terminal, sem retry, sem via alternativa,
   sem tentativa de obter por outro caminho o que a plataforma negou. Já está assim em
   `core/contracts.py` (`SigiloError`) e na migration (terminal sem transição de saída).
3. **Zero evasão de controle.** Sem contorno de WAF por disfarce, sem rotação de
   identidade para escapar de rate limit, sem fingerprint forjada. `InPageFetchTransport`
   existe para *funcionar dentro* do canal legítimo, não para se passar por outro
   cliente. Se a resposta certa parecer ser evasão, sobe-se de via ou escala-se.
4. **A autenticação é ato do titular.** Login manual com certificado, feito pela pessoa
   titular — como no TaxMap. Não automatizar o titular para fora do laço com
   `client_certificates` e `.pfx` exportável (já descartado na ADR 003 por outro
   motivo; agora há um segundo motivo, mais forte).
5. **Auditoria registra a identidade.** `auditoria.credencial_id` grava qual identidade
   originou cada requisição. Serve para debug, para demonstrar legitimidade e para LGPD.
6. **Rate limit conservador é parte da política de acesso**, não só higiene técnica:
   uma identidade pedindo volume anormal é o que muda a natureza do acesso, mesmo
   quando cada requisição isolada é legítima.

## Consequências

- Nada na arquitetura muda. As salvaguardas já estavam desenhadas — esta ADR as torna
  explícitas e justificadas, em vez de implícitas.
- `capabilities.yaml` ganha, por tribunal, a constatação de como o sigilo se manifesta
  (recusa silenciosa vs. erro explícito): a diferença entre `SIGILOSO` e `INEXISTENTE`
  depende disso, e classificar errado polui a métrica de erro.
- Fica registrado que a via de aquisição preferencial é a autenticada e pública, e que
  fontes licenciadas (Escavador, já contratado) permanecem como complemento legítimo
  para enriquecimento — não como substituto.
