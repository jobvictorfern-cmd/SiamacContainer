import random

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from siamac.api import create_app
from siamac.cameras import PROJECT_CAMERAS, SimulatedCamera
from siamac.ocr.simulated import SimulatedOcr
from siamac.pipeline import Pipeline
from siamac.storage import OutboxItem, TrainingSample, make_engine, make_session_factory

TRUTH = "CSQU3054383"
KEY = "chave-de-teste"


@pytest.fixture
def ctx(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path/'t.db'}")
    sf = make_session_factory(engine)
    pipe = Pipeline(
        [SimulatedCamera(s) for s in PROJECT_CAMERAS],
        SimulatedOcr(seed=1),
        session_factory=sf,
        rng=random.Random(1),
    )
    return TestClient(create_app(session_factory=sf, pipeline=pipe, api_key=KEY)), sf


@pytest.fixture
def client(ctx):
    c, _ = ctx
    c.headers.update({"X-API-Key": KEY})
    return c


def test_sem_chave_recusa(ctx):
    c, _ = ctx
    assert c.post("/v1/events", json={"truth": TRUTH}).status_code == 401


def test_health_dispensa_chave(ctx):
    c, _ = ctx
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["ocr_backend"] == "simulated"


def test_evento_completo_e_persistido(client):
    r = client.post("/v1/events", json={"truth": TRUTH, "external_ref": "NF-42"})
    assert r.status_code == 201
    body = r.json()
    assert body["external_ref"] == "NF-42"
    assert len(body["reads"]) == 3
    assert body["status"] in {"AUTO_ACCEPTED", "NEEDS_REVIEW"}
    assert client.get(f"/v1/events/{body['id']}").json()["id"] == body["id"]


def test_correcao_humana_valida_e_gera_treino(client, ctx):
    _, sf = ctx
    eid = client.post("/v1/events", json={"truth": TRUTH}).json()["id"]

    r = client.patch(
        f"/v1/events/{eid}",
        json={"container_code": TRUTH, "iso_type": "45G1", "corrected_by": "joao"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "CORRECTED"
    assert r.json()["container_code"] == TRUTH
    assert r.json()["corrected_by"] == "joao"

    with sf() as s:
        samples = s.scalars(select(TrainingSample).where(TrainingSample.event_id == eid)).all()
    # Uma amostra por câmera, com uma única transcrição digitada — é a
    # economia de 3x na anotação que o plano prevê.
    assert len(samples) == 3
    assert {x.truth_text for x in samples} == {TRUTH}


def test_correcao_recusa_codigo_com_dv_errado(client):
    eid = client.post("/v1/events", json={"truth": TRUTH}).json()["id"]
    r = client.patch(
        f"/v1/events/{eid}",
        json={"container_code": "CSQU3054384", "corrected_by": "joao"},
    )
    assert r.status_code == 422
    assert "verificador" in r.json()["detail"]


def test_correcao_recusa_size_type_invalido(client):
    eid = client.post("/v1/events", json={"truth": TRUTH}).json()["id"]
    r = client.patch(
        f"/v1/events/{eid}",
        json={"container_code": TRUTH, "iso_type": "XX", "corrected_by": "joao"},
    )
    assert r.status_code == 422


def test_correcao_enfileira_entrega_ao_sistema_principal(client, ctx):
    _, sf = ctx
    eid = client.post("/v1/events", json={"truth": TRUTH}).json()["id"]
    client.patch(f"/v1/events/{eid}", json={"container_code": TRUTH, "corrected_by": "ana"})

    with sf() as s:
        items = s.scalars(select(OutboxItem).where(OutboxItem.event_id == eid)).all()
    assert any('"source": "human"' in i.payload for i in items)
    assert all(i.delivered_at is None for i in items)


def test_fila_de_revisao_filtra_por_status(client):
    for _ in range(6):
        client.post("/v1/events", json={"truth": TRUTH})
    fila = client.get("/v1/events", params={"status": "NEEDS_REVIEW"}).json()
    assert all(e["status"] == "NEEDS_REVIEW" for e in fila)


def test_confirmar_leitura_automatica(client):
    eid = client.post("/v1/events", json={"truth": TRUTH}).json()["id"]
    r = client.post(f"/v1/events/{eid}/confirm", params={"confirmed_by": "ana"})
    assert r.status_code == 200
    assert r.json()["status"] == "CONFIRMED"


def test_evento_inexistente(client):
    assert client.get("/v1/events/9999").status_code == 404


def test_status_das_cameras(client):
    cams = client.get("/v1/cameras/status").json()
    assert {c["name"] for c in cams} == {"left", "right", "rear"}
    # A 4K do fundo tem de entregar mais pixel por caractere que as laterais.
    by = {c["name"]: c["px_per_char"] for c in cams}
    assert by["rear"] > by["left"]
