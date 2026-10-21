"""assistant/iterative_assistant.py with a stubbed llama.cpp model and an SQLite link store."""

import json

import numpy as np
import pytest
from llama_cpp import LlamaGrammar
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from assistant.assistant_model import (
    AssistantLink,
    AssistantSubject,
    OperationType,
    QueryGraph,
    StringSubQuery,
    VectorSortSubQuery,
)
from assistant.iterative_assistant import IterativeAssistant, LinkCandidate, OperationCandidates
from explorative.exp_model import N_EMBEDDINGS, RETURN_TYPE, BasePostgres, FuzzyQueryResults, SubjectInDB, SubjectLinkDB

from fakes import StubGuidance, dbo

HOMEPORT_KEY = "homeport|ship|country"


class StubLlama:
    """``create_chat_completion`` returning canned (grammar-conforming) JSON."""

    def __init__(self, content: dict | None = None):
        self.content = content or {"operations": []}
        self.calls = []

    def create_chat_completion(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        return {"choices": [{"message": {"role": "assistant", "content": json.dumps(self.content)}}]}


def link_store():
    """In-memory replacement of the Postgres subject/link tables."""
    engine = create_engine("sqlite://")
    BasePostgres.metadata.create_all(engine)
    zeros = np.zeros(N_EMBEDDINGS)
    with Session(engine) as session:
        for name, label in [("Ship", "ship"), ("Country", "country")]:
            session.add(SubjectInDB(subject_id=dbo(name), label=label, subject_type="class", embedding=zeros))
        session.add_all(
            [
                SubjectLinkDB(link_id=1, from_id=dbo("Ship"), to_id=dbo("Country"), link_type="relation",
                              property_id=dbo("homeport"), label="homeport"),
                SubjectLinkDB(link_id=2, from_id=dbo("Ship"), to_id=None, link_type="property",
                              to_proptype="xsd:double", property_id=dbo("length"), label="length"),
            ]
        )
        session.commit()
    return engine


@pytest.fixture
def guidance(ontology):
    guidance = StubGuidance(ontology)
    guidance.engine = link_store()
    guidance.llama_model = StubLlama()
    return guidance


@pytest.fixture
def assistant(guidance):
    return IterativeAssistant(guidance=guidance)


def ship_graph(with_country=False):
    graph = QueryGraph(subjects=[AssistantSubject(id="node_1", uri=dbo("Ship"), label="ship")])
    if with_country:
        graph.subjects.append(AssistantSubject(id="node_2", uri=dbo("Country"), label="country"))
        graph.links.append(AssistantLink(id="l1", uri=dbo("homeport"), label="homeport",
                                         from_subject_id="node_1", to_subject_id="node_2"))
    return graph


def op(operation, **data):
    return {"operations": [{"operation": operation, "data": data}]}


def test_candidates_from_search(assistant, guidance):
    candidates = assistant._IterativeAssistant__candidates("ship with a homeport")
    assert candidates.subjects == {"ship": dbo("Ship")}
    assert list(candidates.links) == [HOMEPORT_KEY]
    assert candidates.links[HOMEPORT_KEY].uri == dbo("homeport")
    query = guidance.queries[-1]
    assert query.type == RETURN_TYPE.BOTH and query.limit == assistant.top_k


def test_constrained_model_only_allows_candidates(assistant):
    candidates = assistant._IterativeAssistant__candidates("ship")
    model = assistant._IterativeAssistant__build_constrained_model(candidates, QueryGraph())
    parsed = model.model_validate(op("add", kind="link", link=HOMEPORT_KEY, from_subject="a", to_subject="b"))
    assert parsed.operations[0].data.link.value == HOMEPORT_KEY
    parsed = model.model_validate(op("add", kind="subject", subject="ship", id="a"))
    assert parsed.operations[0].data.subject.value == "ship"
    with pytest.raises(ValidationError):
        model.model_validate(op("add", kind="link", link="commander|ship|person", from_subject="a", to_subject="b"))
    with pytest.raises(ValidationError):
        model.model_validate(op("add", kind="subject", subject="unicorn", id="a"))


def test_constrained_model_falls_back_to_graph(assistant):
    graph = ship_graph(with_country=True)
    model = assistant._IterativeAssistant__build_constrained_model(OperationCandidates({}, {}), graph)
    # only the graph's own subjects and ids are allowed
    parsed = model.model_validate(op("remove", kind="subject", subject="country", id="node_2"))
    assert parsed.operations[0].data.id.value == "node_2"
    model.model_validate(op("remove", kind="link", link=HOMEPORT_KEY, from_subject="node_1", to_subject="node_2"))
    with pytest.raises(ValidationError):
        model.model_validate(op("remove", kind="subject", subject="country", id="node_9"))
    assert assistant._IterativeAssistant__build_constrained_model(OperationCandidates({}, {}), QueryGraph()) is None


def test_link_key():
    assert LinkCandidate(uri="u", label="a", from_label="b", to_label="c").key == "a|b|c"


def test_add_link_completes_missing_subject(assistant, guidance):
    guidance.llama_model.content = op("add", kind="link", link=HOMEPORT_KEY, from_subject="node_1", to_subject="node_2")
    ops = assistant.run_query("add a homeport", ship_graph())

    call = guidance.llama_model.calls[-1]
    assert isinstance(call["grammar"], LlamaGrammar)
    assert call["temperature"] == assistant.temperature and call["max_tokens"] == assistant.max_tokens
    assert call["messages"][0]["role"] == "system" and "add a homeport" in call["messages"][-1]["content"]

    link, added = [o.data for o in ops.operations]
    assert all(o.operation == OperationType.ADD for o in ops.operations)
    assert isinstance(link, AssistantLink)
    assert (link.uri, link.label) == (dbo("homeport"), "homeport")
    # from/to are the graph ids picked by the model
    assert (link.from_subject_id, link.to_subject_id) == ("node_1", "node_2")
    # node_2 did not exist: it is added as the range of the link
    assert added == AssistantSubject(uri=dbo("Country"), label="country", id="node_2")


def test_add_subject_resolves_subquery_property(assistant, guidance):
    guidance.llama_model.content = op(
        "add", kind="subject", subject="ship", id="node_5",
        subqueries=[{"type": "string", "property_id": "length", "value": "27"}],
    )
    ops = assistant.run_query("ships by length", QueryGraph())
    (operation,) = ops.operations
    subject = operation.data
    assert (subject.uri, subject.label, subject.id) == (dbo("Ship"), "ship", "node_5")
    assert isinstance(subject.subqueries[0], StringSubQuery)
    # the label the model chose is resolved to the property
    assert subject.subqueries[0].property_id == dbo("length")


def test_remove_subject_removes_its_links(assistant, guidance):
    guidance.llama_model.content = op("remove", kind="subject", subject="ship", id="node_1")
    ops = assistant.run_query("remove the ship", ship_graph(with_country=True))
    assert [(o.operation, type(o.data).__name__, o.data.id) for o in ops.operations] == [
        (OperationType.REMOVE, "AssistantSubject", "node_1"),
        (OperationType.REMOVE, "AssistantLink", "l1"),
    ]


def test_nothing_to_constrain_on(assistant, guidance):
    guidance.search_fuzzy = lambda query: FuzzyQueryResults(results=[])
    assert assistant.run_query("anything", QueryGraph()).operations == []
    assert guidance.llama_model.calls == []


def test_vector_payloads_are_not_sent(assistant, guidance):
    graph = ship_graph()
    graph.subjects[0].subqueries = [VectorSortSubQuery(vector=[0.123456] * 4, input_state={"image": "data:image/png;base64,AAAA"})]
    assistant.run_query("add a homeport", graph)
    prompt = guidance.llama_model.calls[-1]["messages"][-1]["content"]
    assert "0.123456" not in prompt and "base64" not in prompt
    # the caller's graph is untouched
    assert graph.subjects[0].subqueries[0].vector == [0.123456] * 4
