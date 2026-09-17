# Contrato de Persistência Segura de `Session`

**Estado:** contrato de pré-implementação  
**Escopo:** definir requisitos para uma futura persistência de `storage_state`  
**Fora do escopo:** implementar persistência, criptografia, autenticação, login ou browser

## 1. Objetivo e autoridade

Este documento fecha o comportamento que uma futura implementação deverá cumprir antes
de tirar o `SessionPool` do modo exclusivamente em memória. Ele complementa, sem alterar,
os contratos em `src/trt_extractor/core/contracts.py` e as decisões 003, 006 e 007.

Persistir uma sessão significa persistir uma credencial viva. O artefato pode permitir
que outra parte aja como a credencial até a expiração. Portanto, a persistência é
opcional e deve ser tratada como segredo de alto impacto, não como cache comum.

Enquanto as decisões humanas deste documento estiverem abertas, o comportamento
oficial continua sendo somente em memória.

## 2. Modelo de ameaça

### Ativos protegidos

- `Session.token`, incluindo JWT e qualquer token equivalente.
- `Session.cookies`, incluindo cookies de autenticação, CSRF/XSRF e de afinidade.
- Demais valores de `storage_state` que possam manter ou reconstituir a sessão.
- A associação entre sessão, `credencial_id` e `tribunal`.
- A trilha local de auditoria sobre emissão, carregamento, rejeição, invalidação e rotação.

### Adversários e falhas consideradas

- Leitura não autorizada do arquivo, diretório, volume, backup ou snapshot que contenha o
  estado persistido.
- Usuário ou processo local sem autorização suficiente para operar aquela credencial.
- Vazamento acidental por logs, tracebacks, dumps, métricas, mensagens de erro, git ou
  artefatos de teste.
- Corrupção, truncamento, cópia parcial, replay de uma versão antiga ou troca de arquivo
  entre tribunais/credenciais.
- Falha durante gravação, carregamento, descriptografia, expiração ou rotação.
- Confusão entre sessões de credenciais diferentes ou de tribunais diferentes.

### Não é uma garantia deste contrato

Este contrato não define como proteger a máquina, o processo em execução, a memória
durante o uso, o endpoint do tribunal ou a conta do titular contra uso autorizado em
volume indevido. Também não autoriza o uso da credencial. A aprovação do titular e de
compliance/jurídico permanece necessária conforme ADR 007.

## 3. Dados permitidos e proibidos

### Permitidos no estado persistido

Somente os dados necessários para reconstruir uma sessão já emitida, após validação:

- cookies e valores de storage necessários ao transporte autenticado;
- `tribunal`;
- `credencial_id`;
- `emitido_em`;
- `expira_em`, quando conhecido e verificável;
- versão/formato do envelope e identificador não secreto para diagnosticar compatibilidade;
- integridade/autenticidade do envelope, se exigidas pelo mecanismo escolhido.

Metadados podem existir em registro separado, desde que não revelem segredo e mantenham
a mesma associação de escopo. O identificador da credencial deve ser suficiente para
selecionar o contexto correto; CPF cru, token ou cookie não devem ser usados como
identificador de log.

### Proibidos

- certificado A1, arquivo `.pfx`/`.p12`, chave privada, senha, PIN ou qualquer material
  criptográfico do certificado;
- `contexto_browser` ou handle equivalente, páginas, conexões ou objetos do Playwright/CDP;
- token, cookie ou valor de storage em texto puro fora da área protegida definida após a
  decisão de chave;
- CPF cru, headers de autenticação, conteúdo de `Authorization` ou dumps do envelope em
  logs, auditoria, métricas, exceções, testes, git e relatórios;
- estado de uma credencial/tribunal em um registro cujo escopo pertença a outro par;
- dados recebidos sem validação de validade, identidade e integridade.

Não é permitido persistir apenas o JWT como atalho: a sessão pode depender do conjunto
de cookies e storage, conforme ADR 006.

## 4. Origem e gestão da chave: decisão humana pendente

