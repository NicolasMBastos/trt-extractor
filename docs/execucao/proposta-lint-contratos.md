# Proposta separada: compatibilidade do contrato com o lint

Estado: APLICADA em 2026-09-08, com autorizacao do orquestrador. Arquivo
protegido: src/trt_extractor/core/contracts.py.
Nao ha necessidade de mudar assinaturas, campos, enums ou semantica para o adapter.
O bloqueio aqui e mecanico: o Gate 1 exige lint global verde, e o baseline tem
nove ocorrencias neste arquivo, alem de quatro alinhamentos do formatter.

Patch proposto, restrito a este arquivo:

1. Acrescentar `from collections.abc import Iterable, Mapping` antes de dataclasses;
   remover `Iterable, Mapping` do import de typing. As anotacoes ficam identicas.
2. Nas seis declaracoes abaixo, acrescentar `# noqa: UP042`:
   `TipoDocumento(str, Enum)`, `Grau(str, Enum)`, `EstadoJob(str, Enum)`,
   `Via(str, Enum)`, `StatusDownload(str, Enum)`, `MetodoClassificacao(str, Enum)`.
   Justificativa: converter para StrEnum mudaria str(membro), comportamento publico.
   Manter a heranca atual e intencional, nao trocar enum para satisfazer estilo.
3. Nas docstrings substituir apenas `70–90%` por `70-90%` e `0–4` por `0-4`.
4. Aplicar os quatro alinhamentos exigidos pelo formatter:

```diff
-    PDPJ_API = "pdpj_api"          # 0 — nacional, api/v2
-    MNI_SOAP = "mni_soap"          # 1 — por tribunal
+    PDPJ_API = "pdpj_api"  # 0 — nacional, api/v2
+    MNI_SOAP = "mni_soap"  # 1 — por tribunal
-    BROWSER = "browser"            # 4 — Playwright no navegador oficial
-    LEGADO = "legado"              # 5 — visualizadores legados (VDOC etc.)
+    BROWSER = "browser"  # 4 — Playwright no navegador oficial
+    LEGADO = "legado"  # 5 — visualizadores legados (VDOC etc.)
```

Aceite: nenhuma mudanca de valor/assinatura/campo, str dos enums preservado,
suite offline verde, mypy e lint global verdes. Nenhum ADR/migration/capability alterado.
Validacao posterior:

- `ruff check . --no-cache`: aprovado;
- `ruff format --check . --no-cache`: 49 arquivos ja formatados;
- suite offline: 159 aprovados, 1 excluido;
- `mypy`: 10 arquivos fonte sem erros.

O patch preserva os valores, assinaturas, campos e comportamento publico dos
enums. Nenhum ADR, migration ou capability foi alterado.
