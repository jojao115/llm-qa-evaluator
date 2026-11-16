"""Roda o juiz sobre o conjunto de avaliação e mede a concordância com a referência.

    python -m evals.run_evals                         # juiz simulado, sem custo
    python -m evals.run_evals --provedor anthropic    # Claude: usa a API e gasta créditos

Escreve evals/resultados/<provedor>-<modelo>.md (tabelas) e .json (tudo, conversa a conversa).
"""

import argparse
import asyncio
import json
import re
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.avaliador import AvaliacaoFalhou, Avaliador
from app.config import PASTA_RUBRICAS_PADRAO
from app.juizes import Juiz, JuizAnthropic, JuizSimulado
from app.models import Mensagem, Nivel, PedidoAvaliacao, ResultadoAvaliacao
from app.rubricas import RegistroRubricas, calcular_nota
from evals.metricas import (
    NIVEIS,
    deteccao_critica,
    matriz_confusao,
    pearson,
    resumir_criterio,
)

RAIZ = Path(__file__).parent
DATASET = RAIZ / "dataset.jsonl"
RESULTADOS = RAIZ / "resultados"


class Exemplo(BaseModel):
    id: str
    rubrica: str
    canal: str
    tema: str
    conversa: list[Mensagem]
    referencia: dict[str, Nivel]
    observacao: str = ""


def carregar(caminho: Path, rubricas: RegistroRubricas) -> list[Exemplo]:
    """Lê e confere o dataset antes de qualquer chamada ao LLM (erro aqui não custa nada)."""
    exemplos: list[Exemplo] = []
    vistos: set[str] = set()
    with caminho.open(encoding="utf-8") as f:
        for n, linha in enumerate(f, 1):
            if not linha.strip():
                continue
            ex = Exemplo.model_validate_json(linha)
            if ex.id in vistos:
                raise ValueError(f"linha {n}: id repetido {ex.id}")
            vistos.add(ex.id)
            # As métricas comparam critério a critério: o dataset usa uma rubrica só.
            if exemplos and ex.rubrica != exemplos[0].rubrica:
                raise ValueError(
                    f"linha {n} ({ex.id}): rubrica {ex.rubrica}, mas o dataset começou com "
                    f"{exemplos[0].rubrica}; separe um arquivo por rubrica"
                )
            rubrica = rubricas.obter(ex.rubrica)
            esperado = {c.id for c in rubrica.criterios}
            if set(ex.referencia) != esperado:
                raise ValueError(f"linha {n} ({ex.id}): a referência não cobre os critérios")
            exemplos.append(ex)
    if not exemplos:
        raise ValueError(f"dataset vazio: {caminho}")
    return exemplos


def _positivo(valor: str) -> int:
    n = int(valor)
    if n < 1:
        raise argparse.ArgumentTypeError("precisa ser 1 ou mais")
    return n


async def avaliar_todos(
    avaliador: Avaliador, exemplos: list[Exemplo], concorrencia: int
) -> dict[str, ResultadoAvaliacao | str]:
    semaforo = asyncio.Semaphore(concorrencia)
    saida: dict[str, ResultadoAvaliacao | str] = {}

    async def um(ex: Exemplo) -> None:
        async with semaforo:
            try:
                saida[ex.id] = await avaliador.avaliar(
                    PedidoAvaliacao(rubrica_id=ex.rubrica, conversa=ex.conversa)
                )
            except AvaliacaoFalhou as e:
                saida[ex.id] = f"erro: {e}"
            print(".", end="", flush=True, file=sys.stderr)

    await asyncio.gather(*(um(ex) for ex in exemplos))
    print(file=sys.stderr)
    return saida


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{100 * x:.0f}%"


def _num(x: float | None, casas: int = 2) -> str:
    return "—" if x is None else f"{x:.{casas}f}"


