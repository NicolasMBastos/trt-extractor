# EXECUTION REPORT - TRT Extractor

## Estado inicial

Checkout `main` limpo em `7057fa2`. O baseline em ambiente gravável foi 35 pass e 1
portão excluído. O sandbox puro falhou em 13 `tmp_path` por WinError 5.

## Execução e evidência

| Task | Agente | Resultado | Evidência |
| --- | --- | --- | --- |
| Contrato PDPJ | Prisma/Claude e Codex | revisado | decisão refletida nos testes |
| Fixture PDPJ | Molde/OpenCode e Codex | concluída | `tests/fixtures/pdpj/` |
| L2 | Codex após falha AGY | parcial | `download-l2.md` |
| HttpxTransport | Sonda/Claude e Codex | concluído | 49 testes MockTransport |
| Adapter PDPJ | Codex | concluído localmente | seleção, sigilo, erro e PDF |
| SessionPool | Codex | concluído localmente | 50 consumidores e invalidação |
| Classificação por código | Codex | concluído localmente | cinco testes; mapeamento injetado |
| Preparação L3 | Codex | concluído | probe sanitizado, sem rede |

## Código alterado

- `core/httpx_transport.py`: HTTP/2, UA estável, origem HTTPS, cookies isolados e erros sem segredo.
- `adapters/pdpj.py`: Via 0 nacional com sessão existente, grau e geração injetáveis.
- `core/session_pool.py`: chave tribunal/credencial, single-flight, pausa e invalidação.
- `classify/tipo_pje.py`: camada 1 determinística, sem fallback por texto ou posição.
- `docs/execucao/l3-href-texto.md`: hipótese, limite e evidência mínima para o probe autorizado.
- `tests/`: bloqueio outbound, fixtures e cobertura dos componentes.

## Testes

- Final: 164 pass, 1 deselected em Python 3.12.13.
- Mypy: 11 arquivos fonte sem erros.
- `git diff --check`: sucesso.
- Lint global: aprovado (`ruff check . --no-cache` e `ruff format --check . --no-cache`).
  O ajuste mecânico documentado em `proposta-lint-contratos.md` preservou a API pública do
  contrato protegido.

## Lacunas

| Lacuna | Estado |
| --- | --- |
| L1 sigilo | CLOSED como limite legal |
| L2 JSON antes do PDF | PARTIAL, sem payload nacional confirmado |
| L3 hrefTexto | OPEN |
| L4 sessão de dispositivo | OPEN |
| L5 concorrência real | OPEN; software testado, teto não medido |
| L6 TRT2/TRT13 | OPEN |
| L7 documentos volumosos | OPEN |
| L8 governança | OPEN |

## Fases, decisões e riscos

Fase 0 e Fase 2 permanecem comprovadas pela evidência existente. Fase 1 tem base offline,
mas não integração com captura autorizada. Fases 3-6 não iniciaram.

O adapter não faz handshake, não infere grau, `hrefTexto` ou JSON de geração, e exige um
documento explicitamente selecionado por pedido. Nenhuma requisição judicial foi feita.

## Próximas tarefas

1. Revisão independente do adapter/transport antes de usar sessão real.
2. Persistência cifrada de storage state, com permissões e corrupção.
3. Provedor de sessão capturada para integrar `SessionPool` sem login automatizado.
4. Repositório de jobs sobre a migration e teste de restart.
5. Classificação por códigos comprovados.
6. Medição autorizada L2 sanitizada.
7. Medição autorizada L3 sem OCR.
8. Contraste TRT2/TRT13 em baixa taxa autorizada.
9. Aprovação de governança antes de volume.
