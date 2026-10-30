"""api/config.py: ManMan registry and the per-request config resolution."""

import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import api.config
from agent.llm import AgentLLM
from agent.session import AgentSessionStore
from api.config import ManMan, ManManRegistry
from eval_config import CONFIG_FILE, MultimodalConfig

from fakes import StubGuidance, make_ontology

# the constraint defaults of the panel (eval_config.ProgressiveConfig)
CONSTRAINTS = {"sample_constraints": False, "constraint_sample_size": 8, "max_constraint_sample_size": 64, "numeric_percentiles": [10, 25, 50, 75, 90], "categorical_samples": 3}


class LightManMan:
    """Stands in for ManMan, whose start_systems needs every service."""

    created = []

    def __init__(self, config_id, eval_cfg):
        self.config_id = config_id
        self.db_config = eval_cfg
        self.config = SimpleNamespace(multimodal_config=eval_cfg.multimodal_config or MultimodalConfig())
        LightManMan.created.append(config_id)


@pytest.fixture
def light(monkeypatch):
    LightManMan.created = []
    monkeypatch.setattr(api.config, "ManMan", LightManMan)
    return LightManMan


def test_registry_knows_configs(light):
    registry = ManManRegistry()
    assert "dbpedia" in registry and "oma" in registry
    assert "nonexistent" not in registry
    with pytest.raises(KeyError):
        registry.get("nonexistent")
    assert light.created == []


def test_registry_creates_lazily_once(light):
    registry = ManManRegistry()
    manman = registry.get("dbpedia")
    assert registry.get("dbpedia") is manman
    assert manman.db_config == CONFIG_FILE.base("dbpedia")
    assert light.created == ["dbpedia"]


def test_registry_lru_eviction(light):
    registry = ManManRegistry(max_loaded=1)
    dbpedia = registry.get("dbpedia")
    registry.get("oma")
    assert list(registry._loaded) == ["oma"]
    assert registry.get("dbpedia") is not dbpedia
    assert light.created == ["dbpedia", "oma", "dbpedia"]


def test_registry_unlimited(light):
    registry = ManManRegistry(max_loaded=0)
    registry.get("dbpedia")
    registry.get("oma")
    registry.get("dbpedia")
    assert list(registry._loaded) == ["oma", "dbpedia"]


def test_registry_concurrent_get_builds_once(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    created = []

    class SlowManMan(LightManMan):
        def __init__(self, config_id, eval_cfg):
            created.append(config_id)
            started.set()
            release.wait(5)
            super().__init__(config_id, eval_cfg)

    monkeypatch.setattr(api.config, "ManMan", SlowManMan)
    registry = ManManRegistry()
    results = []
    threads = [threading.Thread(target=lambda: results.append(registry.get("dbpedia"))) for _ in range(3)]
    for thread in threads:
        thread.start()
    assert started.wait(5)
    # other configurations are not blocked by a slow construction
    monkeypatch.setattr(api.config, "ManMan", LightManMan)
    assert registry.get("oma").config_id == "oma"
    release.set()
    for thread in threads:
        thread.join(5)
    assert created == ["dbpedia"]
    assert len({id(r) for r in results}) == 1


def test_get_manman_uses_registry(app, light, monkeypatch):
    monkeypatch.setattr(api.config, "REGISTRY", ManManRegistry())
    client = TestClient(app)
    response = client.get("/dbpedia/ontology/config")
    assert response.status_code == 200
    assert response.json() == {
        "id": "dbpedia",
        "name": "DBpedia",
        "description": "Test DBpedia",
        "multimodal": MultimodalConfig(encoding_model="clip-test").model_dump(),
        # tests/data/config.json: defaults <- dbpedia
        "progressive": {"default_sample_size": 32, "max_sample_size": 64, "count_limit": 1000, **CONSTRAINTS},
    }
    oma = client.get("/oma/ontology/config").json()
    assert oma["name"] == "OMA"
    assert oma["progressive"] == {"default_sample_size": 32, "max_sample_size": 128, "count_limit": 1000, **CONSTRAINTS}
    client.get("/dbpedia/ontology/config")
    assert light.created == ["dbpedia", "oma"]


def test_unknown_config_http_404(raw_client):
    response = raw_client.get("/nonexistent/classes/roots")
    assert response.status_code == 404
    assert response.json() == {"detail": "Unknown configuration 'nonexistent'"}


def test_unknown_config_websocket_1008(raw_client):
    with pytest.raises(WebSocketDisconnect) as error:
        with raw_client.websocket_connect("/nonexistent/agent/ws"):
            pass
    assert error.value.code == 1008


def test_manman_agent_services_are_lazy_and_cached():
    # bypass start_systems (it connects to QLever/Postgres/Redis)
    manman = ManMan.__new__(ManMan)
    manman.db_config = CONFIG_FILE.base("dbpedia")
    manman.ontology_manager = make_ontology()
    manman.guidance_man = StubGuidance(manman.ontology_manager)

    assert isinstance(manman.agent_llm, AgentLLM) and manman.agent_llm is manman.agent_llm
    assert manman.agent_llm.config.base_url == "http://llm.invalid/v1"
    store = manman.agent_sessions
    assert isinstance(store, AgentSessionStore) and store is manman.agent_sessions
    session, resumed = store.get_or_create("s")
    assert not resumed and session.agent.llm is manman.agent_llm
    assert session.tools.ontology_manager is manman.ontology_manager
    assert session.agent.max_steps == manman.db_config.agent.max_steps


@pytest.mark.live
def test_manman_starts_against_services():
    """Builds a real ManMan for the default configuration of backend/config.json."""
    from eval_config import DEFAULT_CONFIG_PATH, load_config_file

    config = load_config_file(str(DEFAULT_CONFIG_PATH))
    manman = ManMan(config.default, config.base(config.default))
    assert manman.ontology_manager.get_root_classes()
