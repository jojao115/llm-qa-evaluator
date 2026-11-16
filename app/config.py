from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PASTA_RUBRICAS_PADRAO = Path(__file__).parent / "rubrics"

Esforco = Literal["low", "medium", "high", "xhigh", "max"]


class Config(BaseSettings):
    """Configuração lida do ambiente (ou do .env). Nada aqui tem segredo com valor padrão."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # "simulado" roda sem chave de API (heurística por palavras-chave); "anthropic" chama o Claude.
    llm_provedor: Literal["simulado", "anthropic"] = "simulado"
    llm_modelo: str = "claude-opus-5-5"
    llm_esforco: Esforco = "medium"
    llm_timeout_s: float = Field(default=120.0, gt=0)
    # Quantas vezes pedir de novo quando a resposta do LLM não passa na validação.
    max_tentativas: int = Field(default=3, ge=1)

    pasta_rubricas: Path = PASTA_RUBRICAS_PADRAO

    # Fila de lote: quantas avaliações rodam ao mesmo tempo, o tamanho máximo de um lote,
    # quantas conversas podem esperar na fila (somando todos os lotes) e quantos lotes
    # ficam guardados para consulta.
    lote_concorrencia: int = Field(default=4, ge=1)
    lote_max_conversas: int = Field(default=200, ge=1)
    lote_fila_max: int = Field(default=2000, ge=1)
    lotes_guardados: int = Field(default=100, ge=1)
