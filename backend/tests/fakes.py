"""Offline stand-ins for the services a ManMan wires up.

- ``make_ontology``: a real ``OntologyManager`` over an in-memory rdflib graph
  (a tiny DBpedia-like ontology) instead of the QLever ``SPARQLStore``.
- ``StubGuidance``: the search side of ``GuidanceManager`` (no Postgres/embeddings).
- ``ScriptedLLM`` / ``BlockingLLM``: ``AgentLLMBase`` implementations that play
  back Responses API output items.
- ``FakeManMan``: just the attributes the routers touch.
"""

import json
import threading
from types import SimpleNamespace
from typing import Callable, Iterable

import numpy as np
from rdflib import Graph

from agent.llm import AgentLLMBase, LLMEvent, ReasoningDelta, ResponseDone, TextDelta
from agent.session import AgentSession, AgentSessionStore
from assistant.assistant_model import EnrichedEntitiesRelations, Operations
from assistant.progressive import ProgressiveSampler
from eval_config import AgentConfig, MultimodalConfig, ProgressiveConfig
from explorative.exp_model import RETURN_TYPE, FuzzyQueryResult, FuzzyQueryResults, Topic
from model import Subject, SubjectLink
from ontology import OntologyConfig, OntologyManager

DBO = "http://dbpedia.org/ontology/"
RES = "http://dbpedia.org/resource/"


def dbo(name: str) -> str:
    """Wrapped IRI of a dbo: term, as the OntologyManager renders it."""
    return f"<{DBO}{name}>"


ONTOLOGY_TTL = """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix dbo: <http://dbpedia.org/ontology/> .
@prefix dbr: <http://dbpedia.org/resource/> .

dbo:Vehicle a owl:Class ; rdfs:label "vehicle"@en, "Fahrzeug"@de .
dbo:Ship a owl:Class ; rdfs:subClassOf dbo:Vehicle ; rdfs:label "ship"@en .
dbo:Warship a owl:Class ; rdfs:subClassOf dbo:Ship ; rdfs:label "warship"@en .
dbo:Place a owl:Class ; rdfs:label "place"@en .
dbo:Country a owl:Class ; rdfs:subClassOf dbo:Place ; rdfs:label "country"@en .
dbo:Person a owl:Class ; rdfs:label "person"@en .

dbo:homeport a owl:ObjectProperty ; rdfs:label "homeport"@en ;
    rdfs:domain dbo:Ship ; rdfs:range dbo:Country .
dbo:commander a owl:ObjectProperty ; rdfs:label "commander"@en ;
    rdfs:domain dbo:Ship ; rdfs:range dbo:Person .
dbo:length a owl:DatatypeProperty ; rdfs:label "length"@en ;
    rdfs:domain dbo:Ship ; rdfs:range xsd:double .

dbr:Bounty a dbo:Ship, owl:NamedIndividual ; rdfs:label "Bounty"@en ;
    dbo:homeport dbr:England ; dbo:length "27.7"^^xsd:double .
dbr:Victory a dbo:Ship, dbo:Warship, owl:NamedIndividual ; rdfs:label "HMS Victory"@en ;
    dbo:homeport dbr:England .
dbr:England a dbo:Country ; rdfs:label "England"@en .
dbr:Bligh a dbo:Person ; rdfs:label "William Bligh"@en .
"""


def make_ontology(ttl: str = ONTOLOGY_TTL, **config) -> OntologyManager:
    # copy the triples without the turtle's prefixes: like the SPARQLStore of
    # a ManMan, only the core namespaces are bound, so IRIs render as <...>
    graph = Graph(bind_namespaces="core")
    graph += Graph().parse(data=ttl, format="turtle")
    return OntologyManager(OntologyConfig(**config), graph)


# --- search ---

CLASS_NAMES = {"ship": "Ship", "country": "Country", "person": "Person", "place": "Place"}


