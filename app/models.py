"""Modelos de entrada e saída da API e o formato que o LLM precisa devolver."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Nivel = Literal["atende", "parcial", "nao_atende", "nao_se_aplica"]
Autor = Literal["cliente", "atendente"]


# ---------- Entrada ----------


class Mensagem(BaseModel):
    autor: Autor
    texto: str = Field(min_length=1, max_length=4000)


class PedidoAvaliacao(BaseModel):
    rubrica_id: str = Field(min_length=1, max_length=100, examples=["suporte_provedor_v1"])
    conversa: list[Mensagem] = Field(min_length=2, max_length=200)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "rubrica_id": "suporte_provedor_v1",
                    "conversa": [
                        {"autor": "cliente", "texto": "Boa tarde, estou sem internet desde cedo"},
                        {
                            "autor": "atendente",
                            "texto": "Boa tarde! Aqui é a Carla, da Alfa Fibra. Pode me "
                            "passar o CPF do titular?",
                        },
                        {"autor": "cliente", "texto": "CPF final 4521"},
                    ],
                }
            ]
        }
    }


# ---------- O que o LLM devolve (saída estruturada) ----------


class Evidencia(BaseModel):
    mensagem: int = Field(description="Índice da mensagem na conversa, começando em 0.")
    trecho: str = Field(description="Trecho copiado literalmente dessa mensagem.")


class VeredictoCriterio(BaseModel):
    criterio_id: str
    nivel: Nivel
    justificativa: str = Field(description="Uma ou duas frases, citando o que aconteceu.")
    evidencias: list[Evidencia] = Field(
        description="Trechos que sustentam o nível. Vazio quando o motivo é uma ausência."
    )


class RespostaJuiz(BaseModel):
    criterios: list[VeredictoCriterio]
    resumo: str = Field(description="Duas ou três frases sobre o atendimento como um todo.")


# ---------- Saída da API ----------


class CriterioAvaliado(BaseModel):
    id: str
    nome: str
    bloco: str
    peso: float
    critico: bool
    nivel: Nivel
    justificativa: str
    evidencias: list[Evidencia]


class MetaAvaliacao(BaseModel):
    provedor: str
    modelo: str
    tentativas: int
    tokens_entrada: int
    tokens_saida: int
    custo_estimado_usd: float | None = Field(
        description="Estimativa pela tabela de preços do modelo que respondeu; None se o "
        "modelo não está na tabela."
    )
    duracao_ms: int


class ResultadoAvaliacao(BaseModel):
    rubrica_id: str
    rubrica_versao: int
    nota: float = Field(ge=0, le=100, description="0 a 100. Zera quando um critério crítico falha.")
    nota_sem_criticos: float = Field(
        ge=0, le=100, description="A nota que daria sem a regra de zerar por falha crítica."
    )
    falhas_criticas: list[str]
    criterios: list[CriterioAvaliado]
    resumo: str
    meta: MetaAvaliacao


# ---------- Lotes ----------

StatusItem = Literal["na_fila", "processando", "concluido", "erro"]
StatusLote = Literal["na_fila", "processando", "concluido"]


class PedidoLote(BaseModel):
    itens: list[PedidoAvaliacao] = Field(min_length=1)


class ItemLote(BaseModel):
    indice: int
    status: StatusItem = "na_fila"
    resultado: ResultadoAvaliacao | None = None
    erro: str | None = None


class Lote(BaseModel):
    id: str
    status: StatusLote
    criado_em: datetime
    total: int
    concluidos: int
    erros: int
    itens: list[ItemLote]


class LoteCriado(BaseModel):
    id: str
    total: int
    status: StatusLote
