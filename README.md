# trt-extractor

Aquisição em volume de peças processuais (PDF) dos 24 TRTs.

Cinco classes-alvo: **petição inicial, acórdão, sentença, acordo, laudo/perícia**.
O entregável é o binário — metadado existe só para saber qual arquivo buscar e onde
guardar. Este não é um projeto de metadados.

Acesso por certificado digital próprio, legítimo, que já seria feito manualmente. O
objetivo é volume e velocidade, não acesso a algo indisponível.

> **Estado: fase 0 (reconhecimento).** Nenhum código de extração escrito, por decisão.
> Ver `docs/fase-0/plano.md`.

## Comece por aqui

| Documento | O que é |
|---|---|
| [`docs/arquitetura.md`](docs/arquitetura.md) | A arquitetura, e onde ela diverge do briefing original |
| [`docs/fase-0/plano.md`](docs/fase-0/plano.md) | Checklist executável da fase 0 + **3 perguntas para o dono do projeto** |
| [`docs/decisions/`](docs/decisions/) | Registros de decisão arquitetural |
| [`docs/maestri-cli.md`](docs/maestri-cli.md) | Mapa do Maestri CLI desta versão |
| [`capabilities.yaml`](capabilities.yaml) | Matriz de capacidade — **dado de produção**, lido em runtime |

## Estrutura

```
src/trt_extractor/
  core/contracts.py     TribunalAdapter, Transport, Session, Storage — interfaces
  adapters/             pdpj (Via 0, nacional) · pje2x (genérico) · mni · por tribunal
  storage/              content-addressed por sha256
  classify/             tipo_pje → posição no fluxo → keywords → LLM
migrations/001_inicial.sql   esquema + máquina de estados validada por trigger
config/keywords.yaml         VAZIO por design — ver abaixo
capabilities.yaml            24 TRTs, todos `nao_testado`
research/har/                HARs sanitizados da fase 0
```

## As duas perguntas que travam o projeto

Nenhuma linha de adapter antes destas duas respostas (`docs/arquitetura.md` §4):

- **H1** — a API nacional `portaldeservicos.pdpj.jus.br/api/v2` entrega o **binário** do
  documento, ou só a lista? Se entregar, 24 integrações viram 1.
- **H2** — o WAF rejeita `httpx` portando o mesmo Bearer que funciona via `fetch` dentro
  da página? Se rejeitar, o substrato de volume não é HTTP paralelo.

## Desenvolvimento

Python **3.12** (a máquina tem 3.14; ver arquitetura §2 D6).

```bash
py -3.12 -m venv .venv && .venv/Scripts/activate   # Windows
pip install -e ".[dev,pdf]"

pytest -m "not rede and not portao"   # suíte normal — tem que ficar verde
pytest -m "portao"                    # portões de fase — vermelho de propósito
```

`-m "not rede"` é obrigatório: **zero teste que bate em tribunal de produção**.

### `config/keywords.yaml` está vazio, e o teste falha

É proposital. As palavras-chave são fornecidas pelo dono do projeto —
`tests/test_config.py::test_keywords_preenchido` é o portão que impede a fase 4 de ser
declarada pronta com o classificador vazio. Não preencher para fazer passar.

## Segurança e conformidade

- `.gitignore` exclui certificados, credenciais, `.env` e **todo PDF**. O CI tem job
  próprio que barra qualquer um deles no índice.
- HAR bruto carrega `Authorization`, cookies e peça processual. Só entra no git
  sanitizado (`*.sanitized.har`) — o CI verifica.
- Chave privada, senha de certificado e PIN nunca entram no processo nem em log.
  `Credencial` e `Session` têm `__repr__` que não vaza CPF nem token.
- `SIGILOSO` é estado terminal **legítimo**, não erro: registra, não faz retry, e sai do
  denominador da taxa de erro (view `v_taxa_erro`).
- Auditoria completa por credencial/processo/peça — para debug, para demonstrar
  legitimidade e para LGPD.
- **Não há evasão de detecção neste projeto.** Se essa parecer a saída, a resposta certa
  é subir de via ou escalar a decisão.
