# Tarefa fase 0 — AGY

Leia a nota do Maestri 'TRT-EXTRACTOR ESTADO' (maestri note read "TRT-EXTRACTOR ESTADO") ANTES de comecar. Ela tem os invariantes, contratos e fatos ja medidos. Nao re-investigue o que ja esta la. Raiz do projeto: C:/Users/nicolas.bastos/Desktop/Projetos/Extrator-Petição. Invariantes que valem para voce: SIGILOSO e terminal legitimo; ZERO evasao de controle (se a saida parecer ser evasao, PARE e escale); nenhum teste bate em tribunal de producao; nao versionar credencial, certificado, .env, PDF ou HAR bruto. Toque APENAS os arquivos listados na sua tarefa. Conflito de merge entre agentes e falha de especificacao minha, nao sua. Ao terminar, responda com: (a) o que entregou, (b) o que descobriu que contraria a premissa, (c) o que ficou em aberto.

=== TAREFA: mapa completo da superficie da API PDPJ ===
ENTRADA (somente leitura): C:/Users/nicolas.bastos/Desktop/Projetos/TaxMap-main/taxmap/jusbr.py (2183 linhas), C:/Users/nicolas.bastos/Desktop/Projetos/TaxMap-main/taxmap/pdpj_selenium.py (3163 linhas), C:/Users/nicolas.bastos/Desktop/Projetos/TaxMap-main/taxmap/config.py, C:/Users/nicolas.bastos/Desktop/Projetos/TaxMap-main/docs/taxmap-stability/ (todos os .md).
Este e um projeto irmao, do mesmo escritorio, em producao, com as mesmas credenciais. E arte previa legitima: minerar, nao reescrever.

SAIDA: crie research/pdpj-api-mapa.md no projeto trt-extractor.

CRITERIO DE ACEITE — o documento tem que responder, com arquivo:linha para cada afirmacao:
1. TODOS os paths de endpoint sob portaldeservicos.pdpj.jus.br que aparecem no codigo. Metodo, query params, headers, corpo. Inclusive os montados dinamicamente por f-string.
2. A PERGUNTA CENTRAL (hipotese H1): existe no codigo QUALQUER indicio de endpoint que devolva o BINARIO de um documento (PDF), e nao apenas metadados/lista? Procure por hrefBinario, idOrigem, arquivo, conteudo, documentos[], _links, /binario, /download, base64. Se NAO existir, diga explicitamente que nao existe e mostre por onde o PDF e obtido em vez disso.
3. A sequencia exata de requests: da autenticacao ate obter o documento. Diagrama ou lista ordenada.
4. Como o Bearer e capturado e como e renovado. Onde expira.
5. EVIDENCIA sobre o WAF (hipotese H2): o que no codigo sustenta ou contradiz a afirmacao de que 'fetch precisa rodar dentro da pagina para passar pelo WAF'. Cite o codigo. Existe alguma tentativa de httpx/requests direto que tenha falhado? Ha comentario, retry ou fallback que indique isso?
6. Paginacao (searchAfter), filtros server-side aceitos, e limites/rate observados.

NAO faca nenhuma chamada de rede. Analise estatica apenas. NAO edite nada em TaxMap-main. Seu unico arquivo de escrita e research/pdpj-api-mapa.md.
