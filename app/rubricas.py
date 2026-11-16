"""Rubricas em YAML: leitura, validação e cálculo da nota."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from app.models import Nivel

NivelPontuado = Literal["atende", "parcial", "nao_atende"]


class Criterio(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    bloco: str
    nome: str
    peso: float = Field(gt=0)
    critico: bool = False
    descricao: str
    atende: str
    parcial: str
    nao_atende: str
    nao_se_aplica: str | None = None

    @property
    def aceita_nao_se_aplica(self) -> bool:
        return self.nao_se_aplica is not None


class Rubrica(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    nome: str
    versao: int = Field(ge=1)
    descricao: str
    niveis: dict[NivelPontuado, float]
    criterios: list[Criterio] = Field(min_length=1)

    @model_validator(mode="after")
    def _validar(self) -> "Rubrica":
        ids = [c.id for c in self.criterios]
        repetidos = sorted({i for i in ids if ids.count(i) > 1})
        if repetidos:
            raise ValueError(f"critérios repetidos: {', '.join(repetidos)}")
        faltando = {"atende", "parcial", "nao_atende"} - set(self.niveis)
        if faltando:
            raise ValueError(f"faltam valores para os níveis: {', '.join(sorted(faltando))}")
        if any(not 0 <= v <= 1 for v in self.niveis.values()):
            raise ValueError("o valor de cada nível fica entre 0 e 1")
        return self

    def criterio(self, criterio_id: str) -> Criterio | None:
        return next((c for c in self.criterios if c.id == criterio_id), None)


class RubricaNaoEncontrada(KeyError):
    pass


class RegistroRubricas:
    """Guarda as rubricas lidas de uma pasta. `recarregar` troca todas de uma vez."""

    def __init__(self, pasta: Path) -> None:
        self.pasta = pasta
        self._rubricas: dict[str, Rubrica] = {}
        self.recarregar()

    def recarregar(self) -> list[str]:
        novas: dict[str, Rubrica] = {}
        for arquivo in sorted(self.pasta.glob("*.yaml")):
            try:
                with arquivo.open(encoding="utf-8") as f:
                    dados = yaml.safe_load(f)
                rubrica = Rubrica.model_validate(dados)
            except (ValueError, yaml.YAMLError) as e:
                raise ValueError(f"rubrica inválida em {arquivo.name}: {e}") from e
            if rubrica.id in novas:
                raise ValueError(f"id de rubrica repetido: {rubrica.id} ({arquivo.name})")
            novas[rubrica.id] = rubrica
        # Só troca depois de ler tudo: um arquivo quebrado não derruba as rubricas em uso.
        self._rubricas = novas
        return sorted(novas)

    def obter(self, rubrica_id: str) -> Rubrica:
        try:
            return self._rubricas[rubrica_id]
        except KeyError:
            raise RubricaNaoEncontrada(rubrica_id) from None

    def listar(self) -> list[Rubrica]:
        return [self._rubricas[i] for i in sorted(self._rubricas)]


def calcular_nota(rubrica: Rubrica, niveis: dict[str, Nivel]) -> tuple[float, float, list[str]]:
    """Devolve (nota, nota_sem_criticos, falhas_criticas).

    Média ponderada dos critérios que se aplicam, em 0-100. "nao_se_aplica" sai da conta.
    Um critério crítico em "nao_atende" zera a nota, como numa monitoria de qualidade.
    """
    soma = 0.0
    pesos = 0.0
    falhas: list[str] = []
    for c in rubrica.criterios:
        nivel = niveis[c.id]
        if nivel == "nao_se_aplica":
            continue
        soma += c.peso * rubrica.niveis[nivel]
        pesos += c.peso
        if c.critico and nivel == "nao_atende":
            falhas.append(c.id)
    sem_criticos = round(100 * soma / pesos, 1) if pesos else 100.0
    return (0.0 if falhas else sem_criticos), sem_criticos, falhas