class StubGuidance:
    """``GuidanceManager.search_fuzzy`` over a fixed catalog, records the queries."""

    def __init__(self, ontology: OntologyManager):
        self.ontology = ontology
        self.queries = []

    def subject(self, name: str) -> Subject:
        return self.ontology.enrich_subject(dbo(name))

    def link(self, name: str, instance_count: int = 42) -> SubjectLink:
        link = self.ontology.enrich_subject(dbo(name)).to_link()
        link.link_id = 7
        link.link_type = "relation"
        link.instance_count = instance_count
        link.from_subject = self.ontology.enrich_subject(link.from_id)
        link.to_subject = self.ontology.enrich_subject(link.to_id)
        return link

    def search_fuzzy(self, query) -> FuzzyQueryResults:
        self.queries.append(query)
        if query.type == RETURN_TYPE.SUBJECT:
            name = CLASS_NAMES.get((query.q or "").lower())
            if name is None:
                return FuzzyQueryResults(results=[])
            # duplicates are collapsed by the tools
            subject = self.subject(name)
            return FuzzyQueryResults(
                results=[FuzzyQueryResult(subject=subject, score=0.1)] * 2
            )
        if query.type == RETURN_TYPE.LINK:
            return FuzzyQueryResults(
                results=[
                    FuzzyQueryResult(link=self.link("homeport"), score=0.1),
                    FuzzyQueryResult(link=self.link("commander", 3), score=0.2),
                    FuzzyQueryResult(link=None, subject=self.subject("Ship"), score=0.3),
                ]
            )
        return FuzzyQueryResults(
            results=[
                FuzzyQueryResult(subject=self.subject("Ship"), score=0.1),
                FuzzyQueryResult(link=self.link("homeport"), score=0.2),
            ]
        )

    # --- REST-only methods ---

    def search_subclasses(self, query):
        return self.search_fuzzy(query)

    def search_links(self, q, from_id, to_id):
        return [self.link("homeport")]

    def get_link(self, property_id):
        return self.link("homeport")

    def encode_query(self, query: str) -> np.ndarray:
        """Deterministic stand-in for the sentence embedding of ``query``."""
        return np.array([len(query), query.count(" ") + 1, 1.0])

    def get_topic_tree(self) -> Topic:
        leaf = Topic(
            topic_id=1,
            sub_topics=[],
            parent_topic_id=0,
            topic="Ships",
            count=2,
            subjects_ids=[dbo("Ship")],
            property_ids=[dbo("homeport")],
        )
        return Topic(
            topic_id=0,
            sub_topics=[leaf],
            parent_topic_id=None,
            topic="root",
            count=2,
            subjects_ids=[],
            property_ids=[],
        )


# --- Responses API output items ---


def function_call(call_id: str, name: str, **arguments) -> dict:
    return {
        "type": "function_call",
        "id": f"fc_{call_id}",
        "call_id": call_id,
        "name": name,
        "arguments": json.dumps(arguments),
        "status": "completed",
    }


def reasoning(item_id: str, text: str) -> dict:
    return {
        "type": "reasoning",
        "id": item_id,
        "summary": [],
        "content": [{"type": "reasoning_text", "text": text}],
    }


def message(item_id: str | None, text: str) -> dict:
    item = {
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": text}],
    }
    if item_id is not None:
        item["id"] = item_id
    return item


def tool_outputs(history: list[dict]) -> list[dict]:
    """The decoded function_call_outputs of a history."""
    return [
        json.loads(m["output"]) for m in history if m.get("type") == "function_call_output"
    ]


Response = Iterable[LLMEvent] | Callable[[list[dict]], Iterable[LLMEvent]]


class ScriptedLLM(AgentLLMBase):
    """Plays back one scripted response per call.

    A response is a list of events or a callable building them from the
    history (e.g. to reference graph ids returned by earlier tool calls).
    After the script is exhausted ``fallback`` is repeated, if set.
    """

    def __init__(self, responses: list[Response], fallback: Response | None = None):
        self.responses = list(responses)
        self.fallback = fallback
        self.calls: list[list[dict]] = []
        self.tools: list[list[dict]] = []

    def respond(self, messages, tools):
        # snapshot, the agent keeps appending to the history
        self.calls.append(json.loads(json.dumps(messages)))
        self.tools.append(tools)
        if self.responses:
            response = self.responses.pop(0)
        elif self.fallback is not None:
            response = self.fallback
        else:
            raise AssertionError("ScriptedLLM called more often than scripted")
        if callable(response):
            response = response(messages)
        yield from response


def final_answer(text: str, item_id: str = "msg_final") -> list[LLMEvent]:
    return [TextDelta(item_id, text), ResponseDone(output=[message(item_id, text)])]


