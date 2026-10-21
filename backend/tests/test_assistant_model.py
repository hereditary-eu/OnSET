"""assistant/assistant_model.py: the QueryGraph of the editor and Operations."""

import pytest

from assistant.assistant_model import (
    AssistantLink,
    AssistantSubject,
    Operation,
    Operations,
    QueryGraph,
    StringSubQuery,
    SubjectSubQuery,
    VectorSortSubQuery,
)
from model import Subject, SubjectLink

from fakes import dbo


def subject(id, label=None):
    return AssistantSubject(id=id, uri=f"<urn:{id}>", label=label or id)


def link(id, from_id, to_id, label=None):
    return AssistantLink(id=id, uri=f"<urn:{id}>", label=label or id, from_subject_id=from_id, to_subject_id=to_id)


@pytest.fixture
def graph():
    return QueryGraph(
        subjects=[subject("a"), subject("b"), subject("c")],
        links=[link("ab", "a", "b"), link("bc", "b", "c"), link("ca", "c", "a")],
    )


def test_lookups(graph):
    assert graph.get_subject_by_id("b").id == "b"
    assert graph.get_subject_by_id("x") is None
    assert graph.has_subject("a") and not graph.has_subject("ab")
    assert graph.has_link("ab") and not graph.has_link("a")


def test_next_id_skips_subject_and_link_ids():
    graph = QueryGraph(subjects=[subject("ship_1")], links=[link("ship_2", "ship_1", "ship_1")])
    assert graph.next_id("ship_") == "ship_3"
    assert graph.next_subject_id() == "subject_1"
    assert graph.next_link_id() == "link_1"


def test_add_subject_assigns_id_from_label():
    graph = QueryGraph()
    graph.add_subject(AssistantSubject(uri=dbo("Ship"), label="Military Ship"))
    graph.add_subject(AssistantSubject(uri=dbo("Ship"), label="Military Ship", id=""))
    graph.add_subject(AssistantSubject(uri=dbo("Ship"), label="x", id="keep"))
    assert [s.id for s in graph.subjects] == ["military_ship_1", "military_ship_2", "keep"]


def test_add_link(graph):
    graph.add_link(AssistantLink(uri="<urn:p>", label="birth place", from_subject_id="a", to_subject_id="c"))
    assert graph.links[-1].id == "birth_place_1"
    with pytest.raises(AssertionError, match="already exists"):
        graph.add_link(link("ab", "a", "b"))
    with pytest.raises(AssertionError, match="from_subject_id x"):
        graph.add_link(link("xa", "x", "a"))
    with pytest.raises(AssertionError, match="to_subject_id x"):
        graph.add_link(link("ax", "a", "x"))


def test_remove_subject_cascades_links(graph):
    graph.remove_subject("a")
    assert [s.id for s in graph.subjects] == ["b", "c"]
    # both links touching "a" (outgoing and incoming) are gone
    assert [l.id for l in graph.links] == ["bc"]
    with pytest.raises(AssertionError):
        graph.remove_subject("a")


def test_remove_link(graph):
    graph.remove_link("bc")
    assert [l.id for l in graph.links] == ["ab", "ca"]
    assert len(graph.subjects) == 3
    with pytest.raises(AssertionError):
        graph.remove_link("bc")


def test_from_subject():
    ship = Subject(subject_id=dbo("Ship"), label="ship")
    assert AssistantSubject.from_subject(ship, id="s1") == AssistantSubject(uri=dbo("Ship"), label="ship", id="s1")
    # the label falls back to the id
    assert AssistantSubject.from_subject(Subject(subject_id="x", label="")).label == "x"


def test_from_link(graph):
    subject_link = SubjectLink(
        link_id=1, label="", from_id=None, link_type="relation", to_id=None,
        to_proptype=None, property_id=dbo("homeport"), from_subject=None, to_subject=None,
    )
    created = AssistantLink.from_link(graph, subject_link, from_subject_id="a", to_subject_id="b", id="l")
    assert (created.uri, created.label, created.id) == (dbo("homeport"), dbo("homeport"), "l")
    assert (created.from_subject_id, created.to_subject_id) == ("a", "b")
    assert (created.from_subject_uri, created.from_subject_label) == ("<urn:a>", "a")
    assert (created.to_subject_uri, created.to_subject_label) == ("<urn:b>", "b")

    with pytest.raises(ValueError):
        AssistantLink.from_link(graph, subject_link, from_subject_id="a", to_subject_id="x")
    incomplete = AssistantLink.from_link(graph, subject_link, "a", "x", force_complete=False)
    assert incomplete.from_subject_label == "a" and incomplete.to_subject_uri is None


def test_subqueries_discriminated_by_type():
    parsed = AssistantSubject.model_validate(
        {
            "uri": "u",
            "label": "l",
            "subqueries": [
                {"type": "string", "property_id": "rdfs:label", "value": "x", "operator": "startswith"},
                {"type": "subject", "instance_id": "dbr:Bounty"},
                {"type": "vector_sort", "vector": [0.5]},
            ],
        }
    )
    assert [type(q) for q in parsed.subqueries] == [StringSubQuery, SubjectSubQuery, VectorSortSubQuery]
    assert parsed.subqueries[2].input_state.image is None


def test_operations_round_trip():
    ops = Operations(
        operations=[
            Operation(operation="add", data=link("ab", "a", "b")),
            Operation(operation="remove", data=subject("a")),
        ]
    )
    parsed = Operations.model_validate_json(ops.model_dump_json())
    assert isinstance(parsed.operations[0].data, AssistantLink)
    assert isinstance(parsed.operations[1].data, AssistantSubject)
    assert parsed == ops