**Pendente e bloqueante:** o titular do risco, com compliance/jurídico e a operação,
deve aprovar por escrito de onde vem a chave de proteção, quem pode usá-la, como é
disponibilizada ao processo e como é recuperada quando necessário.

Este documento deliberadamente **não escolhe nem presume** cofre, KMS, HSM, variável de
ambiente, arquivo de chave, senha, agente, sistema operacional ou qualquer outro
provedor. Nenhum desses mecanismos deve ser introduzido por uma implementação futura
sem decisão explícita.

A decisão deve responder, no mínimo:

- quem é o proprietário e o custodiante da chave;
- quais identidades/processos podem cifrar, decifrar, listar metadados e invalidar;
- se a chave pode ser usada somente localmente e sob quais condições;
- como ocorre recuperação, indisponibilidade, perda e substituição da chave;
- como se registra a auditoria sem registrar a chave ou o estado em claro;
- qual é a política de retenção e destruição dos estados protegidos e seus backups;
- se a persistência será habilitada em produção ou apenas em ambientes controlados.

Sem essas respostas, a implementação posterior deve falhar fechada ou permanecer em
memória, nunca criar uma chave implícita nem gravar estado em claro.

## 5. Permissão e isolamento

- O arquivo/envelope e qualquer diretório pai devem ser acessíveis somente pela identidade
  operacional aprovada para esse serviço, com permissões mínimas de leitura/escrita.
- A implementação deve validar a identidade e o escopo antes de devolver uma `Session` ao
  pool; não basta confiar no nome do arquivo.
- Cada entrada é endereçada pelo par `(tribunal, credencial_id)`. Não há fallback para
  outra credencial, tribunal ou sessão global.
- O carregamento deve rejeitar escopo divergente, registro duplicado ambíguo, metadado
  incompatível ou envelope que não possa ser validado.
- Um estado carregado não pode ser impresso, retornado para diagnóstico ou incluído em
  exceção. A representação segura já exigida por `Session` deve continuar valendo.
- Auditoria registra evento, resultado, par de isolamento e motivo sanitizado, mas nunca
  token, cookie, storage, chave, senha, CPF cru ou conteúdo do envelope.

As permissões concretas, inclusive usuário/grupo/conta de serviço e política de backup,
dependem da decisão de gestão de chave e do ambiente; não são inventadas aqui.

## 6. Ciclo de vida e validade

1. Captura: aceitar somente `storage_state` produzido após autenticação explícita e
   associá-lo ao tribunal e à credencial que o emitiram.
2. Validação: conferir formato, integridade/autenticidade, escopo e `expira_em` antes de
   instalar o estado no `SessionPool`.
3. Uso: nunca entregar ao transporte uma sessão já expirada ou dentro da margem de
   renovação configurada; a política existente de validade do pool continua aplicável.
4. Falha: estado ausente, ilegível, corrompido, incompatível ou expirado é descartado ou
   isolado sem reutilização. Deve resultar em renovação/reautenticação conforme o pool,
   não em tentativa de uso do estado inválido.
5. Invalidação: `invalidate` deve impedir que estado previamente carregado volte a ser
   instalado; renovações concorrentes obsoletas não podem sobrescrever a invalidação.
6. Pausa: falha de renovação silenciosa pausa o par afetado e exige nova sessão autorizada,
   sem preservar o segredo inválido como caminho de recuperação.

## 7. Atomicidade, corrupção e recuperação

- A publicação de uma nova versão deve ser atômica para leitores: eles veem a versão
  anterior completa ou a nova completa, nunca um arquivo parcial.
- Escrita interrompida não pode substituir a última versão válida nem produzir uma entrada
  que pareça válida.
- A validação deve ocorrer antes da publicação e novamente antes de instalar no pool.
- Corrupção, falha de autenticação do envelope, schema desconhecido ou truncamento devem
  ser tratados como estado inutilizável e não como sessão vazia.
- Não fazer fallback silencioso para dados em claro, cópia temporária não protegida ou
  outro tribunal/credencial.
- Após falha, remover/invalidar a versão defeituosa de modo que ela não seja reutilizada;
  preservar somente metadados de auditoria sanitizados e, se aprovado, a última versão
  protegida válida.