def ship_scenario() -> list[Response]:
    """Add a ship with a homeport in a country: search, add subjects, search link, add link, answer."""

    def add_link(history):
        ids = [o["id"] for o in tool_outputs(history) if "id" in o]
        return [
            ResponseDone(
                output=[
                    function_call(
                        "c6", "add_link", from_id=ids[0], to_id=ids[1], uri=dbo("homeport")
                    )
                ]
            )
        ]

    return [
        [
            ReasoningDelta("rs_1", "The user wants a ship "),
            ReasoningDelta("rs_1", "with a homeport."),
            ResponseDone(
                output=[
                    reasoning("rs_1", "The user wants a ship with a homeport."),
                    function_call("c1", "search_classes", query="ship"),
                    function_call("c2", "search_classes", query="country"),
                ]
            ),
        ],
        [
            ResponseDone(
                output=[
                    function_call("c3", "add_subject", uri=dbo("Ship")),
                    function_call("c4", "add_subject", uri=dbo("Country")),
                ]
            )
        ],
        [
            ResponseDone(
                output=[
                    function_call(
                        "c5", "search_links", query="homeport", class_uri=dbo("Ship"), side="source"
                    )
                ]
            )
        ],
        add_link,
        [
            # inline <think> tags split across deltas, then the answer
            *(
                TextDelta("msg_1", d)
                for d in [
                    "<thi",
                    "nk>Done, summarise",
                    ".</th",
                    "ink>Added a ship ",
                    "with a homeport in a country.",
                ]
            ),
            ResponseDone(
                output=[
                    message(
                        "msg_1",
                        "<think>Done, summarise.</think>Added a ship with a homeport in a country.",
                    )
                ]
            ),
        ],
    ]


class BlockingLLM(AgentLLMBase):
    """Blocks every response until ``release()``, to hold a turn open.

    ``entered`` is set while a response is waiting. Each released response
    calls a tool (``get_query_graph``) so the turn keeps going until cancelled,
    unless ``answer`` is set, which ends the turn.
    """

    def __init__(self, answer: str | None = None, timeout: float = 10):
        self.entered = threading.Event()
        self._release = threading.Event()
        self.answer = answer
        self.timeout = timeout
        self.calls = 0

    def release(self):
        self._release.set()

    def respond(self, messages, tools):
        self.calls += 1
        self.entered.set()
        assert self._release.wait(self.timeout), "BlockingLLM was never released"
        if self.answer is not None:
            yield from final_answer(self.answer)
        else:
            yield ResponseDone(output=[function_call(f"b{self.calls}", "get_query_graph")])


# --- ManMan ---


class DictCache:
    """In-memory ``RedisCache``."""

    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value

    def get_or_set(self, key, compute):
        if key not in self.data:
            self.data[key] = compute()
        return self.data[key]


class FakeManMan:
    """The parts of ``api.config.ManMan`` the routers use, without any service."""

    def __init__(
        self,
        llm: AgentLLMBase | None = None,
        agent_config: AgentConfig | None = None,
        config_id: str = "dbpedia",
    ):
        self.config_id = config_id
        self.ontology_manager = make_ontology()
        self.guidance_man = StubGuidance(self.ontology_manager)
        self.llm = llm if llm is not None else ScriptedLLM(ship_scenario())
        self.agent_config = agent_config or AgentConfig(max_steps=8)
        self.agent_sessions = AgentSessionStore(
            lambda session_id: AgentSession(
                session_id,
                llm=self.llm,
                ontology_manager=self.ontology_manager,
                guidance=self.guidance_man,
                config=self.agent_config,
            )
        )
        self.assistant_cache = DictCache()
        # counts run on the in-memory ontology
        self.progressive_config = ProgressiveConfig()
        self.progressive = ProgressiveSampler(self.ontology_manager, self.progressive_config)
        self.progressive_cache = DictCache()
        self.assistant_runs = []
        self.iterative_assistant = SimpleNamespace(
            run_query=lambda q, graph: self.assistant_runs.append((q, graph)) or Operations()
        )
        self.llm_query = SimpleNamespace(
            get_examples=lambda: [EnrichedEntitiesRelations(message="the homeport of a ship")]
        )
        self.db_config = SimpleNamespace(
            name="DBpedia", description="Test DBpedia", progressive=self.progressive_config
        )
        self.config = SimpleNamespace(multimodal_config=MultimodalConfig())
