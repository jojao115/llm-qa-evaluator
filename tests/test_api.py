import time
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Config
from app.juizes import ErroJuiz
from app.main import criar_app
from app.models import RespostaJuiz
from tests.conftest import CONVERSA, JuizRoteirizado

CORPO = {
    "rubrica_id": "suporte_provedor_v1",
    "conversa": [m.model_dump() for m in CONVERSA],
}


@pytest.fixture
def cliente(resposta_valida: Callable[..., RespostaJuiz]) -> Iterator[TestClient]:
    juiz = JuizRoteirizado(resposta_valida(retencao="nao_se_aplica"))
    app = criar_app(Config(lote_concorrencia=2, lote_max_conversas=3), juiz=juiz)
    with TestClient(app) as c:  # o "with" roda o lifespan, que liga os workers do lote
        yield c


def test_saude(cliente: TestClient) -> None:
    r = cliente.get("/saude")
    assert r.status_code == 200
    assert r.json() == {
        "status": "ok",
        "provedor": "teste",
        "modelo": "roteiro",
        "rubricas": ["suporte_provedor_v1"],
    }


def test_rubricas(cliente: TestClient) -> None:
    assert [r["id"] for r in cliente.get("/rubricas").json()] == ["suporte_provedor_v1"]
    assert len(cliente.get("/rubricas/suporte_provedor_v1").json()["criterios"]) == 12
    assert cliente.get("/rubricas/outra").status_code == 404
    assert cliente.post("/rubricas/recarregar").json() == {"rubricas": ["suporte_provedor_v1"]}


def test_avaliar(cliente: TestClient) -> None:
    r = cliente.post("/avaliar", json=CORPO)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["nota"] == 100.0
    assert corpo["meta"]["tentativas"] == 1
    assert {c["id"] for c in corpo["criterios"]} >= {"saudacao", "retencao"}


def test_entrada_invalida(cliente: TestClient) -> None:
    assert cliente.post("/avaliar", json={**CORPO, "rubrica_id": "outra"}).status_code == 404
    curta = {**CORPO, "conversa": CORPO["conversa"][:1]}
    assert cliente.post("/avaliar", json=curta).status_code == 422
    autor_errado = {**CORPO, "conversa": [{"autor": "bot", "texto": "oi"}] * 2}
    assert cliente.post("/avaliar", json=autor_errado).status_code == 422


def test_juiz_falhando_vira_502() -> None:
    juiz = JuizRoteirizado(ErroJuiz("a API respondeu 529"))
    with TestClient(criar_app(Config(), juiz=juiz)) as c:
        r = c.post("/avaliar", json=CORPO)
    assert r.status_code == 502
    assert r.json() == {"detail": "a API respondeu 529"}


def _esperar_lote(c: TestClient, lote_id: str) -> dict[str, object]:
    for _ in range(100):
        corpo: dict[str, object] = c.get(f"/lotes/{lote_id}").json()
        if corpo["status"] == "concluido":
            return corpo
        time.sleep(0.02)
    raise AssertionError("o lote não terminou")


def test_lote(cliente: TestClient) -> None:
    r = cliente.post("/lotes", json={"itens": [CORPO, CORPO, CORPO]})
    assert r.status_code == 202
    assert r.json()["total"] == 3
    lote = _esperar_lote(cliente, r.json()["id"])
    assert lote["concluidos"] == 3
    assert lote["erros"] == 0
    itens = lote["itens"]
    assert isinstance(itens, list)
    assert [i["status"] for i in itens] == ["concluido"] * 3
    assert itens[0]["resultado"]["nota"] == 100.0


def test_lote_com_item_que_falha(resposta_valida: Callable[..., RespostaJuiz]) -> None:
    juiz = JuizRoteirizado(ErroJuiz("o modelo recusou avaliar esta conversa"), resposta_valida())
    with TestClient(criar_app(Config(lote_concorrencia=1), juiz=juiz)) as c:
        r = c.post("/lotes", json={"itens": [CORPO, CORPO]})
        lote = _esperar_lote(c, r.json()["id"])
    assert lote["concluidos"] == 1
    assert lote["erros"] == 1
    itens = lote["itens"]
    assert isinstance(itens, list)
    assert itens[0]["erro"] == "o modelo recusou avaliar esta conversa"


def test_lote_invalido(cliente: TestClient) -> None:
    assert cliente.post("/lotes", json={"itens": [CORPO] * 4}).status_code == 422
    assert cliente.post("/lotes", json={"itens": []}).status_code == 422
    outra = {**CORPO, "rubrica_id": "outra"}
    assert cliente.post("/lotes", json={"itens": [CORPO, outra]}).status_code == 404
    assert cliente.get("/lotes/naoexiste").status_code == 404
