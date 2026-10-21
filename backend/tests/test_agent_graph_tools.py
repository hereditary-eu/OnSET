"""agent/graph_tools.py: ontology search and query graph editing tools."""

import pytest

from agent.graph_tools import GraphEditorTools, same_uri
from assistant.assistant_model import AssistantSubject, QueryGraph
from explorative.exp_model import RETURN_TYPE

from fakes import DBO, dbo


@pytest.fixture
def tools(ontology, guidance):
    return GraphEditorTools(ontology, guidance, retrieve_k=3)


def add(tools, name, **args):
    result = tools.call(name, args)
    assert result.ok, result.error
    return result.output


def test_definitions_cover_all_tools(tools):
    assert set(tools.tool_names()) == {
        "search_classes",
        "search_links",
        "add_subject",
        "add_link",
        "remove_subject",
        "remove_link",
        "get_query_graph",
    }
    search_links = {d["name"]: d for d in tools.definitions()}["search_links"]
    side = search_links["parameters"]["properties"]["side"]
    assert side["enum"] == ["source", "target"] and side["default"] == "source"


def test_same_uri():
    assert same_uri(f"{DBO}Ship", dbo("Ship"))
    assert not same_uri(dbo("Ship"), dbo("Country"))
    assert not same_uri(None, dbo("Ship"))


def test_search_classes_dedupes_and_uses_retrieve_k(tools, guidance):
    assert add(tools, "search_classes", query="ship") == [{"uri": dbo("Ship"), "label": "ship"}]
    query = guidance.queries[-1]
    assert query.type == RETURN_TYPE.SUBJECT and query.limit == 3
    assert add(tools, "search_classes", query="unicorn") == []


@pytest.mark.parametrize("side, from_id, to_id", [("source", dbo("Ship"), None), ("target", None, dbo("Ship"))])
def test_search_links_side(tools, guidance, side, from_id, to_id):
    links = add(tools, "search_links", query="homeport", class_uri=dbo("Ship"), side=side)
    query = guidance.queries[-1]
    assert (query.from_id, query.to_id) == (from_id, to_id)
    assert query.include_thing is False
    # results without a link are skipped
    assert [l["uri"] for l in links] == [dbo("homeport"), dbo("commander")]
    assert links[0] == {
        "uri": dbo("homeport"),
        "label": "homeport",
        "from_uri": dbo("Ship"),
        "from_label": "ship",
        "to_uri": dbo("Country"),
        "to_label": "country",
    }


def test_add_subject_records_details(tools):
    subject = add(tools, "add_subject", uri=dbo("Ship"))
    assert subject == {"uri": dbo("Ship"), "label": "ship", "id": "ship_1", "subqueries": []}
    # an unwrapped IRI works as well and gets the next id
    assert add(tools, "add_subject", uri=f"{DBO}Ship")["id"] == "ship_2"
    assert [s.id for s in tools.graph.subjects] == ["ship_1", "ship_2"]
    assert set(tools.details.subjects) == {"ship_1", "ship_2"}
    assert tools.details.subjects["ship_1"].subject_id == dbo("Ship")


def test_add_subject_unknown_uri(tools):
    result = tools.call("add_subject", {"uri": dbo("Unicorn")})
    assert not result.ok and "does not exist" in result.error
    assert tools.graph.subjects == [] and tools.details.subjects == {}


def test_add_link_from_search_results(tools):
    ship = add(tools, "add_subject", uri=dbo("Ship"))["id"]
    country = add(tools, "add_subject", uri=dbo("Country"))["id"]
    add(tools, "search_links", query="homeport", class_uri=dbo("Ship"))
    link = add(tools, "add_link", from_id=ship, to_id=country, uri=dbo("homeport"))
    assert link["id"] == "homeport_1"
    assert (link["from_subject_id"], link["to_subject_id"]) == (ship, country)
    assert (link["from_subject_uri"], link["to_subject_label"]) == (dbo("Ship"), "country")
    # the searched link (with its instance count) is kept as details
    assert tools.details.links["homeport_1"].instance_count == 42


def test_add_link_without_search_enriches_property(tools):
    ship = add(tools, "add_subject", uri=dbo("Ship"))["id"]
    person = add(tools, "add_subject", uri=dbo("Person"))["id"]
    link = add(tools, "add_link", from_id=ship, to_id=person, uri=f"{DBO}commander")
    details = tools.details.links[link["id"]]
    assert (details.from_id, details.to_id) == (dbo("Ship"), dbo("Person"))


@pytest.mark.parametrize(
    "args, error",
    [
        ({"from_id": "nope", "to_id": "ship_1", "uri": dbo("homeport")}, "Subject nope is not in the query graph"),
        ({"from_id": "ship_1", "to_id": "nope", "uri": dbo("homeport")}, "Subject nope is not in the query graph"),
        # a class is no property
        ({"from_id": "ship_1", "to_id": "ship_1", "uri": dbo("Country")}, "does not exist"),
        ({"from_id": "ship_1", "to_id": "ship_1", "uri": dbo("unknownProp")}, "does not exist"),
    ],
)
def test_add_link_errors(tools, args, error):
    add(tools, "add_subject", uri=dbo("Ship"))
    result = tools.call("add_link", args)
    assert not result.ok and error in result.error
    assert tools.graph.links == [] and tools.details.links == {}


def test_remove_subject_cascades_and_prunes_details(tools):
    ship = add(tools, "add_subject", uri=dbo("Ship"))["id"]
    country = add(tools, "add_subject", uri=dbo("Country"))["id"]
    add(tools, "add_link", from_id=ship, to_id=country, uri=dbo("homeport"))
    assert "success" in add(tools, "remove_subject", subject_id=country)
    assert [s.id for s in tools.graph.subjects] == [ship]
    assert tools.graph.links == []
    assert set(tools.details.subjects) == {ship} and tools.details.links == {}

    result = tools.call("remove_subject", {"subject_id": country})
    assert not result.ok and f"existing subjects: ['{ship}']" in result.error


def test_remove_link(tools):
    ship = add(tools, "add_subject", uri=dbo("Ship"))["id"]
    country = add(tools, "add_subject", uri=dbo("Country"))["id"]
    link = add(tools, "add_link", from_id=ship, to_id=country, uri=dbo("homeport"))["id"]
    add(tools, "remove_link", link_id=link)
    assert tools.graph.links == [] and tools.details.links == {}
    assert len(tools.graph.subjects) == 2
    result = tools.call("remove_link", {"link_id": link})
    assert not result.ok and "existing links: []" in result.error


def test_get_query_graph_and_details_for(tools):
    # elements synced from the editor have no details
    tools.graph = QueryGraph(subjects=[AssistantSubject(id="node_1", uri=dbo("Person"), label="person")])
    ship = add(tools, "add_subject", uri=dbo("Ship"))["id"]
    graph = add(tools, "get_query_graph")
    assert [s["id"] for s in graph["subjects"]] == ["node_1", ship]
    details = tools.details_for(tools.graph)
    assert set(details.subjects) == {ship} and details.links == {}


def test_prune_details_after_graph_replacement(tools):
    add(tools, "add_subject", uri=dbo("Ship"))
    tools.graph = QueryGraph()
    tools.prune_details()
    assert tools.details.subjects == {}