- Recuperação exige nova leitura autorizada ou nova autenticação do titular quando não
  houver uma versão válida. Nunca recuperar copiando certificado ou chave privada.

## 8. Rotação e expiração

**Pendente:** a gestão de chave deve aprovar periodicidade, gatilho e procedimento de
rotação, incluindo coexistência temporária de versões, revogação da chave anterior e
tratamento de backups.

O contrato mínimo para qualquer procedimento aprovado é:

- identificar a versão da chave/envelope sem expor a chave;
- revalidar cada sessão antes de reempacotá-la;
- publicar a nova versão atomicamente;
- não aceitar estado expirado apenas porque foi reprocessado durante a rotação;
- impedir que uma versão antiga revogada seja carregada;
- auditar sucesso, falha e descarte sem dados secretos;
- se não for possível re-envelopar com segurança, invalidar a sessão e exigir renovação,
  sem tocar no certificado A1.

Rotação de chave não é renovação de sessão. Renovar o JWT/cookies depende do fluxo de
autenticação já decidido no ADR 006; não deve ser simulado usando material do certificado.

## 9. Critérios de teste offline para habilitar implementação

Os testes podem usar sessões sintéticas e segredos fictícios. Não podem usar certificado,
PIN, CPF real, token real, cookie real, login, browser ou rede.

Uma implementação futura somente fica habilitada quando demonstrar, no mínimo:

- round-trip de um estado sintético preserva os campos permitidos e não inclui
  `contexto_browser`;
- nenhum segredo aparece em `repr`, logs, exceções, métricas, fixtures, snapshots ou
  arquivos temporários de teste;
- entrada em claro, truncada, adulterada, de formato desconhecido ou com integridade
  inválida é rejeitada;
- estado expirado e estado dentro da margem de renovação não são entregues ao transporte;
- tribunal A não consegue carregar estado do tribunal B, e credencial A não consegue
  carregar estado da credencial B;
- estado sem `expira_em`, com timezone inválido ou com identidade divergente é rejeitado;
- gravação interrompida deixa o leitor com a versão anterior ou sem versão, nunca parcial;
- concorrência entre carga, `put`, `invalidate` e renovação não permite que estado obsoleto
  sobrescreva estado novo ou invalidação;
- corrupção e falha de chave não ativam fallback inseguro nem reutilização;
- rotação aprovada mantém atomicidade e rejeita versões revogadas;
- auditoria contém os eventos esperados, com `tribunal`, `credencial_id` e resultado, sem
  qualquer segredo;
- ausência, indisponibilidade ou recusa do mecanismo de chave mantém o sistema seguro:
  modo em memória ou falha fechada, conforme decisão humana aprovada.

Esses testes são critérios de contrato, não uma autorização para implementar o mecanismo.

## 10. Decisões e bloqueios

### Decisões já fixadas

- A sessão é segredo vivo e deve ser cifrada em repouso; nunca em texto puro.
- Certificado A1 e chave privada permanecem no repositório do sistema operacional e fora do
  processo; não são carregados, copiados ou persistidos por este projeto.
- O escopo de isolamento é `(tribunal, credencial_id)`.
- Sessão inválida, expirada, corrompida ou de escopo divergente não pode ser reutilizada.
- Auditoria deve ser preservada sem conteúdo secreto.
- O `SessionPool` permanece em memória até o contrato de chave ser decidido.

### Decisões humanas pendentes

- [ ] Aprovar ou rejeitar persistência durável de sessão para cada ambiente.
- [ ] Definir origem, custodiante, permissões, recuperação e rotação da chave.
- [ ] Definir retenção, destruição, backup e restauração dos estados protegidos.
- [ ] Definir quem autoriza reautenticação e invalidação operacional.
- [ ] Aprovar o teto de responsabilidade e uso automatizado da credencial, conforme ADR 007.

Enquanto qualquer item bloqueante permanecer aberto, não há contrato de implantação nem
permissão para armazenar `storage_state`.
