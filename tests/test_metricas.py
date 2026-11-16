import pytest

from evals.metricas import (
    deteccao_critica,
    distancia,
    kappa_cohen,
    matriz_confusao,
    pearson,
    resumir_criterio,
)


def test_kappa() -> None:
    assert kappa_cohen(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0
    # Concordância observada 0,5, esperada 0,5 → 0.
    assert kappa_cohen(["a", "a", "b", "b"], ["a", "b", "a", "b"]) == 0.0
    # Exemplo clássico: 20 pares, 15 iguais.
    a = ["s"] * 10 + ["n"] * 10
    b = ["s"] * 8 + ["n"] * 2 + ["s"] * 3 + ["n"] * 7
    assert kappa_cohen(a, b) == pytest.approx(0.5)
    assert kappa_cohen([], []) is None
    assert kappa_cohen(["a", "a"], ["a", "a"]) is None  # um rótulo só: indefinido


def test_pearson() -> None:
    assert pearson([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert pearson([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    assert pearson([1, 1, 1], [1, 2, 3]) is None
    assert pearson([1], [1]) is None


def test_distancia() -> None:
    assert distancia("atende", "atende") == 0
    assert distancia("atende", "parcial") == 1
    assert distancia("atende", "nao_atende") == 2
    assert distancia("nao_se_aplica", "atende") is None
    assert distancia("nao_se_aplica", "nao_se_aplica") == 0


def test_resumo_por_criterio() -> None:
    r = resumir_criterio(
        "x",
        ["atende", "parcial", "nao_atende", "nao_se_aplica"],
        ["atende", "atende", "atende", "atende"],
    )
    assert r.pares == 4
    assert r.acerto == 0.25
    assert r.ate_um_nivel == 0.5


def test_deteccao_critica() -> None:
    d = deteccao_critica([True, True, False, False], [True, False, True, False])
    assert (d.verdadeiros, d.perdidas, d.falsos_alarmes) == (1, 1, 1)
    assert d.precisao == 0.5
    assert d.revocacao == 0.5
    vazio = deteccao_critica([False], [False])
    assert vazio.precisao is None
    assert vazio.revocacao is None


def test_matriz() -> None:
    m = matriz_confusao(["atende", "atende", "parcial"], ["atende", "parcial", "parcial"])
    assert m["atende"]["atende"] == 1
    assert m["atende"]["parcial"] == 1
    assert m["parcial"]["parcial"] == 1
    assert m["nao_atende"] == dict.fromkeys(m["nao_atende"], 0)