def calcular(
    exemplos: list[Exemplo],
    resultados: dict[str, ResultadoAvaliacao | str],
    rubricas: RegistroRubricas,
) -> dict[str, Any]:
    ok = [(ex, r) for ex in exemplos if isinstance(r := resultados[ex.id], ResultadoAvaliacao)]
    rubrica = rubricas.obter(exemplos[0].rubrica)
    ids = [c.id for c in rubrica.criterios]

    por_criterio = []
    todos_ref: list[str] = []
    todos_juiz: list[str] = []
    for cid in ids:
        ref = [ex.referencia[cid] for ex, _ in ok]
        juiz = [next(c.nivel for c in r.criterios if c.id == cid) for _, r in ok]
        todos_ref += ref
        todos_juiz += juiz
        por_criterio.append(resumir_criterio(cid, ref, juiz))

    notas_ref = [calcular_nota(rubrica, ex.referencia)[0] for ex, _ in ok]
    notas_juiz = [r.nota for _, r in ok]
    critica = deteccao_critica([n == 0 for n in notas_ref], [n == 0 for n in notas_juiz])
    geral = resumir_criterio("geral", todos_ref, todos_juiz)

    divergencias = []
    for ex, r in ok:
        for c in r.criterios:
            if c.nivel != ex.referencia[c.id]:
                divergencias.append(
                    {
                        "conversa": ex.id,
                        "criterio": c.id,
                        "referencia": ex.referencia[c.id],
                        "juiz": c.nivel,
                        "justificativa": c.justificativa,
                    }
                )

    custos = [r.meta.custo_estimado_usd for _, r in ok]
    return {
        "conversas": len(exemplos),
        "avaliadas": len(ok),
        "erros": {i: r for i, r in resultados.items() if isinstance(r, str)},
        "acerto_geral": geral.acerto,
        "ate_um_nivel_geral": geral.ate_um_nivel,
        "kappa_geral": geral.kappa,
        "erro_medio_nota": (
            sum(abs(a - b) for a, b in zip(notas_ref, notas_juiz, strict=True)) / len(ok)
            if ok
            else None
        ),
        "correlacao_nota": pearson(notas_ref, notas_juiz),
        "falha_critica": {
            "verdadeiros": critica.verdadeiros,
            "falsos_alarmes": critica.falsos_alarmes,
            "perdidas": critica.perdidas,
            "precisao": critica.precisao,
            "revocacao": critica.revocacao,
        },
        "por_criterio": [asdict(p) for p in por_criterio],
        "matriz": matriz_confusao(todos_ref, todos_juiz),
        "custo_total_usd": None if any(c is None for c in custos) else sum(c or 0 for c in custos),
        "tokens_entrada": sum(r.meta.tokens_entrada for _, r in ok),
        "tokens_saida": sum(r.meta.tokens_saida for _, r in ok),
        "tentativas_extras": sum(r.meta.tentativas - 1 for _, r in ok),
        "duracao_media_ms": sum(r.meta.duracao_ms for _, r in ok) / len(ok) if ok else None,
        "divergencias": divergencias,
    }


