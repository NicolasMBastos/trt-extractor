# L2: interpretacao local do binario

Fonte: research/evidencia/pdpj-nacional-H1-CONFIRMADA-2026-09-03.md,
secao Ressalva de confiabilidade. Foram registrados tamanho de 57 bytes e
prefixo JSON, sem codigo completo. A semantica de geracao e NAO CONFIRMADA.

| Entrada | Interpretacao | Acao local | Resultado |
| --- | --- | --- | --- |
| 200, assinatura %PDF-, fim %%EOF | candidato PDF completo | calcular SHA dos bytes originais | Artefato |
| 200 PDF com Content-Type JSON | header inconsistente | assinatura e completude prevalecem | Artefato application/pdf |
| JSON com regra de geracao explicitamente injetada | geracao reconhecida pela politica do chamador | uma leitura, sem sleep | GERANDO |
| JSON sem regra reconhecida | resposta nao comprovada | nao gravar, nao supor retry de geracao | PermanenteError |
| 200 HTML ou outro formato | conteudo inesperado | nao gravar | PermanenteError |
| corpo vazio, 206 ou Content-Range | resposta incompleta | nao gravar, retry limitado pelo chamador | TransienteError |
| assinatura PDF sem terminador | possivel truncamento | nao gravar | TransienteError |
| 401 | sessao recusada | entregar renovacao ao pool | SessaoExpiradaError |
| 403 sem evidencia de sigilo | acesso negado ambiguo, inclusive WAF | nao inferir SIGILOSO; nao trocar via | BloqueioError |
| nivelSigilo nao publico explicito | restricao legitima | nao buscar documento | SigiloError |
| 404 | recurso inexistente | sem retry | InexistenteError |
| 429 | limite do servidor | backoff fora do adapter | BloqueioError |
| 5xx ou timeout | falha transiente | backoff fora do adapter | TransienteError |
| redirecionamento | rota nao aceita implicitamente | nao seguir com credenciais | PermanenteError |

Assinatura e terminador sao uma verificacao de transporte, nao uma validacao
estrutural completa de PDF. Nao prometem paginas parseaveis nem conteudo textual.
Content-Length so pode ser comparado aos bytes recebidos quando nao houve
descompressao indicada por Content-Encoding.

O adapter nao executa retries nem escolhe prazo: poll_download faz uma leitura.
O futuro orquestrador deve limitar tentativas e deadline, com backoff configuravel.
Reconhecimento de geracao sera desativado por padrao ate existir payload autorizado
sanitizado. Fixtures de geracao devem dizer SINTETICO, jamais evidencia nacional.

## Coleta futura, nao executada

- Hipotese: o JSON observado sinaliza geracao assincrona.
- Entrada necessaria: Session de handshake humano e hrefBinario publico ja listado,
  em processo expressamente autorizado; nao usar o codigo 403 como atalho.
- Procedimento: uma requisicao ao href original; registrar apenas status, tipo,
  tamanho e estrutura/codigo sanitizado. Uma segunda leitura somente sob limite
  e autorizacao definidos para a coleta.
- Esperado: relacionar codigo documentado a PDF posterior, ou rejeitar a hipotese.
- Risco: trafego atribuivel ao titular e conteudo pessoal no corpo.
- Evidencia persistida: estrutura sintetizada/redigida; nenhum JWT/cookie/PDF/HAR bruto.
- Nenhuma execucao contra producao foi autorizada ou feita nesta rodada.
