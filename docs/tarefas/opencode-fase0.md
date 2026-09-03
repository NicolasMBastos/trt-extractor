# Tarefa fase 0 — OpenCode

Leia a nota do Maestri 'TRT-EXTRACTOR ESTADO' (maestri note read "TRT-EXTRACTOR ESTADO") ANTES de comecar. Ela tem os invariantes, contratos e fatos ja medidos. Nao re-investigue o que ja esta la. Raiz do projeto: C:/Users/nicolas.bastos/Desktop/Projetos/Extrator-Petição. Invariantes que valem para voce: SIGILOSO e terminal legitimo; ZERO evasao de controle (se a saida parecer ser evasao, PARE e escale); nenhum teste bate em tribunal de producao; nao versionar credencial, certificado, .env, PDF ou HAR bruto. Toque APENAS os arquivos listados na sua tarefa. Conflito de merge entre agentes e falha de especificacao minha, nao sua. Ao terminar, responda com: (a) o que entregou, (b) o que descobriu que contraria a premissa, (c) o que ficou em aberto.

=== TAREFA: sanitizador de HAR + storage local content-addressed ===
Duas entregas independentes. A primeira BLOQUEIA a captura de HAR da fase 0, entao faca ela primeiro.

--- ENTREGA 1: scripts/sanitizar_har.py ---
  HAR bruto carrega Authorization, cookies e peca processual. So a versao sanitizada pode ser versionada — o CI (.github/workflows/ci.yml, job 'segredos') barra o resto.
  Assinatura: python scripts/sanitizar_har.py ENTRADA.har [-o SAIDA.sanitized.har]
  Default de saida: mesmo nome com sufixo .sanitized.har
  Remove/mascara: headers Authorization, Cookie, Set-Cookie, X-CSRF-Token e qualquer header cujo nome contenha token/auth/session/key (case-insensitive); query params com esses mesmos nomes; corpos de resposta que nao sejam JSON/texto pequeno de metadado (substitua por marcador com content-type e tamanho); padroes de CPF (NNN.NNN.NNN-NN e 11 digitos) e CNPJ; conteudo base64 longo (>512 chars).
  PRESERVA: URLs, metodos, status, timing, nomes de header, estrutura — e o que torna o HAR util.
  Imprime um resumo do que foi removido, por categoria e contagem.
  Teste: tests/test_sanitizar_har.py com um HAR sintetico fixture (crie voce, nao use HAR real). Assere que nenhum dos padroes sobrevive e que as URLs sobrevivem.

--- ENTREGA 2: src/trt_extractor/storage/local_cas.py ---
  Implementa o Protocol Storage de src/trt_extractor/core/contracts.py. LEIA o contrato primeiro. NAO edite contracts.py — se precisar de mudanca, peca ao Maestro.
  Classe LocalCASStorage(raiz: Path). Content-addressed por sha256, layout de fanout (ab/cd/abcdef...), para nao criar um diretorio com 100k arquivos.
  put() idempotente: regravar o mesmo conteudo e no-op, nao reescreve. Escrita atomica (tmp + rename) para sobreviver a kill -9 no meio — a fase 3 exige retomada sem corromper.
  Teste: tests/test_local_cas.py com tmp_path. Cobre: put/get/exists, idempotencia, sha256 conferido na leitura, e que put duas vezes nao duplica arquivo.

ARQUIVOS QUE VOCE PODE TOCAR (apenas estes 4):
  scripts/sanitizar_har.py, tests/test_sanitizar_har.py,
  src/trt_extractor/storage/local_cas.py, tests/test_local_cas.py

CRITERIO DE ACEITE: pytest passa, ruff limpo, mypy limpo, zero rede em qualquer teste.
