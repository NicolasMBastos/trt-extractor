"""Ritmo de operação: quando a próxima requisição pode sair. ADR 009.

O dono do projeto decidiu em 2026-09-14: transporte de dentro da página autenticada,
**horário comercial, volume baixo**. Este módulo é o que torna essa frase executável.

## Por que o ritmo é o controle principal, e não um detalhe

A medição de 2026-09-14 mostrou que cada requisição carrega um JWT com nome, CPF, e-mail
e papéis do titular. Ou seja: **não há anonimato, e não se busca nenhum**. O servidor sabe
exatamente quem está pedindo.

Isso reposiciona o risco. Ele não é "ser detectado"; é um auditor perguntando por que uma
credencial abriu dez mil processos numa tarde. Contra esse risco, fingerprint não ajuda e
mecanismo de transporte quase não importa — **só o ritmo importa**. Por isso esta camada
é obrigatória no caminho de qualquer requisição de aquisição, e não um enfeite opcional.

## Nenhum número de POLÍTICA neste arquivo

Taxa, janela e limiar de falha são política, e política não mora em código. Limites
estruturais de laço (até onde vasculhar um calendário) não são política e ficam aqui.
Mesma regra de `capabilities.py`, pela mesma razão (`docs/execucao/governanca-volume.md`):

> "O rate limiter futuro deve ler a matriz em runtime; não pode embutir limites, exceções
> ou valores de fallback próprios."

A taxa **e a janela** vêm de `capabilities.yaml`, por tribunal. O limiar do disjuntor vem
do chamador, **sem default**: a governança diz que esse número é "parâmetro operacional a
definir e registrar antes da implementação". Um default aqui seria eu decidindo no lugar
de quem responde pela credencial.

## Duas decisões que contrariam o manual de circuit breaker

**1. Fora da janela não é espera, é parada.** Um job que chega às 19h não dorme até as 9h
segurando um slot. Ele recebe `ForaDaJanelaError`, com o instante da próxima abertura, e
volta para a fila. Dormir catorze horas dentro de uma requisição é bug fantasiado de
paciência.

**2. O disjuntor não fecha sozinho.** Não há meio-aberto por temporizador. A governança
exige "decisão operacional para a próxima tentativa", e o corolário já exercitado no
FALCÃO em 2026-09-08 foi: no `429`, a execução **parou**. Um disjuntor que reabre por
relógio transforma "limite respeitado" em "limite contornado com paciência" — que é
exatamente a postura que este projeto não tem. Reabrir é ato humano: `liberar()`.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .capabilities import Capabilities, Capacidade
from .contracts import (
    BloqueioError,
    InexistenteError,
    PermanenteError,
    SigiloError,
)

Clock = Callable[[], datetime]
Espera = Callable[[float], Awaitable[None]]
Aleatorio = Callable[[], float]

#: Teto de dias vasculhados ao procurar a próxima abertura: uma semana inteira mais um
#: dia de folga. Janela que não abre em sete dias é configuração errada, não espera longa.
_DIAS_ATE_DESISTIR = 8


class ForaDaJanelaError(BloqueioError):
    """Fora do horário de operação. Transiente por natureza: amanhã abre.

    Carrega `proxima_abertura` para o orquestrador agendar em vez de repetir em laço.
    """

    def __init__(self, proxima_abertura: datetime) -> None:
        super().__init__("fora da janela operacional")
        self.proxima_abertura = proxima_abertura


class DisjuntorAbertoError(BloqueioError):
    """O tribunal recusou e o disjuntor abriu. Só reabre por decisão humana."""

    def __init__(self, motivo: str) -> None:
        super().__init__(f"disjuntor aberto: {motivo}")
        self.motivo = motivo


@dataclass(frozen=True, slots=True)
class JanelaOperacional:
    """Horário em que é aceitável falar com o tribunal.

    Sem valores padrão de propósito. "Horário comercial" não é um fato universal: muda
    por tribunal, por fuso e por combinado interno. Quem opera declara.
    """

    #: 0 = segunda … 6 = domingo, como `datetime.weekday()`.
    dias: frozenset[int]
    inicio: time
    fim: time
    fuso: tzinfo

    def __post_init__(self) -> None:
        if not self.dias:
            raise ValueError("janela sem nenhum dia é janela fechada; declare os dias")
        if not self.dias <= set(range(7)):
            raise ValueError("dias devem estar entre 0 (segunda) e 6 (domingo)")
        if self.inicio >= self.fim:
            # Janela que cruza a meia-noite não é horário comercial; se um dia for
            # preciso, é caso novo e merece decisão, não um `if` escondido aqui.
            raise ValueError("inicio deve ser anterior a fim; janela não cruza o dia")

    @classmethod
    def da_matriz(cls, capacidade: Capacidade) -> JanelaOperacional:
        """Constrói a janela a partir do que a matriz declara para este tribunal.

        A matriz é a fonte de verdade (ADR 009). Ausência **não** vira horário padrão:
        um tribunal sem janela declarada não tem hora aceitável para ser incomodado, e
        inventar uma aqui seria exatamente o que a governança proíbe.
        """
        config = capacidade.janela
        if config is None:
            raise PermanenteError(
                f"{capacidade.tribunal} sem janela_operacional na matriz; "
                "o ritmo não infere horário"
            )
        try:
            fuso = ZoneInfo(config.fuso)
        except (ZoneInfoNotFoundError, ValueError):
            # Sem ecoar o nome recebido: a matriz é editada por humanos que já sabem o
            # que escreveram, e mensagem de erro não é lugar de repetir configuração.
            raise PermanenteError(
                f"{capacidade.tribunal}: fuso da janela não existe nesta máquina"
            ) from None
        return cls(dias=config.dias, inicio=config.inicio, fim=config.fim, fuso=fuso)

    def aberta_em(self, quando: datetime) -> bool:
        if quando.utcoffset() is None:
            raise ValueError("instante sem fuso não pode ser comparado à janela")
        local = quando.astimezone(self.fuso)
        return local.weekday() in self.dias and self.inicio <= local.time() < self.fim

    def proxima_abertura(self, quando: datetime) -> datetime:
        """Primeiro instante de abertura a partir de `quando`. `quando` se já aberta."""
        if self.aberta_em(quando):
            return quando
        local = quando.astimezone(self.fuso)
        for salto in range(_DIAS_ATE_DESISTIR):
            dia: date = (local + timedelta(days=salto)).date()
            candidato = datetime.combine(dia, self.inicio, tzinfo=self.fuso)
            if candidato > local and candidato.weekday() in self.dias:
                return candidato
        # Inalcançável com dias não vazios, mas explodir é melhor que devolver algo
        # plausível e errado para um agendador.
        raise PermanenteError("janela operacional não abre nos próximos dias")


class Fase(str, Enum):  # noqa: UP042
    FECHADO = "fechado"
    ABERTO = "aberto"


@dataclass
class _Estado:
    """Estado de tráfego de uma chave `(tribunal, credencial)`."""

    proximo_permitido: datetime | None = None


class Disjuntor:
    """Por tribunal, nunca global. Abre na recusa e **não** fecha sozinho.

    `falhas_para_abrir` é obrigatório e sem default: a governança manda que o critério
    numérico seja decidido junto da implementação, com evidência autorizada.

    Uma recusa explícita do tribunal (`429`, `403` — que chegam como `BloqueioError`)
    abre **na primeira ocorrência**, independente do contador. Limite encontrado é
    limite respeitado, não um voto entre vários.
    """

    def __init__(self, *, falhas_para_abrir: int) -> None:
        if falhas_para_abrir < 1:
            raise ValueError("falhas_para_abrir deve ser >= 1")
        self._limite = falhas_para_abrir
        self._falhas: dict[str, int] = {}
        self._abertos: dict[str, str] = {}

    def fase(self, tribunal: str) -> Fase:
        return Fase.ABERTO if tribunal in self._abertos else Fase.FECHADO

    def conferir(self, tribunal: str) -> None:
        motivo = self._abertos.get(tribunal)
        if motivo is not None:
            raise DisjuntorAbertoError(motivo)

    def registrar_sucesso(self, tribunal: str) -> None:
        """Sucesso zera o contador — mas não reabre um disjuntor aberto: para chegar
        aqui com ele aberto seria preciso ter furado o `conferir`."""
        self._falhas.pop(tribunal, None)

    def registrar_recusa(self, tribunal: str) -> None:
        """Recusa explícita do tribunal. Abre imediatamente."""
        self._abertos[tribunal] = "tribunal recusou a requisicao"
        self._falhas.pop(tribunal, None)

    def registrar_falha(self, tribunal: str) -> None:
        """Falha transiente comum (timeout, 5xx). Abre ao atingir o limite."""
        contagem = self._falhas.get(tribunal, 0) + 1
        self._falhas[tribunal] = contagem
        if contagem >= self._limite:
            self._abertos[tribunal] = "falhas consecutivas acima do limite"
            self._falhas.pop(tribunal, None)

    def liberar(self, tribunal: str) -> None:
        """Reabertura por decisão operacional. Não existe caminho automático."""
        self._abertos.pop(tribunal, None)
        self._falhas.pop(tribunal, None)

    def abertos(self) -> tuple[str, ...]:
        return tuple(sorted(self._abertos))


class Ritmo:
    """Porta única por onde toda requisição de aquisição passa antes de sair.

    Ordem das checagens, e ela importa: disjuntor, janela, e só então espera de taxa.
    Verificar o barato e definitivo antes do caro evita dormir por um tribunal que já
    está bloqueado.
    """

    def __init__(
        self,
        capabilities: Capabilities,
        disjuntor: Disjuntor,
        *,
        janela: JanelaOperacional | None = None,
        jitter: float,
        clock: Clock = lambda: datetime.now(tz=None).astimezone(),
        espera: Espera = asyncio.sleep,
        aleatorio: Aleatorio = random.random,
    ) -> None:
        if not 0.0 <= jitter <= 1.0:
            raise ValueError("jitter é uma fração do intervalo, entre 0 e 1")
        self._capabilities = capabilities
        self._janela_fixa = janela
        self._janelas: dict[str, JanelaOperacional] = {}
        self._disjuntor = disjuntor
        self._jitter = jitter
        self._clock = clock
        self._espera = espera
        self._aleatorio = aleatorio
        self._estados: dict[tuple[str, str], _Estado] = {}
        self._lock = asyncio.Lock()

    def janela_de(self, tribunal: str) -> JanelaOperacional:
        """A janela deste tribunal. Vem da matriz, salvo override explícito.

        O override existe para teste e para operação excepcional autorizada — não para
        conveniência. Sem ele, quem manda é `capabilities.yaml`.
        """
        if self._janela_fixa is not None:
            return self._janela_fixa
        cacheada = self._janelas.get(tribunal)
        if cacheada is None:
            cacheada = JanelaOperacional.da_matriz(self._capabilities.de(tribunal))
            self._janelas[tribunal] = cacheada
        return cacheada

    def intervalo_base(self, tribunal: str) -> float:
        """Segundos entre requisições, derivados da taxa **da matriz**.

        Recusa tribunal sem `req_por_minuto` medido: sem taxa declarada não há ritmo
        seguro, e escolher um aqui seria embutir limite — o que a governança proíbe.
        """
        limites = self._capabilities.de(tribunal).limites
        if limites.req_por_minuto is None:
            raise PermanenteError(
                f"{tribunal} sem req_por_minuto na matriz; ritmo não pode ser inferido"
            )
        return 60.0 / limites.req_por_minuto

    def _com_jitter(self, base: float) -> float:
        """Intervalo irregular. Ritmo humano não é metrônomo, e uma cadência exata é
        mais notável num log do que a própria quantidade de requisições."""
        if self._jitter == 0.0:
            return base
        fator = 1.0 + self._jitter * (2.0 * self._aleatorio() - 1.0)
        return base * fator

    async def aguardar(self, tribunal: str, credencial_id: str) -> None:
        """Bloqueia até ser aceitável emitir a próxima requisição desta chave.

        Levanta em vez de esperar quando esperar seria errado: disjuntor aberto é
        parada, e fora da janela é reagendamento — nenhum dos dois é "dorme mais".
        """
        self._disjuntor.conferir(tribunal)
        janela = self.janela_de(tribunal)
        agora = self._clock()
        if not janela.aberta_em(agora):
            raise ForaDaJanelaError(janela.proxima_abertura(agora))

        base = self.intervalo_base(tribunal)
        chave = (tribunal, credencial_id)
        async with self._lock:
            estado = self._estados.setdefault(chave, _Estado())
            agora = self._clock()
            alvo = estado.proximo_permitido
            if alvo is None or alvo <= agora:
                partida, dormir = agora, 0.0
            else:
                partida, dormir = alvo, (alvo - agora).total_seconds()
            # A reserva do próximo slot acontece com o lock ainda tomado: dois
            # chamadores concorrentes não podem reservar o mesmo instante e sair juntos.
            intervalo = self._com_jitter(base)
            estado.proximo_permitido = partida + timedelta(seconds=intervalo)
        if dormir > 0:
            await self._espera(dormir)
            # O disjuntor pode ter aberto enquanto se esperava (outra chamada recebeu
            # recusa do tribunal nesse intervalo). Reconferir evita a requisição que sai
            # depois que o tribunal já recusou.
            self._disjuntor.conferir(tribunal)
            # A janela pode ter fechado enquanto se esperava. Reconferir é barato e
            # evita a requisição que sai 30 segundos depois do expediente.
            if not janela.aberta_em(self._clock()):
                raise ForaDaJanelaError(janela.proxima_abertura(self._clock()))

    def registrar(self, tribunal: str, erro: BaseException | None) -> None:
        """Resultado de uma requisição, para alimentar o disjuntor.

        `BloqueioError` é recusa explícita do tribunal e abre na hora. Outras exceções
        contam para o limite. Sucesso zera o contador.
        """
        if erro is None:
            self._disjuntor.registrar_sucesso(tribunal)
        elif isinstance(erro, SigiloError | InexistenteError):
            # Terminais legítimos: o tribunal respondeu, e respondeu CERTO. Segredo de
            # justiça não é defeito dele, e peça inexistente também não.
            #
            # `governanca-volume.md`: "SIGILOSO e INEXISTENTE não podem ser convertidos
            # em erro para fins de volume". Sem esta cláusula, um lote com poucos
            # processos sigilosos abriria o disjuntor do tribunal inteiro — e pararia a
            # operação por causa de respostas corretas. Conta como sucesso porque é o
            # que foi: uma interação que deu certo.
            self._disjuntor.registrar_sucesso(tribunal)
        elif isinstance(erro, ForaDaJanelaError | DisjuntorAbertoError):
            # Decisão nossa, não recusa do tribunal: não conta contra ele.
            return
        elif isinstance(erro, BloqueioError):
            self._disjuntor.registrar_recusa(tribunal)
        else:
            self._disjuntor.registrar_falha(tribunal)

    def __repr__(self) -> str:
        return f"Ritmo(jitter={self._jitter!r}, abertos={self._disjuntor.abertos()!r})"
