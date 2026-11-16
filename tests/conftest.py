from collections.abc import Callable

import pytest

from app.config import PASTA_RUBRICAS_PADRAO
from app.juizes import ErroJuiz, Julgamento, Uso
from app.models import Evidencia, Mensagem, Nivel, RespostaJuiz, VeredictoCriterio
from app.rubricas import RegistroRubricas, Rubrica

CONVERSA = [
    Mensagem(autor="cliente", texto="Boa tarde, quero a segunda via do boleto"),
    Mensagem(
        autor="atendente",
        texto="Boa tarde! Aqui é a Carla, da Alfa Fibra. Pode me passar o CPF do titular?",
    ),
    Mensagem(autor="cliente", texto="CPF final 4521"),
    Mensagem(
        autor="atendente",
        texto="Obrigada! Enviei o boleto no seu e-mail. Protocolo 2026111400123. "
        "Posso ajudar em algo mais?",
    ),
    Mensagem(autor="cliente", texto="Não, obrigado"),
]


@pytest.fixture
def rubricas() -> RegistroRubricas:
    return RegistroRubricas(PASTA_RUBRICAS_PADRAO)


@pytest.fixture
def rubrica(rubricas: RegistroRubricas) -> Rubrica:
    return rubricas.obter("suporte_provedor_v1")


def montar_resposta(rubrica: Rubrica, **niveis: Nivel) -> RespostaJuiz:
    """Resposta válida: "atende" em tudo, menos o que vier em `niveis`."""
    return RespostaJuiz(
        criterios=[
            VeredictoCriterio(
                criterio_id=c.id,
                nivel=niveis.get(c.id, "atende"),
                justificativa=f"justificativa de {c.id}",
                evidencias=(
                    [Evidencia(mensagem=1, trecho="Aqui é a Carla")] if c.id == "saudacao" else []
                ),
            )
            for c in rubrica.criterios
        ],
        resumo="Atendimento ok.",
    )


class JuizRoteirizado:
    """Juiz falso que devolve, em ordem, o que o teste mandar (resposta ou exceção)."""

    provedor = "teste"
    modelo = "roteiro"

    def __init__(self, *passos: RespostaJuiz | Exception) -> None:
        self.passos = list(passos)
        self.chamadas: list[list[str]] = []

    async def julgar(
        self, rubrica: Rubrica, conversa: list[Mensagem], correcoes: list[str]
    ) -> Julgamento:
        self.chamadas.append(list(correcoes))
        passo = self.passos.pop(0) if len(self.passos) > 1 else self.passos[0]
        if isinstance(passo, Exception):
            raise passo
        return Julgamento(
            resposta=passo, modelo="roteiro-1", uso=Uso(tokens_entrada=100, tokens_saida=50)
        )


@pytest.fixture
def resposta_valida(rubrica: Rubrica) -> Callable[..., RespostaJuiz]:
    def fazer(**niveis: Nivel) -> RespostaJuiz:
        return montar_resposta(rubrica, **niveis)

    return fazer


__all__ = ["CONVERSA", "ErroJuiz", "JuizRoteirizado", "montar_resposta"]
