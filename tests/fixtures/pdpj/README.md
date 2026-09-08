# Fixture PDPJ sintetica

Este diretorio contem somente dados sinteticos para testes offline. Nao e uma
gravacao, HAR, PDF, resposta de producao, nem material suficiente para chamar
um sistema judicial.

## Campos estruturais observados

A evidencia local registra `tramitacaoAtual.documentos`, `sequencia`,
`idCodex`, `idOrigem`, `nome`, `nivelSigilo`, `tipo.codigo`, `hrefBinario` e
`hrefTexto`. `hrefBinario` e `hrefTexto` foram observados como caminhos
relativos no mesmo processo.

## Valores inventados para cobertura

CNJ, IDs, nomes, datas, grau literal e o conteudo de todos os documentos sao
sinteticos. So `tipo.codigo=202` para peticao inicial e `402` para certidao
foram registrados na evidencia. Os codigos 990001 e 990002 existem apenas para
testar preservacao de codigo desconhecido; nao sao codebook nacional.

O fixture preserva `hrefTexto` como evidencia estrutural. O contrato atual nao
tem campo para ele e nenhum adapter deve reconstruir essa URL por inferencia.
