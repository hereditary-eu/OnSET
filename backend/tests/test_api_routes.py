"""REST routes of api/app.py and api/router/* with a FakeManMan (in-memory ontology, stub search)."""

import sys

import pytest

from assistant.assistant_model import Operations, QueryGraph

from fakes import DBO, RES, dbo

# the constraint and depth defaults of the panel (eval_config.ProgressiveConfig)
CONSTRAINTS = {"sample_constraints": False, "constraint_sample_size": 8, "max_constraint_sample_size": 64, "numeric_percentiles": [10, 25, 50, 75, 90], "categorical_samples": 3,
               "max_depth": 3, "default_branching": 4, "max_branching": 16, "child_sample_size": 12, "max_total_queries": 400}


def test_root(raw_client):
    assert raw_client.get("/").json() == "Welcome to the Ontology Provenance API"


def test_configs(raw_client):
    assert raw_client.get("/configs").json() == [
        {"id": "dbpedia", "name": "DBpedia", "description": "Test DBpedia", "multimodal": True, "default": True},
        {"id": "oma", "name": "OMA", "description": "Test OMA", "multimodal": False, "default": False},
    ]


def test_configs_default_from_env(raw_client, monkeypatch):
    from eval_config import load_config_file
    from conftest import TESTS_DIR

    # api/__init__.py star-imports app.py, so "api.app" is the FastAPI object
    app_module = sys.modules["api.app"]

    monkeypatch.setenv("ONSET_TEST_DEFAULT", "oma")
    config = load_config_file.__wrapped__(TESTS_DIR / "data" / "config.json")
    monkeypatch.setattr(app_module, "CONFIG_FILE", config)
    assert [c["default"] for c in raw_client.get("/configs").json()] == [False, True]


def test_ontology_config(client):
    assert client.get("/dbpedia/ontology/config").json() == {
        "id": "dbpedia",
        "name": "DBpedia",
        "description": "Test DBpedia",
        "multimodal": {
            "encoding_model": "clip-ViT-B-32",
            "image_vector_properties": ["dbo:thumbnail_embedding"],
            "image_properties": ["dbo:thumbnail"],
            "image_types": ["dbo:Image"],
        },
        "progressive": {"default_sample_size": 48, "max_sample_size": 256, "count_limit": 1_000_000, **CONSTRAINTS},
    }


def test_subject(client):
    subject = client.get("/dbpedia/classes/subjects", params={"subject_id": f"{DBO}Ship"}).json()
    assert (subject["subject_id"], subject["label"], subject["instance_count"]) == (dbo("Ship"), "ship", 2)
    assert "rdfs:subClassOf" in subject["spos"]


def test_class_hierarchy(client):
    roots = client.get("/dbpedia/classes/roots").json()
    assert {r["subject_id"] for r in roots} == {dbo("Vehicle"), dbo("Place"), dbo("Person")}
    subclasses = client.get("/dbpedia/classes/subclasses", params={"cls": dbo("Ship")}).json()
    assert [s["subject_id"] for s in subclasses] == [dbo("Warship")]


def test_most_generic(client):
    response = client.post(
        "/dbpedia/classes/parents/most_generic",
        json={"cls": dbo("Warship"), "out_link_ids": [dbo("homeport")], "in_link_ids": []},
    )
    assert response.json()["subject_id"] == dbo("Ship")


def test_instances(client):
    named = client.get("/dbpedia/classes/instances", params={"cls": dbo("Ship")}).json()
    assert {n["subject_id"] for n in named} == {f"<{RES}Bounty>", f"<{RES}Victory>"}
    found = client.get("/dbpedia/classes/instances/search", params={"cls": dbo("Ship"), "q": "bounty"}).json()
    assert [f["label"] for f in found] == ["Bounty"]
    properties = client.get("/dbpedia/classes/instances/properties", params={"instance_id": f"{RES}Bounty"}).json()
    assert properties[dbo("homeport")]["values"][0]["label"] == "England"


def test_links(client):
    link = client.get("/dbpedia/classes/links", params={"link_id": dbo("homeport")}).json()
    assert (link["from_id"], link["to_id"], link["instance_count"]) == (dbo("Ship"), dbo("Country"), 42)
    relations = client.get("/dbpedia/classes/relations", params={"q": "homeport"}).json()
    assert [r["property_id"] for r in relations] == [dbo("homeport")]


def test_search(client, fake_manman):
    results = client.post("/dbpedia/classes/search", json={"q": "ship", "type": "subject"}).json()["results"]
    assert results[0]["subject"]["subject_id"] == dbo("Ship")
    assert fake_manman.guidance_man.queries[-1].q == "ship"
    # the body is optional
    assert client.post("/dbpedia/classes/subclasses/search").status_code == 200


def test_assistant_is_cached(client, fake_manman):
    graph = QueryGraph().model_dump(mode="json")
    for _ in range(2):
        response = client.post("/dbpedia/classes/search/assistant", params={"q": "add a ship"}, json=graph)
        assert Operations.model_validate(response.json()) == Operations()
    assert len(fake_manman.assistant_runs) == 1
    assert fake_manman.assistant_runs[0][0] == "add a ship"


def test_llm_examples(client):
    examples = client.get("/dbpedia/classes/search/llm/examples").json()
    assert examples[0]["message"] == "the homeport of a ship"


def test_topics(client):
    root = client.get("/dbpedia/topics/root").json()
    assert root["topic"] == "root" and root["sub_topics"][0]["topic"] == "Ships"


def test_sparql(client):
    # values are made readable by q_to_df_values (wrapped/prefixed IRIs)
    query = f"SELECT ?s WHERE {{ ?s a <{DBO}Country> }}"
    assert client.post("/dbpedia/sparql", json={"query": query}).json() == [{"s": f"<{RES}England>"}]
    bindings = client.get("/dbpedia/sparql", params={"query": query}).json()
    assert bindings == {"results": {"bindings": [{"s": f"<{RES}England>"}]}}


def test_nlp_embeddings(client):
    assert client.get("/dbpedia/nlp/embeddings", params={"query": "a ship"}).json() == {"embedding": [6.0, 2.0, 1.0]}
    closest = client.post(
        "/dbpedia/nlp/embeddings/closest",
        json={"embedding": [1, 0], "query": None, "all_embeddings": [[0, 1], [1, 0.1], [1, 2, 3]], "n_closest": 1},
    ).json()
    assert closest[0]["index"] == 1


@pytest.mark.parametrize("alg", ["MDS", "smacof"])
def test_nlp_manifold(client, alg):
    embeddings = [[1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 0]]
    reduced = client.post("/dbpedia/nlp/embeddings/manifold", json={"embeddings": embeddings, "alg": alg}).json()
    assert len(reduced) == 4 and all(len(r) == 2 for r in reduced)


def test_validation_error(client):
    assert client.get("/dbpedia/classes/subjects").status_code == 422
