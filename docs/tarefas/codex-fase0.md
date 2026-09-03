# Tarefa fase 0 — Codex

Leia a nota do Maestri 'TRT-EXTRACTOR ESTADO' (maestri note read "TRT-EXTRACTOR ESTADO") ANTES de comecar. Ela tem os invariantes, contratos e fatos ja medidos. Nao re-investigue o que ja esta la. Raiz do projeto: C:/Users/nicolas.bastos/Desktop/Projetos/Extrator-Petição. Invariantes que valem para voce: SIGILOSO e terminal legitimo; ZERO evasao de controle (se a saida parecer ser evasao, PARE e escale); nenhum teste bate em tribunal de producao; nao versionar credencial, certificado, .env, PDF ou HAR bruto. Toque APENAS os arquivos listados na sua tarefa. Conflito de merge entre agentes e falha de especificacao minha, nao sua. Ao terminar, responda com: (a) o que entregou, (b) o que descobriu que contraria a premissa, (c) o que ficou em aberto.

=== TAREFA: probe do MNI SOAP em TRT2, TRT4 e TRT13 ===
Responde as perguntas Q4a/Q4b da fase 0 (docs/fase-0/plano.md).

SAIDA: dois arquivos, so estes:
  - scripts/probe_mni.py
  - research/mni-probe.md

ESPECIFICACAO de scripts/probe_mni.py:
  Assinatura: python scripts/probe_mni.py [--tribunal TRT2 ...] [--timeout 15]
  Para cada tribunal: UMA unica requisicao GET ao WSDL publico do MNI. Sem retry, sem paralelismo, timeout 15s, User-Agent identificavel e honesto.
  O WSDL e metadado publico de servico. NAO envie credencial. NAO chame nenhuma operacao. NAO tente autenticar. So buscar e parsear a descricao do servico.
  Parseie e reporte: WSDL responde (S/N + status HTTP); operacoes expostas; se consultarProcesso existe; quais parametros ela aceita (procure incluirDocumentos, incluirCabecalho, movimentos, idConsultante, senhaConsultante); namespace e versao do MNI.
  Sem dependencia nova alem do que ja esta em pyproject.toml (httpx ja esta la). Nao precisa de zeep para ler o WSDL — xml.etree serve e evita instalar dependencia opcional agora.
  Trate falha de rede como resultado valido do probe ('nao respondeu'), nao como crash.

CRITERIO DE ACEITE:
  - O script roda e produz saida legivel mesmo quando todos os tribunais falham.
  - research/mni-probe.md tem uma tabela: tribunal | WSDL responde | operacoes | consultarProcesso | incluirDocumentos aceito | observacao.
  - Celula em branco nao e resposta. 'nao respondeu' e resposta.
  - ruff limpo, mypy limpo, sem segredo no codigo.

IMPORTANTE: se algum WSDL exigir autenticacao ou credenciamento, isso e a RESPOSTA (Q4d: 'precisa de convenio'), nao um obstaculo a contornar. Registre e siga.
