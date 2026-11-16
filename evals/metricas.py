"""Métricas de concordância entre o juiz e o rótulo de referência."""

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

NIVEIS = ("atende", "parcial", "nao_atende", "nao_se_aplica")
ORDEM = {"atende": 0, "parcial": 1, "nao_atende": 2}


def kappa_cohen(a: Sequence[str], b: Sequence[str]) -> float | None:
    """Concordância corrigida pelo acaso. 1 = perfeita, 0 = o que o acaso daria.

    None quando não dá para calcular (sem pares, ou os dois lados usam um rótulo só).
    """
    if len(a) != len(b):
        raise ValueError("as duas listas precisam ter o mesmo tamanho")
    n = len(a)
    if n == 0:
        return None
    observada = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    esperada = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    if esperada == 1:
        return None
    return (observada - esperada) / (1 - esperada)


def pearson(x: Sequence[float], y: Sequence[float]) -> float | None:
    if len(x) != len(y):
        raise ValueError("as duas listas precisam ter o mesmo tamanho")
    n = len(x)
    if n < 2:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx == 0 or syy == 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def distancia(ref: str, juiz: str) -> int | None:
    """Quantos níveis de diferença (0, 1 ou 2). None quando um lado é nao_se_aplica e o
    outro não: aí não existe "perto"."""
    if ref == juiz:
        return 0
    if ref in ORDEM and juiz in ORDEM:
        return abs(ORDEM[ref] - ORDEM[juiz])
    return None


@dataclass
class ResumoCriterio:
    criterio: str
    pares: int
    acerto: float
    ate_um_nivel: float
    kappa: float | None


def resumir_criterio(criterio: str, ref: Sequence[str], juiz: Sequence[str]) -> ResumoCriterio:
    n = len(ref)
    dist = [distancia(r, j) for r, j in zip(ref, juiz, strict=True)]
    return ResumoCriterio(
        criterio=criterio,
        pares=n,
        acerto=sum(d == 0 for d in dist) / n if n else 0.0,
        ate_um_nivel=sum(d is not None and d <= 1 for d in dist) / n if n else 0.0,
        kappa=kappa_cohen(ref, juiz),
    )


@dataclass
class DeteccaoCritica:
    verdadeiros: int
    falsos_alarmes: int
    perdidas: int

    @property
    def precisao(self) -> float | None:
        total = self.verdadeiros + self.falsos_alarmes
        return self.verdadeiros / total if total else None

    @property
    def revocacao(self) -> float | None:
        total = self.verdadeiros + self.perdidas
        return self.verdadeiros / total if total else None


def deteccao_critica(ref_zerou: Sequence[bool], juiz_zerou: Sequence[bool]) -> DeteccaoCritica:
    pares = list(zip(ref_zerou, juiz_zerou, strict=True))
    return DeteccaoCritica(
        verdadeiros=sum(r and j for r, j in pares),
        falsos_alarmes=sum(j and not r for r, j in pares),
        perdidas=sum(r and not j for r, j in pares),
    )


def matriz_confusao(ref: Sequence[str], juiz: Sequence[str]) -> dict[str, dict[str, int]]:
    m = {r: dict.fromkeys(NIVEIS, 0) for r in NIVEIS}
    for r, j in zip(ref, juiz, strict=True):
        m[r][j] += 1
    return m
