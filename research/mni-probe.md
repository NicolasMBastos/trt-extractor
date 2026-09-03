# Probe MNI SOAP - fase 0

Data: 2026-09-03

Foco atualizado: TRT4 (Rio Grande do Sul) e o alvo primario. TRT2 e TRT13
ficam como contraste.

Comando previsto:

```powershell
rtk python scripts/probe_mni.py --timeout 15
```

Escopo do probe: uma requisicao GET sequencial ao WSDL publico de cada tribunal,
sem credenciais, sem retry, sem paralelismo, sem seguir redirect automaticamente e
sem chamada a qualquer operacao SOAP.

| tribunal | WSDL responde | operacoes | consultarProcesso | incluirDocumentos aceito | observacao |
|---|---|---|---|---|---|
| TRT4 | nao testado de novo | nao identificado | nao identificado | nao identificado | sem URL WSDL oficial publicada em fonte documental; Q4d aponta para credenciamento/liberacao previa |
| TRT2 | nao testado de novo | nao identificado | nao identificado | nao identificado | contraste mantido; sem nova fonte documental apurada nesta tarefa |
| TRT13 | nao testado de novo | nao identificado | nao identificado | nao identificado | contraste mantido; sem nova fonte documental apurada nesta tarefa |

## Conclusao documental

Nao encontrei endpoint MNI/WSDL oficial do TRT4 publicado em fonte documental.
Com base nas fontes oficiais abaixo, a conclusao operacional para Q4d e:
MNI do TRT4 exige credenciamento/liberacao previa do canal de integracao antes
de qualquer probe util de WSDL/operacao.

Por isso, nao atualizei `WSDL_URLS` com uma nova URL e nao rodei novo probe: sem
URL oficial, repetir GET contra candidato inferido seria nova tentativa por chute.

## Fontes documentais consultadas

| fonte | achado |
|---|---|
| CNJ, "Integracao para os Tribunais" - https://www.cnj.jus.br/integracao-para-os-tribunais/ | O tribunal precisa disponibilizar operacoes MNI em endpoint SOAP, informar ao CNJ link de WSDL em homologacao, URL MNI de producao, versao, usuario/senha de homologacao e liberar acesso externo. A propria pagina registra que, ate a homologacao/autorizacao, nada esta disponivel para acesso publico. |
| Escritorio Digital/CNJ - https://www.escritoriodigital.jus.br/escritoriodigital/login.faces | A FAQ informa que o tribunal deve liberar adaptacoes em `consultarAvisosPendentes` e `consultarProcesso`, informar link MNI de homologacao com usuario/senha nos campos `idConsultante` e `senhaConsultante`, liberar acesso externo e depois certificar link de producao e usuarios autorizados via MNI. |
| Documentacao PJe, "Servico MNI Client" - https://docs.pje.jus.br/servicos-auxiliares/servico-mni-client/ | O MNI Client suporta MNI 2.2.2, 2.2.3 e 3.0.0, mas os endpoints sao restritos por roles (`invoke-service-endpoint` para servico e `admin` para configuracao). |
| Documentacao PJe, "Configurando parametros" - https://docs.pje.jus.br/configura%C3%A7%C3%B5es-do-pje/Configurando%20par%C3%A2metros/ | Para remessa MNI ao STF, o WSDL de producao deve ser solicitado por administrador do PJe a equipe tecnica do PJe; a documentacao nao trata URL de producao como descoberta publica. |
| Portal TRT4 Governanca - https://www.trt4.jus.br/portais/governanca/resumo-projetos-2020 | O TRT4 registra que o PJe e acessado por webservices/procedures/views e que ha documentacao interna dessas integracoes, mas nao publica endpoint MNI/WSDL. |
| TaxMap-main, `docs/taxmap-stability/BUILD_BUY_SOURCES.md:11` e `:28` | A arte previa nao cita endpoint; registra MNI como integracao sistema-sistema que exige certificado, convenios/acordos, escopo de acesso e liberacao por IP/Escritorio Digital. |
| TaxMap-main, `docs/taxmap-stability/SOURCE_RESEARCH_2026-08-25.md:29-31` | A arte previa descreve MNI/WSDL/SOAP como padrao oficial para fonte primaria, historicamente voltado a orgaos publicos e escritorios conveniados. |

## Medicao anterior invalidada

- TRT4: `https://pje.trt4.jus.br/primeirograu/intercomunicacao?wsdl` respondeu HTTP 404.
- TRT2: `https://pje.trt2.jus.br/primeirograu/intercomunicacao?wsdl` respondeu HTTP 404.
- TRT13: `https://pje.trt13.jus.br/primeirograu/intercomunicacao?wsdl` respondeu HTTP 403.

Esses resultados agora ficam classificados como medicao de candidatos sem fonte
documental, nao como evidencia de inexistencia do MNI.
