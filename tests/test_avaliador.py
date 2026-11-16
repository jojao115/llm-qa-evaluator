from collections.abc import Callable

import pytest

from app.avaliador import AvaliacaoFalhou, Avaliador, validar_resposta
from app.juizes import ErroJuiz
from app.models import Evidencia, PedidoAvaliacao, RespostaJuiz
from app.rubricas import RegistroRubricas, Rubrica
from tests.conftest import CONVERSA, JuizRoteirizado

Fabrica = Callable[..., RespostaJuiz]
PEDIDO = PedidoAvaliacao(rubrica_id="suporte_provedor_v1", conversa=CONVERSA)


def test_resposta_valida_passa(rubrica: Rubrica, resposta_valida: Fabrica) -> None:
    assert validar_resposta(resposta_valida(), rubrica, CONVERSA) == []


def test_trecho_com_espaco_e_maiuscula_diferentes_ainda_vale(
    rubrica: Rubrica, resposta_valida: Fabrica
) -> None:
    r = resposta_valida()
    r.criterios[0].evidencias = [Evidencia(mensagem=1, trecho="aqui  É A carla")]
    assert validar_resposta(r, rubrica, CONVERSA) == []


def test_aponta_evidencia_inventada(rubrica: Rubrica, resposta_valida: Fabrica) -> None:
    r = resposta_valida()
    r.criterios[0].evidencias = [
        Evidencia(mensagem=1, trecho="Aqui é o Pedro"),
        Evidencia(mensagem=9, trecho="qualquer"),
    ]
    problemas = validar_resposta(r, rubrica, CONVERSA)
    assert "saudacao: o trecho 'Aqui é o Pedro' não está na mensagem 1" in problemas
    assert "saudacao: a evidência aponta a mensagem 9, que não existe" in problemas


def test_aponta_criterio_faltando_repetido_ou_desconhecido(
    rubrica: Rubrica, resposta_valida: Fabrica
) -> None:
    r = resposta_valida()
    r.criterios[1] = r.criterios[0].model_copy()
    r.criterios[2].criterio_id = "inventado"
    problemas = validar_resposta(r, rubrica, CONVERSA)
    assert "critério desconhecido: inventado" in problemas
    assert "critérios repetidos: saudacao" in problemas
    assert "faltam os critérios: identificacao_titular, entendimento" in problemas


def test_nao_se_aplica_em_criterio_que_nao_aceita(
    rubrica: Rubrica, resposta_valida: Fabrica
) -> None:
    r = resposta_valida(protocolo="nao_se_aplica", retencao="nao_se_aplica")
    assert validar_resposta(r, rubrica, CONVERSA) == [
        "protocolo: este critério não aceita nao_se_aplica"
    ]


async def test_avaliacao_na_primeira_tentativa(
    rubricas: RegistroRubricas, resposta_valida: Fabrica
) -> None:
    juiz = JuizRoteirizado(resposta_valida(retencao="nao_se_aplica"))
    r = await Avaliador(juiz, rubricas).avaliar(PEDIDO)
    assert r.nota == 100.0
    assert r.meta.tentativas == 1
    assert r.meta.modelo == "roteiro-1"
    assert [c.id for c in r.criterios][:2] == ["saudacao", "identificacao_titular"]
    assert r.criterios[0].evidencias[0].trecho == "Aqui é a Carla"


async def test_refaz_quando_a_validacao_recusa_e_soma_o_uso(
    rubricas: RegistroRubricas, resposta_valida: Fabrica
) -> None:
    ruim = resposta_valida()
    ruim.criterios[0].evidencias = [Evidencia(mensagem=1, trecho="inventado")]
    juiz = JuizRoteirizado(ruim, resposta_valida())
    r = await Avaliador(juiz, rubricas).avaliar(PEDIDO)
    assert r.meta.tentativas == 2
    assert r.meta.tokens_entrada == 200
    # A segunda chamada leva o motivo da recusa para o modelo corrigir.
    assert juiz.chamadas[0] == []
    assert juiz.chamadas[1] == ["saudacao: o trecho 'inventado' não está na mensagem 1"]


async def test_desiste_depois_do_limite(
    rubricas: RegistroRubricas, resposta_valida: Fabrica
) -> None:
    ruim = resposta_valida(protocolo="nao_se_aplica")
    juiz = JuizRoteirizado(ruim)
    with pytest.raises(AvaliacaoFalhou, match="em 2 tentativas"):
        await Avaliador(juiz, rubricas, max_tentativas=2).avaliar(PEDIDO)
    assert len(juiz.chamadas) == 2


async def test_erro_do_juiz_vira_falha_da_avaliacao(rubricas: RegistroRubricas) -> None:
    juiz = JuizRoteirizado(ErroJuiz("o modelo recusou avaliar esta conversa"))
    with pytest.raises(AvaliacaoFalhou, match="recusou"):
        await Avaliador(juiz, rubricas).avaliar(PEDIDO)
    assert len(juiz.chamadas) == 1  # erro do juiz não gasta nova tentativa


async def test_falha_critica_aparece_no_resultado(
    rubricas: RegistroRubricas, resposta_valida: Fabrica
) -> None:
    juiz = JuizRoteirizado(resposta_valida(identificacao_titular="nao_atende"))
    r = await Avaliador(juiz, rubricas).avaliar(PEDIDO)
    assert r.nota == 0.0
    assert r.nota_sem_criticos == 90.0
    assert r.falhas_criticas == ["identificacao_titular"]


def test_trecho_vazio_nao_comprova_nada(rubrica: Rubrica, resposta_valida: Fabrica) -> None:
    r = resposta_valida()
    r.criterios[0].evidencias = [Evidencia(mensagem=1, trecho="   ")]
    assert validar_resposta(r, rubrica, CONVERSA) == ["saudacao: evidência com trecho vazio"]
