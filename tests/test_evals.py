import json
from pathlib import Path

import pytest

from app.rubricas import RegistroRubricas
from evals.run_evals import DATASET, carregar


def _linhas() -> list[dict[str, object]]:
    with DATASET.open(encoding="utf-8") as f:
        return [json.loads(linha) for linha in f][:2]


def _gravar(tmp_path: Path, linhas: list[dict[str, object]]) -> Path:
    arquivo = tmp_path / "d.jsonl"
    arquivo.write_text("\n".join(json.dumps(x) for x in linhas), encoding="utf-8")
    return arquivo


def test_dataset_do_projeto(rubricas: RegistroRubricas) -> None:
    exemplos = carregar(DATASET, rubricas)
    assert len(exemplos) == 40
    assert len({e.id for e in exemplos}) == 40


def test_recusa_id_repetido(tmp_path: Path, rubricas: RegistroRubricas) -> None:
    a, b = _linhas()
    b["id"] = a["id"]
    with pytest.raises(ValueError, match="linha 2: id repetido"):
        carregar(_gravar(tmp_path, [a, b]), rubricas)


def test_recusa_rubrica_misturada(tmp_path: Path, rubricas: RegistroRubricas) -> None:
    a, b = _linhas()
    b["rubrica"] = "outra"
    with pytest.raises(ValueError, match="separe um arquivo por rubrica"):
        carregar(_gravar(tmp_path, [a, b]), rubricas)


def test_recusa_referencia_incompleta(tmp_path: Path, rubricas: RegistroRubricas) -> None:
    a, _ = _linhas()
    referencia = a["referencia"]
    assert isinstance(referencia, dict)
    referencia.pop("protocolo")
    with pytest.raises(ValueError, match="não cobre os critérios"):
        carregar(_gravar(tmp_path, [a]), rubricas)


def test_recusa_dataset_vazio(tmp_path: Path, rubricas: RegistroRubricas) -> None:
    with pytest.raises(ValueError, match="dataset vazio"):
        carregar(_gravar(tmp_path, []), rubricas)
