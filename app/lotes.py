"""Fila de lote em memória: workers asyncio, sem Redis.

Um lote entra na fila e volta na hora com um id; os workers processam as conversas com
concorrência limitada (para não estourar o limite de requisições da API) e o cliente
consulta o andamento em GET /lotes/{id}. Some quando o processo reinicia: para a escala
deste projeto, é o tamanho certo. Com mais volume, a troca natural é Redis + arq ou Celery.
"""

import asyncio
import contextlib
import uuid
from collections import OrderedDict
from datetime import UTC, datetime

from app.avaliador import AvaliacaoFalhou, Avaliador
from app.models import ItemLote, Lote, PedidoAvaliacao
from app.rubricas import RubricaNaoEncontrada


class CapacidadeEsgotada(Exception):
    """Não cabe o lote agora: a fila está cheia ou só há lotes em andamento guardados."""


class GerenciadorLotes:
    def __init__(
        self, avaliador: Avaliador, concorrencia: int, guardar: int, fila_max: int
    ) -> None:
        self.avaliador = avaliador
        self.concorrencia = concorrencia
        self.guardar = guardar
        self.fila_max = fila_max
        self._lotes: OrderedDict[str, Lote] = OrderedDict()
        self._fila: asyncio.Queue[tuple[str, int, PedidoAvaliacao]] = asyncio.Queue()
        self._workers: list[asyncio.Task[None]] = []

    def iniciar(self) -> None:
        self._workers = [
            asyncio.create_task(self._worker(), name=f"lote-worker-{i}")
            for i in range(self.concorrencia)
        ]

    async def parar(self) -> None:
        for w in self._workers:
            w.cancel()
        for w in self._workers:
            with contextlib.suppress(asyncio.CancelledError):
                await w
        self._workers = []

    def criar(self, pedidos: list[PedidoAvaliacao]) -> Lote:
        # Sem await daqui até o fim: no asyncio, nenhum outro pedido entra no meio da conta.
        if self._fila.qsize() + len(pedidos) > self.fila_max:
            raise CapacidadeEsgotada(
                f"a fila tem {self._fila.qsize()} conversas esperando; tente de novo depois"
            )
        if len(self._lotes) >= self.guardar and not self._descartar_um_concluido():
            raise CapacidadeEsgotada("todos os lotes guardados ainda estão em andamento")
        lote = Lote(
            id=uuid.uuid4().hex[:12],
            status="na_fila",
            criado_em=datetime.now(UTC),
            total=len(pedidos),
            concluidos=0,
            erros=0,
            itens=[ItemLote(indice=i) for i in range(len(pedidos))],
        )
        self._lotes[lote.id] = lote
        for i, p in enumerate(pedidos):
            self._fila.put_nowait((lote.id, i, p))
        return lote

    def _descartar_um_concluido(self) -> bool:
        """Tira o lote concluído mais antigo. Lote em andamento nunca é descartado."""
        for lote_id, lote in self._lotes.items():
            if lote.status == "concluido":
                del self._lotes[lote_id]
                return True
        return False

    def obter(self, lote_id: str) -> Lote | None:
        return self._lotes.get(lote_id)

    async def aguardar_fila(self) -> None:
        """Espera a fila esvaziar (usado nos testes e no desligamento)."""
        await self._fila.join()

    async def _worker(self) -> None:
        while True:
            lote_id, indice, pedido = await self._fila.get()
            try:
                await self._processar(lote_id, indice, pedido)
            finally:
                self._fila.task_done()

    async def _processar(self, lote_id: str, indice: int, pedido: PedidoAvaliacao) -> None:
        lote = self._lotes.get(lote_id)
        if lote is None:  # não deveria acontecer: lote em andamento não é descartado
            return
        item = lote.itens[indice]
        item.status = "processando"
        if lote.status == "na_fila":
            lote.status = "processando"
        try:
            item.resultado = await self.avaliador.avaliar(pedido)
            item.status = "concluido"
            lote.concluidos += 1
        except (AvaliacaoFalhou, RubricaNaoEncontrada) as e:
            item.status = "erro"
            item.erro = (
                f"rubrica não encontrada: {e.args[0]}"
                if isinstance(e, RubricaNaoEncontrada)
                else str(e)
            )
            lote.erros += 1
        except Exception:  # um item quebrado não pode matar o worker
            item.status = "erro"
            item.erro = "erro interno ao avaliar"
            lote.erros += 1
        if lote.concluidos + lote.erros == lote.total:
            lote.status = "concluido"