def relatorio_md(m: dict[str, Any], juiz: Juiz, modelo_real: str, quando: str) -> str:
    fc = m["falha_critica"]
    custo = m["custo_total_usd"]
    custo_txt = "—" if custo is None else f"US$ {custo:.2f}"
    tokens_txt = f"{m['tokens_entrada']:,} / {m['tokens_saida']:,}".replace(",", ".")
    media_ms = m["duracao_media_ms"]
    tempo_txt = _num(None if media_ms is None else media_ms / 1000, 1)
    critica_txt = f"{_pct(fc['precisao'])} / {_pct(fc['revocacao'])}"
    linhas = [
        f"# Eval: {juiz.provedor} / {modelo_real}",
        "",
        f"{quando} · {m['avaliadas']} de {m['conversas']} conversas avaliadas"
        + (f" · {len(m['erros'])} com erro" if m["erros"] else ""),
        "",
        "| Métrica | Valor |",
        "| --- | --- |",
        f"| Acerto exato por critério | {_pct(m['acerto_geral'])} |",
        f"| Acerto com até 1 nível de diferença | {_pct(m['ate_um_nivel_geral'])} |",
        f"| Kappa de Cohen (geral) | {_num(m['kappa_geral'])} |",
        f"| Erro médio da nota (0 a 100) | {_num(m['erro_medio_nota'], 1)} pontos |",
        f"| Correlação da nota (Pearson) | {_num(m['correlacao_nota'])} |",
        f"| Falha crítica: precisão / revocação | {critica_txt} |",
        f"| Falha crítica: perdidas / falsos alarmes | {fc['perdidas']} / {fc['falsos_alarmes']} |",
        f"| Tentativas extras (validação recusou) | {m['tentativas_extras']} |",
        f"| Custo estimado | {custo_txt} |",
        f"| Tokens (entrada / saída) | {tokens_txt} |",
        f"| Tempo médio por conversa | {tempo_txt} s |",
        "",
        "## Por critério",
        "",
        "| Critério | Acerto | Até 1 nível | Kappa |",
        "| --- | --- | --- | --- |",
    ]
    for p in m["por_criterio"]:
        linhas.append(
            f"| `{p['criterio']}` | {_pct(p['acerto'])} | {_pct(p['ate_um_nivel'])} | "
            f"{_num(p['kappa'])} |"
        )
    linhas += [
        "",
        "## Matriz de confusão (linhas: referência; colunas: juiz)",
        "",
        "| | " + " | ".join(NIVEIS) + " |",
        "| --- |" + " --- |" * len(NIVEIS),
    ]
    for ref in NIVEIS:
        linhas.append(
            f"| **{ref}** | " + " | ".join(str(m["matriz"][ref][j]) for j in NIVEIS) + " |"
        )
    if m["erros"]:
        linhas += ["", "## Conversas com erro", ""]
        linhas += [f"- `{i}`: {e}" for i, e in sorted(m["erros"].items())]
    return "\n".join(linhas) + "\n"


def _juiz(args: argparse.Namespace) -> Juiz:
    if args.provedor == "anthropic":
        return JuizAnthropic(args.modelo, args.esforco)
    return JuizSimulado()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--provedor", choices=["simulado", "anthropic"], default="simulado")
    p.add_argument("--modelo", default="claude-opus-5-5")
    p.add_argument("--esforco", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("--limite", type=_positivo, help="avalia só as N primeiras conversas")
    p.add_argument("--concorrencia", type=_positivo, default=4)
    p.add_argument("--dataset", type=Path, default=DATASET)
    p.add_argument("--saida", type=Path, default=RESULTADOS)
    args = p.parse_args()

    rubricas = RegistroRubricas(PASTA_RUBRICAS_PADRAO)
    exemplos = carregar(args.dataset, rubricas)[: args.limite]
    juiz = _juiz(args)
    avaliador = Avaliador(juiz, rubricas)

    inicio = time.perf_counter()
    resultados = asyncio.run(avaliar_todos(avaliador, exemplos, args.concorrencia))
    metricas = calcular(exemplos, resultados, rubricas)
    metricas["duracao_total_s"] = round(time.perf_counter() - inicio, 1)

    modelos = {r.meta.modelo for r in resultados.values() if isinstance(r, ResultadoAvaliacao)}
    modelo_real = ", ".join(sorted(modelos)) or juiz.modelo
    quando = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    nome = re.sub(r"[^a-z0-9.-]+", "-", f"{juiz.provedor}-{juiz.modelo}".lower())
    if juiz.provedor == "anthropic":
        nome += f"-{args.esforco}"

    args.saida.mkdir(parents=True, exist_ok=True)
    md = relatorio_md(metricas, juiz, modelo_real, quando)
    (args.saida / f"{nome}.md").write_text(md, encoding="utf-8")
    completo = {
        "provedor": juiz.provedor,
        "modelo": modelo_real,
        "esforco": args.esforco if juiz.provedor == "anthropic" else None,
        "quando": quando,
        "metricas": metricas,
        "resultados": {
            i: (r.model_dump(mode="json") if isinstance(r, ResultadoAvaliacao) else r)
            for i, r in sorted(resultados.items())
        },
    }
    (args.saida / f"{nome}.json").write_text(
        json.dumps(completo, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(md)
    print(f"Relatório em {args.saida / (nome + '.md')}", file=sys.stderr)


if __name__ == "__main__":
    main()
