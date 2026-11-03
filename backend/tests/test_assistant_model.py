"""assistant/assistant_model.py: the QueryGraph of the editor and Operations."""

import pytest

from assistant.assistant_model import (
    AssistantLink,
    AssistantNumberConstraintType,
    AssistantSubject,
    AssistantSubQueryType,
    BooleanSubQuery,
    DateSubQuery,
    ImagePropSubQuery,
    InstancePropSubQuery,
    LinkQuantifier,
    LinkQuantifierType,
    LinkSemanticType,
    NumberSubQuery,
    Operation,
    Operations,
    QueryGraph,
    QueryPropSubQuery,
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


def full_graph():
    """An editor graph with every subquery kind and all link options."""
    return QueryGraph.model_validate(
        {
            "subjects": [
                {
                    "id": "node_1",
                    "uri": dbo("Ship"),
                    "label": "ship",
                    "subqueries": [
                        {"type": "query_prop", "id": "1", "property_id": "rdfs:label", "property_label": "label", "property_type": "xsd:string"},
                        {"type": "image_prop", "id": "2", "property_id": dbo("thumbnail"), "property_type": dbo("Image")},
                        {"type": "instance_prop", "id": "3", "property_id": dbo("length"), "value": "120"},
                        {"type": "subject", "id": "4", "instance_id": "dbr:Bounty", "instance_label": "Bounty", "property_type": "owl:Thing"},
                        {"type": "string", "id": "5", "property_id": "rdfs:label", "value": "HMS", "operator": "startswith"},
                        {"type": "number", "id": "6", "property_id": dbo("length"), "property_type": "xsd:double", "value": 42.5, "operator": "less"},
                        {"type": "boolean", "id": "7", "property_id": dbo("active"), "value": True},
                        {"type": "date", "id": "8", "property_id": dbo("completionDate"), "value": "1900-01-01T00:00:00.000Z", "operator": "equals"},
                        {
                            "type": "vector_sort", "id": "9", "property_id": dbo("thumbnail_embedding"),
                            "modality": "text", "direction": "ascending", "distance": "euclidean",
                            "vector": [0.25, -1.0], "input_state": {"text": "a frigate"},
                        },
                    ],
                },
                {"id": "node_2", "uri": dbo("Country"), "label": "country"},
            ],
            "links": [
                {"id": "l1", "uri": dbo("homeport"), "label": "homeport", "from_subject_id": "node_1", "to_subject_id": "node_2"},
                {
                    "id": "l2", "uri": dbo("country"), "label": "country", "from_subject_id": "node_2", "to_subject_id": "node_2",
                    "quantifier": {"type": "BETWEEN", "min": 1, "max": 3},
                },
                {"id": "l3", "uri": "", "label": "*", "from_subject_id": "node_1", "to_subject_id": "node_2", "allow_arbitrary": True},
                {
                    "id": "l4", "uri": dbo("thumbnail_embedding"), "label": "similar", "from_subject_id": "node_1",
                    "to_subject_id": "node_2", "semantic_link_type": "similarity",
                },
            ],
        }
    )


def test_full_graph_round_trip():
    graph = full_graph()
    # every subquery kind is covered
    assert {q.type for q in graph.subjects[0].subqueries} == set(AssistantSubQueryType)
    assert [type(q) for q in graph.subjects[0].subqueries] == [
        QueryPropSubQuery, ImagePropSubQuery, InstancePropSubQuery, SubjectSubQuery, StringSubQuery,
        NumberSubQuery, BooleanSubQuery, DateSubQuery, VectorSortSubQuery,
    ]
    # image/instance props are query props as well
    assert all(isinstance(q, QueryPropSubQuery) for q in graph.subjects[0].subqueries[:3])
    for dumped in (graph.model_dump_json(), graph.model_dump_json(exclude_none=True)):
        assert QueryGraph.model_validate_json(dumped) == graph

    subqueries = graph.subjects[0].subqueries
    assert subqueries[0].property_type == "xsd:string" and subqueries[0].property_label == "label"
    assert subqueries[2].value == "120"
    assert subqueries[5].operator == AssistantNumberConstraintType.LESS
    assert subqueries[8].input_state.text == "a frigate" and subqueries[8].vector == [0.25, -1.0]
    links = graph.links
    assert links[0].quantifier is None and links[0].allow_arbitrary is None and links[0].semantic_link_type is None
    assert links[1].quantifier == LinkQuantifier(type=LinkQuantifierType.BETWEEN, min=1, max=3)
    assert links[2].allow_arbitrary
    assert links[3].semantic_link_type == LinkSemanticType.SIMILARITY


def test_editor_defaults_stay_out_of_compact_dumps():
    # tool results/prompts are dumped with exclude_none, the old shapes must not change
    assert link("ab", "a", "b").model_dump(exclude_none=True) == {
        "uri": "<urn:ab>", "label": "ab", "id": "ab", "from_subject_id": "a", "to_subject_id": "b",
    }
    assert StringSubQuery(property_id="rdfs:label").model_dump(mode="json", exclude_none=True) == {
        "type": "string", "property_id": "rdfs:label", "value": "", "operator": "contains",
    }


def test_operations_carry_new_subquery_kinds():
    ops = Operations(operations=[Operation(operation="add", data=ImagePropSubQuery(property_id=dbo("thumbnail")))])
    parsed = Operations.model_validate_json(ops.model_dump_json())
    assert isinstance(parsed.operations[0].data, ImagePropSubQuery)
