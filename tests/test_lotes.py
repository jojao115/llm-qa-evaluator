"""Capacidade da fila de lote, sem ligar os workers (nada é processado)."""

import pytest
from pydantic import ValidationError

from app.avaliador import Avaliador
from app.config import Config
from app.lotes import CapacidadeEsgotada, GerenciadorLotes
from app.models import PedidoAvaliacao
from app.rubricas import RegistroRubricas
from tests.conftest import CONVERSA, JuizRoteirizado

PEDIDO = PedidoAvaliacao(rubrica_id="suporte_provedor_v1", conversa=CONVERSA)


def _gerenciador(rubricas: RegistroRubricas, guardar: int, fila_max: int) -> GerenciadorLotes:
    avaliador = Avaliador(JuizRoteirizado(ValueError("não deveria rodar")), rubricas)
    return GerenciadorLotes(avaliador, concorrencia=1, guardar=guardar, fila_max=fila_max)


async def test_recusa_lote_que_nao_cabe_na_fila(rubricas: RegistroRubricas) -> None:
    g = _gerenciador(rubricas, guardar=10, fila_max=3)
    g.criar([PEDIDO, PEDIDO])
    with pytest.raises(CapacidadeEsgotada, match="fila"):
        g.criar([PEDIDO, PEDIDO])  # 2 + 2 > 3: recusa o lote inteiro, sem enfileirar metade
    assert g._fila.qsize() == 2


async def test_nunca_descarta_lote_em_andamento(rubricas: RegistroRubricas) -> None:
    g = _gerenciador(rubricas, guardar=2, fila_max=100)
    a = g.criar([PEDIDO])
    b = g.criar([PEDIDO])
    with pytest.raises(CapacidadeEsgotada, match="em andamento"):
        g.criar([PEDIDO])
    assert g.obter(a.id) is not None
    assert g.obter(b.id) is not None


async def test_descarta_o_concluido_mais_antigo(rubricas: RegistroRubricas) -> None:
    g = _gerenciador(rubricas, guardar=2, fila_max=100)
    a = g.criar([PEDIDO])
    b = g.criar([PEDIDO])
    b.status = "concluido"
    c = g.criar([PEDIDO])
    assert g.obter(a.id) is not None  # em andamento, fica
    assert g.obter(b.id) is None
    assert g.obter(c.id) is not None


@pytest.mark.parametrize(
    "campo", ["lote_concorrencia", "lote_max_conversas", "lote_fila_max", "max_tentativas"]
)
def test_config_recusa_zero(campo: str) -> None:
    with pytest.raises(ValidationError):
        Config(**{campo: 0})  # type: ignore[arg-type]
