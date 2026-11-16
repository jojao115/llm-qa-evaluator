from pathlib import Path

import pytest
import yaml

from app.config import PASTA_RUBRICAS_PADRAO
from app.models import Nivel
from app.rubricas import RegistroRubricas, Rubrica, RubricaNaoEncontrada, calcular_nota


def test_carrega_a_rubrica_do_projeto(rubrica: Rubrica) -> None:
    assert rubrica.versao == 1
    assert len(rubrica.criterios) == 12
    criticos = {c.id for c in rubrica.criterios if c.critico}
    assert criticos == {"identificacao_titular", "informacao_precisa"}
    com_na = {c.id for c in rubrica.criterios if c.aceita_nao_se_aplica}
    assert com_na == {"identificacao_titular", "diagnostico", "procedimento", "retencao"}


def test_rubrica_inexistente(rubricas: RegistroRubricas) -> None:
    with pytest.raises(RubricaNaoEncontrada):
        rubricas.obter("nao_existe")


def _dados_validos() -> dict[str, object]:
    with (PASTA_RUBRICAS_PADRAO / "suporte_provedor_v1.yaml").open(encoding="utf-8") as f:
        dados: dict[str, object] = yaml.safe_load(f)
    return dados


@pytest.mark.parametrize(
    ("mexer", "mensagem"),
    [
        (lambda d: d["criterios"].append(dict(d["criterios"][0])), "critérios repetidos"),
        (lambda d: d["niveis"].pop("parcial"), "faltam valores"),
        (lambda d: d["niveis"].update(atende=2), "entre 0 e 1"),
    ],
)
def test_recusa_rubrica_mal_formada(mexer, mensagem: str) -> None:  # type: ignore[no-untyped-def]
    dados = _dados_validos()
    mexer(dados)
    with pytest.raises(ValueError, match=mensagem):
        Rubrica.model_validate(dados)


def test_recarga_com_arquivo_quebrado_mantem_as_rubricas_em_uso(tmp_path: Path) -> None:
    (tmp_path / "boa.yaml").write_text(yaml.safe_dump(_dados_validos()), encoding="utf-8")
    registro = RegistroRubricas(tmp_path)
    assert [r.id for r in registro.listar()] == ["suporte_provedor_v1"]

    (tmp_path / "quebrada.yaml").write_text("id: x\nnome: sem criterios\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"quebrada\.yaml"):
        registro.recarregar()
    assert [r.id for r in registro.listar()] == ["suporte_provedor_v1"]


def _niveis(rubrica: Rubrica, padrao: Nivel = "atende", **outros: Nivel) -> dict[str, Nivel]:
    return {c.id: outros.get(c.id, padrao) for c in rubrica.criterios}


def test_nota_cheia_quando_tudo_atende(rubrica: Rubrica) -> None:
    assert calcular_nota(rubrica, _niveis(rubrica)) == (100.0, 100.0, [])


def test_nao_se_aplica_sai_da_conta(rubrica: Rubrica) -> None:
    # Retenção (peso 2) fora da conta: o resto continua 100.
    assert calcular_nota(rubrica, _niveis(rubrica, retencao="nao_se_aplica"))[0] == 100.0


def test_media_ponderada(rubrica: Rubrica) -> None:
    # Pesos somam 20. solucao_correta (peso 3) parcial perde 1,5 ponto de 20 = 7,5%.
    nota, _, falhas = calcular_nota(rubrica, _niveis(rubrica, solucao_correta="parcial"))
    assert nota == 92.5
    assert falhas == []


def test_falha_critica_zera_e_guarda_a_nota_sem_a_regra(rubrica: Rubrica) -> None:
    nota, sem_criticos, falhas = calcular_nota(
        rubrica, _niveis(rubrica, informacao_precisa="nao_atende")
    )
    assert nota == 0.0
    assert sem_criticos == 85.0  # perde os 3 de 20
    assert falhas == ["informacao_precisa"]


def test_critico_parcial_nao_zera(rubrica: Rubrica) -> None:
    nota, _, falhas = calcular_nota(rubrica, _niveis(rubrica, identificacao_titular="parcial"))
    assert nota == 95.0
    assert falhas == []


def test_yaml_quebrado_vira_erro_de_validacao(tmp_path: Path) -> None:
    (tmp_path / "boa.yaml").write_text(yaml.safe_dump(_dados_validos()), encoding="utf-8")
    registro = RegistroRubricas(tmp_path)
    (tmp_path / "sintaxe.yaml").write_text("criterios: [\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"sintaxe\.yaml"):
        registro.recarregar()
    assert [r.id for r in registro.listar()] == ["suporte_provedor_v1"]
