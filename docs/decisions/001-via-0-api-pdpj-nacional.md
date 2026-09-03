# 001 — Via 0: API PDPJ nacional antes do MNI por tribunal

**Data:** 2026-09-03 · **Estado:** aceita, pendente de validação (H1)

## Contexto

O briefing manda tentar as vias nesta ordem: MNI SOAP → "Download autos" filtrado →
documento individual → Playwright → legado. Todas são **por tribunal**: WSDL próprio,
convênio próprio, credenciamento próprio, quirks próprios. São 24 integrações — o
mesmo problema que a seção 3.1 do briefing manda evitar.

O reconhecimento achou uma camada acima. O projeto irmão `TaxMap`, na mesma máquina e
com as mesmas credenciais, roda em produção contra:

```
https://portaldeservicos.pdpj.jus.br/api/v2/processos?cpfCnpjParte=...&filter=...
```

API do Portal de Serviços do PDPJ: **nacional**, chaveada pelo número CNJ unificado,
autenticada pelo mesmo SSO Keycloak que o briefing já identificou
(`sso.cloud.pje.jus.br/auth/realms/pje`), com paginação `searchAfter` e filtro
server-side. Uma integração, não 24.

## Decisão

Inserir **Via 0 — `pdpj_api`** no topo da tabela de vias, acima do MNI. A enum `Via`
em `core/contracts.py` reflete essa ordem.

A Via 0 é a tentativa padrão para todo tribunal. As vias 1–5 do briefing viram
fallback, acionadas quando a Via 0 estiver comprovadamente indisponível **naquele
tribunal** — registrado em `capabilities.yaml`, medido, não presumido.

## Pendência que a valida ou derruba

**H1:** a API v2 entrega o **binário** do documento, ou só a lista de documentos?

O TaxMap usa a API apenas para *listar* processos; para pegar o PDF ele volta a clicar
no DOM (`DOCUMENTO_LINK_SELECTOR`, `DOWNLOAD_BUTTON_SELECTORS`). Isso pode significar
que (a) a API não serve binário, ou (b) ninguém tentou. Não sabemos qual.

- H1 verdadeira ⇒ esta decisão se confirma e o projeto encolhe pela metade.
- H1 falsa ⇒ a Via 0 fica como fonte de listagem e triagem (ainda útil: é ela que dá
  `id_origem`, sem o qual a via 3 não funciona), e a aquisição cai para as vias 1–3.

Em nenhum dos casos a Via 0 é descartada. Muda o quanto ela cobre.

## Alternativas descartadas

- **Seguir o briefing literalmente (MNI primeiro).** Descartada: MNI depende de convênio
  por tribunal, e negociar 24 convênios antes de saber se a API nacional resolve é gastar
  o recurso mais caro (tempo do dono do projeto) no lugar errado.
- **DataJud como via de aquisição.** Descartada — não tem documentos. Fica como seed,
  filtro de desperdício e chave de reconciliação, exatamente como o briefing define.
- **Ir direto ao Playwright.** Descartada: é o nível 4 de 5, e o briefing está certo.

## Consequências

- `capabilities.yaml` ganha `vias.pdpj_api` com estado próprio, incluindo
  `ok_sem_binario` — o resultado esperado se H1 for falsa.
- Se H1 for verdadeira, `adapters/pdpj.py` atende a maioria dos tribunais e
  `adapters/pje2x.py` vira o fallback, não o caminho principal. A fase 5 encolhe.
- A triagem passa a poder usar a Via 0 como fonte de movimentos, reduzindo a dependência
  do DataJud para descartar processo sem peça-alvo.
