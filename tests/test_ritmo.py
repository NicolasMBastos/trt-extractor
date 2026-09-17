"""Testes da camada de ritmo. Sem rede, sem relógio real, sem sono real.

O que importa provar aqui não é que o código espera — é que ele **se recusa a esperar**
nos dois casos em que esperar seria errado: disjuntor aberto (parada) e fora da janela
(reagendamento). E que nenhum número sai de dentro do código.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trt_extractor.core.capabilities import (
    VERSAO_ESQUEMA,
    Capabilities,
    CapabilitiesError,
)
from trt_extractor.core.contracts import (
    BloqueioError,
    InexistenteError,
    PermanenteError,
    SigiloError,
    TransienteError,
)
from trt_extractor.core.ritmo import (
    Disjuntor,
    DisjuntorAbertoError,
    Fase,
    ForaDaJanelaError,
    JanelaOperacional,
    Ritmo,
)

MATRIZ_REAL = Path(__file__).resolve().parents[1] / "capabilities.yaml"
BRASILIA = timezone(timedelta(hours=-3))
# Segunda-feira, 10h em Brasília.
SEGUNDA_10H = datetime(2026, 9, 14, 10, 0, tzinfo=BRASILIA)

COMERCIAL = JanelaOperacional(
    dias=frozenset({0, 1, 2, 3, 4}),
    inicio=time(9, 0),
    fim=time(18, 0),
    fuso=BRASILIA,
)


def matriz(req_por_minuto: Any = 6, janela: Any = "padrao") -> Capabilities:
    bloco = (
        {"dias": [0, 1, 2, 3, 4], "inicio": "09:00", "fim": "18:00", "fuso": "UTC"}
        if janela == "padrao"
        else janela
    )
    return Capabilities(
        {
            "versao_esquema": VERSAO_ESQUEMA,
            "tribunais": {
                "TRT4": {
                    "status": "parcial",
                    "transporte": "in_page_fetch",
                    "vias": {"pdpj_api": "ok"},
                    "limites": {
                        "jobs_concorrentes_por_sessao": 1,
                        "req_por_minuto": req_por_minuto,
                        "limiar_download_sincrono_mb": 3.0,
                        "latencia_geracao_p50_s": None,
                        "latencia_geracao_p95_s": None,
                    },
                    "janela_operacional": bloco,
                    "adapter": "pdpj",
                    "testado_em": "2026-09-14",
                    "notas": "",
                }
            },
        }
    )


class Relogio:
    """Relógio controlado. Avança só quando o teste manda, ou quando o Ritmo dorme."""

    def __init__(self, inicio: datetime) -> None:
        self.agora = inicio
        self.dormido: list[float] = []

    def __call__(self) -> datetime:
        return self.agora

    async def espera(self, segundos: float) -> None:
        self.dormido.append(segundos)
        self.agora = self.agora + timedelta(seconds=segundos)


def ritmo(
    *,
    req_por_minuto: Any = 6,
    janela: JanelaOperacional = COMERCIAL,
    jitter: float = 0.0,
    inicio: datetime = SEGUNDA_10H,
    falhas_para_abrir: int = 3,
    aleatorio: Any = None,
) -> tuple[Ritmo, Relogio, Disjuntor]:
    relogio = Relogio(inicio)
    disjuntor = Disjuntor(falhas_para_abrir=falhas_para_abrir)
    return (
        Ritmo(
            matriz(req_por_minuto),
            disjuntor,
            janela=janela,
            jitter=jitter,
            clock=relogio,
            espera=relogio.espera,
            aleatorio=aleatorio if aleatorio is not None else (lambda: 0.5),
        ),
        relogio,
        disjuntor,
    )


# -- a taxa vem da matriz, nunca do código ----------------------------------


def test_intervalo_sai_da_matriz() -> None:
    """6 req/min na matriz vira 10 s entre requisições. O número não está no código."""
    assert ritmo(req_por_minuto=6)[0].intervalo_base("TRT4") == 10.0
    assert ritmo(req_por_minuto=30)[0].intervalo_base("TRT4") == 2.0


def test_tribunal_sem_taxa_medida_nao_ganha_ritmo_inventado() -> None:
    """Sem taxa declarada não há ritmo seguro, e escolher um aqui seria embutir limite."""
    with pytest.raises(PermanenteError, match="req_por_minuto"):
        ritmo(req_por_minuto=None)[0].intervalo_base("TRT4")


async def test_tribunal_fora_da_matriz_e_recusado() -> None:
    """Sigla ausente da matriz não ganha ritmo default — vira erro, como em `de()`."""
    with pytest.raises(CapabilitiesError):
        await ritmo()[0].aguardar("TRT9", "cred")


# -- espaçamento ------------------------------------------------------------


async def test_primeira_requisicao_nao_espera() -> None:
    r, relogio, _ = ritmo()
    await r.aguardar("TRT4", "cred")
    assert relogio.dormido == []


async def test_requisicoes_seguidas_sao_espacadas_pela_taxa() -> None:
    r, relogio, _ = ritmo(req_por_minuto=6)
    for _ in range(3):
        await r.aguardar("TRT4", "cred")
    assert relogio.dormido == [10.0, 10.0]


async def test_credenciais_distintas_nao_disputam_a_mesma_fila() -> None:
    """O escopo do limite é `(tribunal, credencial)`, como manda a governança."""
    r, relogio, _ = ritmo()
    await r.aguardar("TRT4", "cred-a")
    await r.aguardar("TRT4", "cred-b")
    assert relogio.dormido == []


async def test_jitter_torna_o_intervalo_irregular() -> None:
    """Cadência exata é mais notável num log do que a quantidade de requisições."""
    sorteios = iter([0.0, 1.0, 0.5])
    r, relogio, _ = ritmo(jitter=0.5, aleatorio=lambda: next(sorteios))
    for _ in range(3):
        await r.aguardar("TRT4", "cred")
    # Base 10 s, jitter 50%: sorteio 0.0 -> 5 s, 1.0 -> 15 s.
    assert relogio.dormido == [5.0, 15.0]


@pytest.mark.parametrize("jitter", [-0.1, 1.1, 2.0])
def test_jitter_fora_da_faixa_e_recusado(jitter: float) -> None:
    with pytest.raises(ValueError):
        ritmo(jitter=jitter)


# -- fora da janela é parada, não espera ------------------------------------


async def test_fora_do_expediente_nao_dorme_ate_amanha() -> None:
    """Dormir catorze horas segurando um slot é bug fantasiado de paciência."""
    noite = datetime(2026, 9, 14, 19, 30, tzinfo=BRASILIA)
    r, relogio, _ = ritmo(inicio=noite)
    with pytest.raises(ForaDaJanelaError) as erro:
        await r.aguardar("TRT4", "cred")
    assert relogio.dormido == []
    assert erro.value.proxima_abertura == datetime(2026, 9, 15, 9, 0, tzinfo=BRASILIA)


async def test_fim_de_semana_aponta_para_segunda() -> None:
    sabado = datetime(2026, 9, 12, 10, 0, tzinfo=BRASILIA)
    r, _, _ = ritmo(inicio=sabado)
    with pytest.raises(ForaDaJanelaError) as erro:
        await r.aguardar("TRT4", "cred")
    assert erro.value.proxima_abertura == datetime(2026, 9, 14, 9, 0, tzinfo=BRASILIA)


async def test_janela_que_fecha_durante_a_espera_interrompe() -> None:
    """A requisição não pode sair 30 segundos depois do expediente."""
    quase_fim = datetime(2026, 9, 14, 17, 59, 55, tzinfo=BRASILIA)
    r, relogio, _ = ritmo(req_por_minuto=6, inicio=quase_fim)
    await r.aguardar("TRT4", "cred")
    with pytest.raises(ForaDaJanelaError):
        await r.aguardar("TRT4", "cred")
    assert relogio.dormido == [10.0]


def test_fora_da_janela_e_transiente_nao_permanente() -> None:
    """Amanhã abre: quem trata o erro deve reagendar, não mandar para dead-letter."""
    erro = ForaDaJanelaError(SEGUNDA_10H)
    assert isinstance(erro, BloqueioError)
    assert isinstance(erro, TransienteError)


# -- a janela -------------------------------------------------------------


@pytest.mark.parametrize(
    "quando,aberta",
    [
        (datetime(2026, 9, 14, 8, 59, tzinfo=BRASILIA), False),
        (datetime(2026, 9, 14, 9, 0, tzinfo=BRASILIA), True),
        (datetime(2026, 9, 14, 17, 59, tzinfo=BRASILIA), True),
        (datetime(2026, 9, 14, 18, 0, tzinfo=BRASILIA), False),
        (datetime(2026, 9, 13, 10, 0, tzinfo=BRASILIA), False),
    ],
)
def test_bordas_da_janela(quando: datetime, aberta: bool) -> None:
    assert COMERCIAL.aberta_em(quando) is aberta


def test_janela_compara_no_fuso_declarado_e_nao_no_do_processo() -> None:
    """13h UTC é 10h em Brasília: dentro. A comparação não pode usar o fuso local."""
    assert COMERCIAL.aberta_em(datetime(2026, 9, 14, 13, 0, tzinfo=UTC))
    assert not COMERCIAL.aberta_em(datetime(2026, 9, 14, 23, 0, tzinfo=UTC))


def test_instante_sem_fuso_e_recusado() -> None:
    with pytest.raises(ValueError):
        COMERCIAL.aberta_em(datetime(2026, 9, 14, 10, 0))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"dias": frozenset()},
        {"dias": frozenset({7})},
        {"dias": frozenset({-1})},
        {"inicio": time(18, 0), "fim": time(9, 0)},
        {"inicio": time(9, 0), "fim": time(9, 0)},
    ],
)
def test_janela_invalida_e_recusada(kwargs: Any) -> None:
    base = {
        "dias": frozenset({0}),
        "inicio": time(9, 0),
        "fim": time(18, 0),
        "fuso": BRASILIA,
    }
    with pytest.raises(ValueError):
        JanelaOperacional(**{**base, **kwargs})


# -- disjuntor --------------------------------------------------------------


async def test_recusa_do_tribunal_abre_na_primeira() -> None:
    """Limite encontrado é limite respeitado, não um voto entre vários."""
    r, _, disjuntor = ritmo(falhas_para_abrir=5)
    r.registrar("TRT4", BloqueioError("429"))
    assert disjuntor.fase("TRT4") is Fase.ABERTO
    with pytest.raises(DisjuntorAbertoError):
        await r.aguardar("TRT4", "cred")


def test_falha_comum_so_abre_no_limite() -> None:
    r, _, disjuntor = ritmo(falhas_para_abrir=3)
    r.registrar("TRT4", TransienteError("timeout"))
    r.registrar("TRT4", TransienteError("timeout"))
    assert disjuntor.fase("TRT4") is Fase.FECHADO
    r.registrar("TRT4", TransienteError("timeout"))
    assert disjuntor.fase("TRT4") is Fase.ABERTO


def test_sucesso_zera_o_contador() -> None:
    r, _, disjuntor = ritmo(falhas_para_abrir=3)
    r.registrar("TRT4", TransienteError("timeout"))
    r.registrar("TRT4", TransienteError("timeout"))
    r.registrar("TRT4", None)
    r.registrar("TRT4", TransienteError("timeout"))
    assert disjuntor.fase("TRT4") is Fase.FECHADO


def test_disjuntor_nao_fecha_sozinho_nem_com_o_tempo() -> None:
    """Não há meio-aberto por temporizador: reabrir é decisão operacional.

    Um disjuntor que reabre por relógio transforma "limite respeitado" em "limite
    contornado com paciência".
    """
    r, relogio, disjuntor = ritmo()
    r.registrar("TRT4", BloqueioError("429"))
    relogio.agora = relogio.agora + timedelta(days=7)
    assert disjuntor.fase("TRT4") is Fase.ABERTO
    disjuntor.liberar("TRT4")
    assert disjuntor.fase("TRT4") is Fase.FECHADO


def test_disjuntor_e_por_tribunal_nunca_global() -> None:
    r, _, disjuntor = ritmo()
    r.registrar("TRT4", BloqueioError("429"))
    assert disjuntor.abertos() == ("TRT4",)
    assert disjuntor.fase("TRT2") is Fase.FECHADO


def test_nossas_proprias_recusas_nao_contam_contra_o_tribunal() -> None:
    """Fora da janela e disjuntor aberto são decisão nossa, não recusa dele."""
    r, _, disjuntor = ritmo(falhas_para_abrir=1)
    r.registrar("TRT4", ForaDaJanelaError(SEGUNDA_10H))
    r.registrar("TRT4", DisjuntorAbertoError("x"))
    assert disjuntor.fase("TRT4") is Fase.FECHADO


@pytest.mark.parametrize("limite", [0, -1])
def test_limite_de_falhas_invalido(limite: int) -> None:
    with pytest.raises(ValueError):
        Disjuntor(falhas_para_abrir=limite)


async def test_disjuntor_e_conferido_antes_de_qualquer_espera() -> None:
    """O barato e definitivo antes do caro: não dormir por tribunal já bloqueado."""
    r, relogio, _ = ritmo()
    await r.aguardar("TRT4", "cred")
    r.registrar("TRT4", BloqueioError("429"))
    with pytest.raises(DisjuntorAbertoError):
        await r.aguardar("TRT4", "cred")
    assert relogio.dormido == []


async def test_disjuntor_aberto_durante_a_espera_interrompe() -> None:
    """Se o disjuntor abrir enquanto a requisição dormia, ela não pode sair mesmo assim.

    Regressão: `aguardar` só conferia o disjuntor antes de dormir. Uma recusa do
    tribunal chegando durante o sono (via outra chamada) não impedia a saída.
    """
    r, relogio, disjuntor = ritmo(req_por_minuto=6)
    await r.aguardar("TRT4", "cred")  # reserva o próximo slot, não dorme

    async def espera_e_recusa(segundos: float) -> None:
        await Relogio.espera(relogio, segundos)
        disjuntor.registrar_recusa("TRT4")

    r._espera = espera_e_recusa  # type: ignore[attr-defined]
    with pytest.raises(DisjuntorAbertoError):
        await r.aguardar("TRT4", "cred")


def test_repr_do_ritmo_nao_revela_credencial() -> None:
    r, _, _ = ritmo()
    assert "cred" not in repr(r)


# -- a janela vem da matriz -------------------------------------------------


def test_janela_vem_da_matriz_quando_nao_ha_override() -> None:
    """A matriz é a fonte de verdade (ADR 009); o override é exceção, não conveniência."""
    r = Ritmo(matriz(), Disjuntor(falhas_para_abrir=3), jitter=0.0)
    janela = r.janela_de("TRT4")
    assert janela.dias == frozenset({0, 1, 2, 3, 4})
    assert janela.inicio == time(9, 0)
    assert janela.fim == time(18, 0)


def test_tribunal_sem_janela_declarada_nao_ganha_horario_inventado() -> None:
    """Sem janela declarada não há hora aceitável para incomodar o tribunal."""
    r = Ritmo(matriz(janela=None), Disjuntor(falhas_para_abrir=3), jitter=0.0)
    with pytest.raises(PermanenteError, match="janela_operacional"):
        r.janela_de("TRT4")


def test_fuso_inexistente_falha_sem_ecoar_o_valor() -> None:
    ruim = {
        "dias": [0],
        "inicio": "09:00",
        "fim": "18:00",
        "fuso": "Marte/Olympus_Mons",
    }
    r = Ritmo(matriz(janela=ruim), Disjuntor(falhas_para_abrir=3), jitter=0.0)
    with pytest.raises(PermanenteError) as erro:
        r.janela_de("TRT4")
    assert "Marte" not in str(erro.value)


def test_janela_e_resolvida_uma_vez_por_tribunal() -> None:
    r = Ritmo(matriz(), Disjuntor(falhas_para_abrir=3), jitter=0.0)
    assert r.janela_de("TRT4") is r.janela_de("TRT4")


@pytest.mark.parametrize(
    "janela",
    [
        {"dias": [], "inicio": "09:00", "fim": "18:00", "fuso": "UTC"},
        {"dias": [7], "inicio": "09:00", "fim": "18:00", "fuso": "UTC"},
        {"dias": [True], "inicio": "09:00", "fim": "18:00", "fuso": "UTC"},
        {"dias": [0], "inicio": "18:00", "fim": "09:00", "fuso": "UTC"},
        {"dias": [0], "inicio": "nove", "fim": "18:00", "fuso": "UTC"},
        {"dias": [0], "inicio": "09:00", "fim": "18:00", "fuso": ""},
        {"dias": [0], "inicio": "09:00", "fim": "18:00"},
        "nao e mapeamento",
    ],
)
def test_janela_invalida_na_matriz_e_recusada_na_leitura(janela: Any) -> None:
    with pytest.raises(CapabilitiesError):
        matriz(janela=janela)


# -- contrato com o dado de produção ----------------------------------------


def test_a_matriz_real_declara_janela_utilizavel_para_os_24() -> None:
    """Se alguém quebrar a janela na matriz, o erro aparece aqui — não em produção."""
    real = Capabilities.de_arquivo(MATRIZ_REAL)
    ritmo_real = Ritmo(real, Disjuntor(falhas_para_abrir=3), jitter=0.0)
    for sigla in real.siglas():
        janela = ritmo_real.janela_de(sigla)
        # Horário comercial, dias úteis: o combinado da ADR 009.
        assert janela.dias == frozenset({0, 1, 2, 3, 4})
        assert not janela.aberta_em(datetime(2026, 9, 12, 10, 0, tzinfo=BRASILIA))
        assert janela.aberta_em(datetime(2026, 9, 14, 10, 0, tzinfo=BRASILIA))


def test_a_matriz_real_poe_o_trt4_no_transporte_da_adr_009() -> None:
    real = Capabilities.de_arquivo(MATRIZ_REAL)
    assert real.de("TRT4").transporte.value == "in_page_fetch"


# -- terminais legítimos não são falha (governanca-volume.md) ----------------


@pytest.mark.parametrize(
    "erro",
    [SigiloError("segredo de justica"), InexistenteError("peca nao existe")],
)
def test_terminal_legitimo_nao_alimenta_o_disjuntor(erro: Exception) -> None:
    """`SIGILOSO` e `INEXISTENTE` são respostas CERTAS do tribunal, não falhas dele.

    `governanca-volume.md`: "SIGILOSO e INEXISTENTE não podem ser convertidos em erro
    para fins de volume". Sem esta distinção, um lote com três processos sigilosos
    abriria o disjuntor do tribunal inteiro — e o tribunal não fez nada de errado.
    """
    r, _, disjuntor = ritmo(falhas_para_abrir=2)
    r.registrar("TRT4", erro)
    r.registrar("TRT4", erro)
    r.registrar("TRT4", erro)
    assert disjuntor.fase("TRT4") is Fase.FECHADO


def test_terminal_legitimo_zera_o_contador_como_sucesso() -> None:
    """Interação bem-sucedida: o tribunal respondeu, e respondeu corretamente."""
    r, _, disjuntor = ritmo(falhas_para_abrir=2)
    r.registrar("TRT4", TransienteError("timeout"))
    r.registrar("TRT4", SigiloError("segredo de justica"))
    r.registrar("TRT4", TransienteError("timeout"))
    assert disjuntor.fase("TRT4") is Fase.FECHADO


def test_permanente_comum_continua_alimentando_o_disjuntor() -> None:
    """A isenção é só dos dois terminais legítimos, não de todo `PermanenteError`."""
    r, _, disjuntor = ritmo(falhas_para_abrir=2)
    r.registrar("TRT4", PermanenteError("resposta inesperada"))
    r.registrar("TRT4", PermanenteError("resposta inesperada"))
    assert disjuntor.fase("TRT4") is Fase.ABERTO
