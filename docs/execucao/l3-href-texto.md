# L3: confirmacao de `hrefTexto`

Estado: NAO CONFIRMADO. Nenhuma requisicao foi executada nesta tarefa.

## Hipotese

Uma resposta autorizada de `GET /api/v2/processos/{numero_cnj}` pode incluir
`hrefTexto` em cada documento ou em outro campo estruturalmente associado ao
documento. A resposta pode representar texto, ausencia de texto, erro de
geracao ou documento digitalizado. Nao e permitido derivar uma URL a partir de
`hrefBinario`.

## Probe minimo autorizado

Executar somente por responsavel autorizado, fora de CI e nunca com credencial,
cookie, JWT, HAR ou resposta bruta versionados:

1. Usar uma sessao capturada pelo handshake humano autorizado, sem chave privada.
2. Consultar um unico CNJ autorizado pela via nacional, em baixa taxa.
3. Registrar somente metadados sanitizados: nomes de chaves, tipos JSON, status,
   content-type, tamanho e SHA-256 do corpo. Omitir valores de URL, token,
   cookie, identificador de pessoa e conteudo do texto.
4. Para um `hrefTexto` efetivamente fornecido, fazer no maximo uma leitura com a
   mesma sessao e registrar a mesma telemetria sanitizada.
5. Parar em 401, 403, 429, CAPTCHA, sigilo, ou formato nao reconhecido. Nao
   alternar via, nao repetir, nao usar browser, proxy ou evasao.

## Entrada necessaria

- autorizacao explicita para o CNJ e credencial;
- sessao humana valida, armazenada fora do repositorio;
- identificacao do responsavel e horario do probe;
- destino local protegido para a evidencia sanitizada.

## Resultado esperado

Classificar a observacao em exatamente uma categoria: `texto_disponivel`,
`texto_indisponivel`, `texto_vazio`, `erro`, ou `documento_digitalizado`.
Somente apos uma observacao sanitizada sera definido o contrato de uma pequena
abstracao de texto. OCR continua fora de escopo.

## Risco e evidencia

O risco e expor dados processuais ou tentar uma rota protegida. A evidencia
aceitavel e uma ficha sanitizada contendo hipotese, CNJ mascarado, status,
schema de chaves, content-type, tamanho, hash e decisao. PDF, HAR bruto,
cookies, JWTs e texto integral nao sao evidencia versionavel.
