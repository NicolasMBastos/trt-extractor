"""Gera capabilities.yaml com os 24 TRTs em `nao_testado`.

Rodar uma única vez, no bootstrap. Depois disso o arquivo é editado por medição —
ele é dado de produção, lido em runtime, não documentação. Não regenerar por cima
de medições reais sem antes salvar o arquivo.

    py -3.12 scripts/gerar_capabilities.py
"""

from __future__ import annotations

from pathlib import Path

# TRT → UFs de jurisdição. Fonte: organização da Justiça do Trabalho (CNJ/TST).
REGIOES: dict[int, str] = {
    1: "RJ",
    2: "SP - capital e Grande São Paulo",
    3: "MG",
    4: "RS",
    5: "BA",
    6: "PE",
    7: "CE",
    8: "PA, AP",
    9: "PR",
    10: "DF, TO",
    11: "AM, RR",
    12: "SC",
    13: "PB",
    14: "RO, AC",
    15: "SP - interior (Campinas)",
    16: "MA",
    17: "ES",
    18: "GO",
    19: "AL",
    20: "SE",
    21: "RN",
    22: "PI",
    23: "MT",
    24: "MS",
}

# Alvos da fase 0: um grande, um médio, um pequeno.
ALVOS_FASE_0 = {2: "grande", 4: "medio", 13: "pequeno"}

CABECALHO = """# capabilities.yaml — matriz de capacidade por tribunal
#
# DADO DE PRODUÇÃO, não documentação. O orquestrador lê deste arquivo em runtime
# para decidir a via de aquisição, o teto de concorrência e o rate limit de cada
# tribunal. Um valor errado aqui vira tráfego anormal ou throughput jogado fora.
#
# Regra: só sai de `nao_testado` com medição registrada e `testado_em` preenchido.
# Nada de preencher por analogia com tribunal vizinho.
#
# -----------------------------------------------------------------------------
# ESQUEMA
# -----------------------------------------------------------------------------
# <sigla>:
#   regiao: str                  UFs de jurisdição. Informativo.
#   status: nao_testado | parcial | operacional | bloqueado
#
#   vias:                        O que funciona, medido. Ordem de preferência é a
#                                da enum `Via` em core/contracts.py, não a daqui.
#     pdpj_api:        desconhecido | ok | ok_sem_binario | indisponivel
#     mni_soap:        desconhecido | ok | ok_sem_documentos | sem_convenio | indisponivel
#     autos_filtrado:  desconhecido | ok | sem_filtro_tipo | indisponivel
#     doc_individual:  desconhecido | ok | indisponivel
#     browser:         desconhecido | ok | indisponivel
#     legado:          desconhecido | ok | indisponivel | nao_aplicavel
#
#   transporte: desconhecido | httpx | in_page_fetch
#                                Resultado da hipótese H2 (docs/arquitetura.md §4).
#                                `httpx` só depois de provar que o WAF aceita.
#
#   limites:
#     jobs_concorrentes_por_sessao: int|null   MÉTRICA MAIS IMPORTANTE DA FASE 0.
#                                              Mais paralelismo de rede que isto é
#                                              desperdício — precisa é de mais sessão.
#     req_por_minuto: int|null                 Rate limit por (tribunal, credencial).
#                                              Default conservador até medir.
#     limiar_download_sincrono_mb: float|null  Abaixo disso baixa direto; acima enfileira.
#     latencia_geracao_p50_s: float|null       Da submissão à Área de Download.
#     latencia_geracao_p95_s: float|null
#
#   auth:
#     cpf_senha_funciona: desconhecido | sim | nao
#                                Se `sim`, o certificado sai do caminho crítico.
#     mfa: desconhecido | por_dispositivo | por_login | ausente
#     sessao_ttl_s: int|null     Quanto a sessão dura antes de renovar.
#
#   filtro_tipos_disponiveis: [str]  Rótulos de tipo que o tribunal oferece no
#                                    filtro, com a grafia dele. Sem tradução aqui —
#                                    o mapeamento para as 5 classes é do adapter.
#
#   quirks: [str]              Desvios do genérico que exigem override no adapter.
#   janelas_manutencao: [str]  Indisponibilidades programadas conhecidas.
#   adapter: str               Módulo que atende. `pje2x` é o genérico.
#   testado_em: YYYY-MM-DD|null
#   har: str|null              Caminho do HAR sanitizado que comprova o fluxo.
#   notas: str
# -----------------------------------------------------------------------------

versao_esquema: 1
atualizado_em: "2026-09-03"

# Defaults conservadores, aplicados a todo tribunal ainda não medido.
# Estes números existem para NÃO gerar tráfego anormal enquanto não se mediu.
# Não são estimativa de capacidade — são piso de segurança.
defaults: &defaults
  status: nao_testado
  vias:
    pdpj_api: desconhecido
    mni_soap: desconhecido
    autos_filtrado: desconhecido
    doc_individual: desconhecido
    browser: desconhecido
    legado: desconhecido
  transporte: desconhecido
  limites:
    jobs_concorrentes_por_sessao: 1
    req_por_minuto: 6
    limiar_download_sincrono_mb: 3.0
    latencia_geracao_p50_s: null
    latencia_geracao_p95_s: null
  auth:
    cpf_senha_funciona: desconhecido
    mfa: desconhecido
    sessao_ttl_s: null
  filtro_tipos_disponiveis: []
  quirks: []
  janelas_manutencao: []
  adapter: pje2x
  testado_em: null
  har: null
  notas: ""

tribunais:
"""


def main() -> None:
    destino = Path(__file__).resolve().parents[1] / "capabilities.yaml"
    if destino.exists():
        raise SystemExit(
            f"{destino} já existe. Apague manualmente se a intenção é recomeçar — "
            "este script sobrescreve medições."
        )

    linhas = [CABECALHO]
    for n in sorted(REGIOES):
        sigla = f"TRT{n}"
        linhas.append(f"  {sigla}:")
        linhas.append("    <<: *defaults")
        linhas.append(f'    regiao: "{REGIOES[n]}"')
        if n in ALVOS_FASE_0:
            linhas.append(
                f'    notas: "Alvo da fase 0 ({ALVOS_FASE_0[n]}). '
                f'Ver docs/fase-0/plano.md."'
            )
        linhas.append("")

    destino.write_text("\n".join(linhas), encoding="utf-8")
    print(f"escrito: {destino} ({len(REGIOES)} tribunais)")


if __name__ == "__main__":
    main()
