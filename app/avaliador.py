"""Orquestra uma avaliação: chama o juiz, valida, refaz quando precisa e calcula a nota."""

import re
import time

from app.juizes import ErroJuiz, Juiz, Uso
from app.models import (
    CriterioAvaliado,
    Mensagem,
    MetaAvaliacao,
    PedidoAvaliacao,
    RespostaJuiz,
    ResultadoAvaliacao,
)
from app.rubricas import RegistroRubricas, Rubrica, calcular_nota


class AvaliacaoFalhou(Exception):
    """O juiz não entregou uma avaliação válida dentro das tentativas."""


def _compactar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip().casefold()


def validar_resposta(
    resposta: RespostaJuiz, rubrica: Rubrica, conversa: list[Mensagem]
) -> list[str]:
    """Confere o que o esquema JSON não garante. Devolve a lista de problemas (vazia = ok).

    A saída estruturada garante o formato; não garante que os ids batem com a rubrica nem
    que o trecho citado existe na conversa. Uma evidência inventada é o erro mais perigoso
    de um avaliador com LLM: a justificativa parece sólida e não tem base.
    """
    problemas: list[str] = []
    vistos: dict[str, int] = {}
    for v in resposta.criterios:
        vistos[v.criterio_id] = vistos.get(v.criterio_id, 0) + 1
        criterio = rubrica.criterio(v.criterio_id)
        if criterio is None:
            problemas.append(f"critério desconhecido: {v.criterio_id}")
            continue
        if v.nivel == "nao_se_aplica" and not criterio.aceita_nao_se_aplica:
            problemas.append(f"{v.criterio_id}: este critério não aceita nao_se_aplica")
        for e in v.evidencias:
            if not 0 <= e.mensagem < len(conversa):
                problemas.append(
                    f"{v.criterio_id}: a evidência aponta a mensagem {e.mensagem}, que não existe"
                )
            elif not _compactar(e.trecho):
                # Trecho vazio "está" em qualquer mensagem; não comprova nada.
                problemas.append(f"{v.criterio_id}: evidência com trecho vazio")
            elif _compactar(e.trecho) not in _compactar(conversa[e.mensagem].texto):
                problemas.append(
                    f"{v.criterio_id}: o trecho {e.trecho!r} não está na mensagem {e.mensagem}"
                )
    repetidos = sorted(i for i, n in vistos.items() if n > 1)
    if repetidos:
        problemas.append(f"critérios repetidos: {', '.join(repetidos)}")
    faltando = [c.id for c in rubrica.criterios if c.id not in vistos]
    if faltando:
        problemas.append(f"faltam os critérios: {', '.join(faltando)}")
    return problemas


class Avaliador:
    def __init__(self, juiz: Juiz, rubricas: RegistroRubricas, max_tentativas: int = 3) -> None:
        self.juiz = juiz
        self.rubricas = rubricas
        self.max_tentativas = max_tentativas

    async def avaliar(self, pedido: PedidoAvaliacao) -> ResultadoAvaliacao:
        rubrica = self.rubricas.obter(pedido.rubrica_id)  # RubricaNaoEncontrada sobe para a API
        inicio = time.perf_counter()
        uso = Uso()
        correcoes: list[str] = []
        modelo = self.juiz.modelo
        for tentativa in range(1, self.max_tentativas + 1):
            try:
                julgamento = await self.juiz.julgar(rubrica, pedido.conversa, correcoes)
            except ErroJuiz as e:
                raise AvaliacaoFalhou(str(e)) from e
            uso.somar(julgamento.uso)
            modelo = julgamento.modelo
            correcoes = validar_resposta(julgamento.resposta, rubrica, pedido.conversa)
            if not correcoes:
                return self._montar(rubrica, julgamento.resposta, modelo, tentativa, uso, inicio)
        raise AvaliacaoFalhou(
            f"a resposta do juiz não passou na validação em {self.max_tentativas} tentativas: "
            + "; ".join(correcoes)
        )

    def _montar(
        self,
        rubrica: Rubrica,
        resposta: RespostaJuiz,
        modelo: str,
        tentativas: int,
        uso: Uso,
        inicio: float,
    ) -> ResultadoAvaliacao:
        por_id = {v.criterio_id: v for v in resposta.criterios}
        nota, sem_criticos, falhas = calcular_nota(rubrica, {i: v.nivel for i, v in por_id.items()})
        criterios = [
            CriterioAvaliado(
                id=c.id,
                nome=c.nome,
                bloco=c.bloco,
                peso=c.peso,
                critico=c.critico,
                nivel=por_id[c.id].nivel,
                justificativa=por_id[c.id].justificativa,
                evidencias=por_id[c.id].evidencias,
            )
            for c in rubrica.criterios
        ]
        return ResultadoAvaliacao(
            rubrica_id=rubrica.id,
            rubrica_versao=rubrica.versao,
            nota=nota,
            nota_sem_criticos=sem_criticos,
            falhas_criticas=falhas,
            criterios=criterios,
            resumo=resposta.resumo,
            meta=MetaAvaliacao(
                provedor=self.juiz.provedor,
                modelo=modelo,
                tentativas=tentativas,
                tokens_entrada=uso.tokens_entrada,
                tokens_saida=uso.tokens_saida,
                custo_estimado_usd=uso.custo_usd,
                duracao_ms=round((time.perf_counter() - inicio) * 1000),
            ),
        )
