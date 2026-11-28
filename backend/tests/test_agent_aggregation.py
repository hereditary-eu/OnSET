"""agent/graph_tools.py: add_property and set_aggregation (GROUP BY/aggregates of the query graph),
and how their changes reach the frontend (protocol.diff_graphs)."""

from agent.protocol import diff_graphs
from assistant.assistant_model import AggregateFunction, QueryGraph
from assistant.sparql_gen import SparqlOptions

from fakes import dbo
from test_agent_constraints import error, guidance, ok, ontology, ship, tools  # noqa: F401 (fixtures)


def port(tools, ship):
    port_id = ok(tools, "add_subject", uri=dbo("Place"))["id"]
    ok(tools, "add_link", from_id=ship, to_id=port_id, uri=dbo("homeport"))
    return port_id


def test_add_property(tools, ship):
    added = ok(tools, "add_property", subject_id=ship, property_uri=dbo("length"))
    assert added == {
        "type": "query_prop",
        "id": "length_1",
        "property_id": dbo("length"),
        "property_label": "length",
        "property_type": "xsd:double",
    }
    assert "already returns length" in error(tools, "add_property", subject_id=ship, property_uri=dbo("length"))
    assert "no datatype property" in error(tools, "add_property", subject_id=ship, property_uri=dbo("homeport"))


def test_set_aggregation_counts_per_group(tools, ship):
    port_id = port(tools, ship)
    before = tools.graph.model_copy(deep=True)
    grouped = ok(tools, "set_aggregation", subject_id=port_id, aggregation="group")
    assert (grouped["subject_id"], grouped["uri"], grouped["group_by"]) == (port_id, dbo("Place"), True)
    assert "aggregate" not in grouped
    counted = ok(tools, "set_aggregation", subject_id=ship, aggregation="count")
    assert counted["aggregate"] == "count" and "group_by" not in counted
    ship_subject = tools.graph.get_subject_by_id(ship)
    assert ship_subject.aggregate == AggregateFunction.COUNT and not ship_subject.group_by

    # the subjects' changes are part of the tool call's change
    change = diff_graphs(before, tools.graph)
    assert not change.empty
    assert {s.id for s in change.updated} == {ship, port_id}

    options = SparqlOptions.from_ontology(tools.ontology_manager)
    query = tools.graph.to_sparql(options)
    assert f"GROUP BY ?{port_id}" in query
    assert f"(COUNT(?{ship}__agg) AS ?{ship})" in query
    rows = tools.ontology_manager.q_to_df(query)
    assert len(rows) > 0

    # reset
    ok(tools, "set_aggregation", subject_id=ship, aggregation="none")
    ok(tools, "set_aggregation", subject_id=port_id, aggregation="none")
    assert "GROUP BY" not in tools.graph.to_sparql(options)


def test_set_aggregation_of_a_property(tools, ship):
    length = ok(tools, "add_property", subject_id=ship, property_uri=dbo("length"))["id"]
    motto = ok(tools, "add_property", subject_id=ship, property_uri=dbo("motto"))["id"]
    before = tools.graph.model_copy(deep=True)
    result = ok(tools, "set_aggregation", subject_id=ship, aggregation="avg", constraint_id=length)
    assert result == {"subject_id": ship, "id": length, "type": "query_prop", "property_id": dbo("length"), "aggregate": "avg"}
    # a property change is a remove + add of the subquery
    change = diff_graphs(before, tools.graph)
    assert [(c.operation, c.subquery.id, c.subquery.aggregate) for c in change.subqueries] == [
        ("remove", length, None), ("add", length, AggregateFunction.AVG),
    ]
    # the aggregates fit the value type
    assert "does not apply to text values" in error(
        tools, "set_aggregation", subject_id=ship, aggregation="avg", constraint_id=motto
    )
    assert "does not apply to the subject's instances" in error(tools, "set_aggregation", subject_id=ship, aggregation="sum")
    assert "has no property or constraint" in error(
        tools, "set_aggregation", subject_id=ship, aggregation="avg", constraint_id="nope"
    )
    ok(tools, "set_aggregation", subject_id=ship, aggregation="group", constraint_id=motto)
    query = tools.graph.to_sparql(SparqlOptions.from_ontology(tools.ontology_manager))
    assert "AVG(" in query and "GROUP BY ?sq_" in query
    tools.ontology_manager.q_to_df(query)


def test_instance_restriction_cannot_be_aggregated(tools, ship):
    restriction = ok(tools, "restrict_to_instance", subject_id=ship, instance="Victoria")["id"]
    assert "has no values" in error(tools, "set_aggregation", subject_id=ship, aggregation="count", constraint_id=restriction)


def test_unset_fields_are_left_out(tools, ship):
    # the editor defaults are not dumped, so payloads without aggregation stay the same
    dumped = QueryGraph.model_validate(tools.graph.model_dump()).model_dump()
    assert "group_by" not in dumped["subjects"][0] and "aggregate" not in dumped["subjects"][0]
