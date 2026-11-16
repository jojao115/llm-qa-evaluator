from pathlib import Path

import pytest

from app.avaliador import validar_resposta
from app.juizes import JuizSimulado
from app.models import Mensagem
from app.rubricas import RegistroRubricas, Rubrica
from evals.run_evals import DATASET, carregar
from tests.conftest import CONVERSA


def _niveis(resposta) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return {v.criterio_id: v.nivel for v in resposta.criterios}


async def test_conversa_boa(rubrica: Rubrica) -> None:
    j = await JuizSimulado().julgar(rubrica, CONVERSA, [])
    n = _niveis(j.resposta)
    assert n["saudacao"] == "atende"
    assert n["identificacao_titular"] == "atende"
    assert n["protocolo"] == "atende"
    assert n["encerramento"] == "atende"
    assert n["retencao"] == "nao_se_aplica"
    assert n["diagnostico"] == "nao_se_aplica"
    assert j.uso.custo_usd == 0.0
    assert validar_resposta(j.resposta, rubrica, CONVERSA) == []


async def test_conversa_ruim(rubrica: Rubrica) -> None:
    conversa = [
        Mensagem(autor="cliente", texto="quero cancelar minha internet"),
        Mensagem(autor="atendente", texto="Ok, cancelado."),
    ]
    n = _niveis((await JuizSimulado().julgar(rubrica, conversa, [])).resposta)
    assert n["saudacao"] == "nao_atende"
    assert n["identificacao_titular"] == "nao_atende"
    assert n["retencao"] == "nao_atende"
    assert n["protocolo"] == "nao_atende"


@pytest.mark.skipif(not Path(DATASET).exists(), reason="sem dataset")
async def test_simulado_sempre_passa_na_validacao(rubricas: RegistroRubricas) -> None:
    # As evidências do simulado também precisam existir na conversa.
    for ex in carregar(DATASET, rubricas):
        rubrica = rubricas.obter(ex.rubrica)
        j = await JuizSimulado().julgar(rubrica, ex.conversa, [])
        assert validar_resposta(j.resposta, rubrica, ex.conversa) == [], ex.id
