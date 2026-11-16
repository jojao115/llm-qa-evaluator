"""API FastAPI: avaliação individual, lotes e rubricas."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status

from app.avaliador import AvaliacaoFalhou, Avaliador
from app.config import Config
from app.juizes import Juiz, JuizAnthropic, JuizSimulado
from app.lotes import CapacidadeEsgotada, GerenciadorLotes
from app.models import Lote, LoteCriado, PedidoAvaliacao, PedidoLote, ResultadoAvaliacao
from app.rubricas import RegistroRubricas, Rubrica, RubricaNaoEncontrada

log = logging.getLogger("llm_qa_evaluator")


def criar_juiz(config: Config) -> Juiz:
    if config.llm_provedor == "anthropic":
        return JuizAnthropic(config.llm_modelo, config.llm_esforco, timeout_s=config.llm_timeout_s)
    return JuizSimulado()


def criar_app(config: Config | None = None, juiz: Juiz | None = None) -> FastAPI:
    config = config or Config()
    rubricas = RegistroRubricas(config.pasta_rubricas)
    juiz = juiz or criar_juiz(config)
    avaliador = Avaliador(juiz, rubricas, config.max_tentativas)
    lotes = GerenciadorLotes(
        avaliador, config.lote_concorrencia, config.lotes_guardados, config.lote_fila_max
    )

    @asynccontextmanager
    async def ciclo(_: FastAPI) -> AsyncIterator[None]:
        lotes.iniciar()
        log.info("juiz: %s / %s; rubricas: %s", juiz.provedor, juiz.modelo, len(rubricas.listar()))
        yield
        await lotes.parar()

    app = FastAPI(
        title="llm-qa-evaluator",
        version="0.1.0",
        summary="Avalia atendimentos com um LLM, por rubrica, com evidência citada.",
        lifespan=ciclo,
    )
    app.state.avaliador = avaliador
    app.state.lotes = lotes

    def _rubrica(rubrica_id: str) -> Rubrica:
        try:
            return rubricas.obter(rubrica_id)
        except RubricaNaoEncontrada:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"rubrica não encontrada: {rubrica_id}"
            ) from None

    @app.get("/saude")
    async def saude() -> dict[str, object]:
        return {
            "status": "ok",
            "provedor": juiz.provedor,
            "modelo": juiz.modelo,
            "rubricas": [r.id for r in rubricas.listar()],
        }

    @app.get("/rubricas")
    async def listar_rubricas() -> list[Rubrica]:
        return rubricas.listar()

    @app.get("/rubricas/{rubrica_id}")
    async def obter_rubrica(rubrica_id: str) -> Rubrica:
        return _rubrica(rubrica_id)

    @app.post("/rubricas/recarregar")
    async def recarregar_rubricas() -> dict[str, list[str]]:
        try:
            return {"rubricas": rubricas.recarregar()}
        except ValueError as e:
            # As rubricas antigas continuam valendo; só a recarga falhou.
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None

    @app.post("/avaliar")
    async def avaliar(pedido: PedidoAvaliacao) -> ResultadoAvaliacao:
        _rubrica(pedido.rubrica_id)
        try:
            return await avaliador.avaliar(pedido)
        except AvaliacaoFalhou as e:
            log.warning("avaliação falhou: %s", e)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from None

    @app.post("/lotes", status_code=status.HTTP_202_ACCEPTED)
    async def criar_lote(pedido: PedidoLote) -> LoteCriado:
        if len(pedido.itens) > config.lote_max_conversas:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"no máximo {config.lote_max_conversas} conversas por lote",
            )
        for item in pedido.itens:
            _rubrica(item.rubrica_id)
        try:
            lote = lotes.criar(pedido.itens)
        except CapacidadeEsgotada as e:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from None
        return LoteCriado(id=lote.id, total=lote.total, status=lote.status)

    @app.get("/lotes/{lote_id}")
    async def obter_lote(lote_id: str) -> Lote:
        lote = lotes.obter(lote_id)
        if lote is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"lote não encontrado: {lote_id}")
        return lote

    return app
