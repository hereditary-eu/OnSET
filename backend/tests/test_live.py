"""Smoke tests against the real services, deselected by default.

Run with ``uv run pytest -m live`` once QLever, Postgres, Redis and the agent's
llama-server are up (see README.md); they use backend/config.json, not the
test configuration.
"""

import os

import pytest

from eval_config import DEFAULT_CONFIG_PATH, load_config_file

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def config():
    config_file = load_config_file(str(DEFAULT_CONFIG_PATH))
    return config_file.base(os.getenv("ONSET_LIVE_CONFIG", config_file.default))


def test_agent_llm_calls_tools(config):
    from agent.llm import AgentLLM, ResponseDone

    llm = AgentLLM(config.agent)
    tools = [
        {
            "type": "function",
            "name": "search_classes",
            "description": "Search ontology classes.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
            "strict": True,
        }
    ]
    messages = [{"role": "user", "content": "Use search_classes to find the class for ships."}]
    done = [e for e in llm.respond(messages, tools) if isinstance(e, ResponseDone)]
    assert done and any(item.get("type") == "function_call" for item in done[-1].output)


def test_redis_cache(config):
    from assistant.assistant_model import Operations
    from redis_cache import RedisCache

    cache = RedisCache(redis_url=config.redis_cache_url, model=Operations)
    cache.set("onset-live-test", Operations(), ttl=5)
    assert cache.get("onset-live-test") == Operations()


def test_sparql_endpoint(config):
    from rdflib import Graph
    from rdflib.plugins.stores.sparqlstore import SPARQLStore

    from ontology import OntologyConfig, OntologyManager

    store = SPARQLStore(config.sparql_endpoint, method="POST_FORM")
    ontology = OntologyManager(OntologyConfig(), Graph(store=store))
    assert ontology.get_root_classes()
