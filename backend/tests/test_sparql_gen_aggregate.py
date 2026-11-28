"""assistant/sparql_gen.py: GROUP BY/aggregate queries of grouped or aggregated subjects/subqueries
(the editor's NodeLinkRepository.aggregationPlan), checked as text, parsed and run with rdflib."""

import pytest
from rdflib import Graph

from assistant.assistant_model import (
    AggregateFunction,
    AssistantLink,
    AssistantSubject,
    NumberSubQuery,
    QueryGraph,
    QueryPropSubQuery,
    StringSubQuery,
    VectorSortSubQuery,
)
from assistant.sparql_gen import (
    AGGREGATES_OF,
    aggregate_expression,
    aggregate_kind,
    generate_sparql,
    rename_variables,
)

from test_sparql_gen import DATA_TTL, MULTIMODAL, NAMESPACES, parse

TENSOR = "<https://w3id.org/rdf-tensor/datatypes#NumericDataTensor>"


@pytest.fixture(scope="module")
def data():
    return Graph().parse(data=DATA_TTL, format="turtle")


def ships_at_ports(ship: dict | None = None, port: dict | None = None, subqueries=None) -> QueryGraph:
    return QueryGraph(
        subjects=[
            AssistantSubject(id="ship", uri="dbo:Ship", label="Ship", subqueries=subqueries or [], **(ship or {})),
            AssistantSubject(id="port", uri="dbo:Place", label="Place", **(port or {})),
        ],
        links=[AssistantLink(id="home", uri="dbo:homeport", label="homeport", from_subject_id="ship", to_subject_id="port")],
    )


def length(**fields) -> QueryPropSubQuery:
    return QueryPropSubQuery(id="len", property_id="dbo:length", property_type="xsd:double", **fields)


def run(data, query: str) -> list[dict[str, str]]:
    return [{str(k): v.toPython() for k, v in row.asdict().items()} for row in data.query(query)]


def test_without_flags_no_aggregation():
    unset = generate_sparql(ships_at_ports(subqueries=[length()]), namespaces=NAMESPACES)
    defaults = generate_sparql(
        ships_at_ports({"group_by": False}, {"aggregate": None}, [length(group_by=False)]), namespaces=NAMESPACES
    )
    assert unset.query == defaults.query
    assert "GROUP BY" not in unset.query and "__agg" not in unset.query
    assert all(not o.grouped and o.aggregate is None for o in unset.outputs)


def test_count_per_group(data):
    result = generate_sparql(
        ships_at_ports({"aggregate": "count"}, {"group_by": True}), namespaces=NAMESPACES, language=None
    )
    query = result.query
    # the counted subject keeps its column name and has no label; the grouped one's label is
    # looked up after the grouping and sampled
    assert query.split("WHERE")[0].endswith("SELECT DISTINCT ?ship ?port (SAMPLE(?lbl_port__agg) AS ?lbl_port) ")
    assert "SELECT (COUNT(?ship__agg) AS ?ship) ?port WHERE {" in query
    assert "?ship__agg dbo:homeport ?port ." in query
    assert "lbl_ship" not in query
    assert "\n    GROUP BY ?port\n  }\n  OPTIONAL { ?port rdfs:label ?lbl_port__agg . }" in query
    assert query.endswith("}\nGROUP BY ?ship ?port\nORDER BY ?lbl_port")
    assert result.variables == ["ship", "port", "lbl_port"]
    assert [o.aggregate for o in result.outputs] == [AggregateFunction.COUNT, None, AggregateFunction.SAMPLE]
    assert [o.grouped for o in result.outputs] == [False, True, False]
    parse(query)
    rows = {r["lbl_port"]: r["ship"] for r in run(data, query)}
    assert rows == {"Portsmouth": 3, "Plymouth": 1}


def test_labels_language_filter(data):
    query = generate_sparql(ships_at_ports({"aggregate": "count"}, {"group_by": True}), namespaces=NAMESPACES).query
    assert 'OPTIONAL { ?port rdfs:label ?lbl_port__agg . FILTER(LANG(?lbl_port__agg) = "en" || LANG(?lbl_port__agg) = "") }' in query
    parse(query)
    assert {r["lbl_port"]: r["ship"] for r in run(data, query)} == {"Portsmouth": 3, "Plymouth": 1}


def test_numeric_aggregate_and_default_count(data):
    graph = ships_at_ports(port={"group_by": True}, subqueries=[length(aggregate="avg")])
    result = generate_sparql(graph, namespaces=NAMESPACES, language=None)
    query = result.query
    # the ship is neither grouped nor aggregated: counted, without a label (labels would
    # multiply the solutions: Bounty has two)
    assert "(COUNT(DISTINCT ?ship__agg) AS ?ship)" in query
    assert "lbl_ship" not in query
    assert "(AVG(?sq_len__agg) AS ?sq_len)" in query
    assert result.variables == ["ship", "port", "lbl_port", "sq_len"]
    parse(query)
    rows = run(data, query)
    assert len(rows) == 1
    assert float(rows[0]["sq_len"]) == pytest.approx(48.5)
    assert rows[0]["lbl_port"] == "Portsmouth"
    assert int(rows[0]["ship"]) == 2


def test_grouped_property_samples_its_subject():
    # avg length of the ships per place label: the place is sampled (its label is the group),
    # the ships are counted
    graph = ships_at_ports(subqueries=[length(aggregate="avg")])
    graph.subjects[1].subqueries = [
        QueryPropSubQuery(id="name", property_id="rdfs:label", property_type="xsd:string", group_by=True)
    ]
    query = generate_sparql(graph, namespaces=NAMESPACES, language=None).query
    assert "(COUNT(DISTINCT ?ship__agg) AS ?ship)" in query
    assert "(SAMPLE(?port__agg) AS ?port)" in query
    assert "(AVG(?sq_len__agg) AS ?sq_len)" in query
    assert "GROUP BY ?sq_name" in query
    parse(query)


def test_grouped_filter_is_projected(data):
    graph = QueryGraph(
        subjects=[
            AssistantSubject(
                id="ship",
                uri="dbo:Ship",
                label="Ship",
                aggregate="count_distinct",
                subqueries=[NumberSubQuery(id="len", property_id="dbo:length", value=10, operator="greater", group_by=True)],
            )
        ]
    )
    result = generate_sparql(graph, namespaces=NAMESPACES)
    assert "(COUNT(DISTINCT ?ship__agg) AS ?ship)" in result.query
    assert "GROUP BY ?sq_len" in result.query
    assert "FILTER(?sq_len > 10)" in result.query
    assert result.var_of("property", "len") == "sq_len"
    parse(result.query)
    assert sorted(r["ship"] for r in run(data, result.query)) == [1, 1]
    # without the flag, the filter is no output (as before)
    plain = generate_sparql(
        QueryGraph(subjects=[AssistantSubject(id="ship", uri="dbo:Ship", label="Ship", subqueries=[
            NumberSubQuery(id="len", property_id="dbo:length", value=10, operator="greater")])]),
        namespaces=NAMESPACES,
    )
    assert "sq_len" not in plain.query.split("WHERE")[0]


def test_group_concat_and_literals_untouched(data):
    graph = ships_at_ports(
        port={"group_by": True},
        ship={"aggregate": "group_concat"},
        subqueries=[StringSubQuery(id="name", property_id="rdfs:label", value='?ship "x"', operator="!=")],
    )
    result = generate_sparql(graph, namespaces=NAMESPACES, labels=False)
    assert 'GROUP_CONCAT(STR(?ship__agg); SEPARATOR=", ") AS ?ship' in result.query
    # the variable name inside the string literal is not renamed (the filter is no output)
    assert 'FILTER(STR(?sq_name) != "?ship \\"x\\"")' in result.query
    assert "?ship__agg rdfs:label ?sq_name ." in result.query
    parse(result.query)
    rows = {r["port"]: r["ship"] for r in run(data, result.query)}
    # Bounty has two labels (en, de): one solution each
    assert sorted(set(rows[f"{NAMESPACES['dbr']}Portsmouth"].split(", "))) == [
        f"{NAMESPACES['dbr']}Bounty",
        f"{NAMESPACES['dbr']}Victory",
    ]


def test_tensor_aggregate_and_vector_sort_order():
    graph = QueryGraph(
        subjects=[
            AssistantSubject(
                id="ship",
                uri="dbo:Ship",
                label="Ship",
                subqueries=[
                    QueryPropSubQuery(id="emb", property_id="dbo:thumbnail_embedding", property_type=TENSOR, aggregate="tensor_avg"),
                    QueryPropSubQuery(id="kind", property_id="dbo:type", group_by=True),
                    VectorSortSubQuery(id="vs", vector=[0.1, 0.2], direction="descending"),
                ],
            )
        ]
    )
    result = generate_sparql(graph, namespaces=NAMESPACES, multimodal=MULTIMODAL)
    query = result.query
    assert "PREFIX dta: <https://w3id.org/rdf-tensor/aggregates#>" in query
    assert "(dta:avg(?sq_emb__agg) AS ?sq_emb)" in query
    # the groups are ordered by their best similarity
    assert "(MAX(?sim_vs__agg) AS ?sim_vs)" in query
    assert "BIND(dtf:cosineSimilarity(?sq_vs__agg, " not in query
    assert "AS ?sim_vs__agg)" in query
    assert "\nGROUP BY ?sq_kind\nORDER BY DESC(?sim_vs)" in query


def test_projection_and_order_by():
    graph = ships_at_ports({"aggregate": "count"}, {"group_by": True}, [length(aggregate="max")])
    result = generate_sparql(graph, namespaces=NAMESPACES, projection=["port", "ship"], order_by=["ship", "len"])
    assert result.variables == ["port", "ship"]
    # ORDER BY only the projected variables (the alias of the count)
    assert result.query.endswith("GROUP BY ?port\nORDER BY ?ship")
    parse(result.query)


def test_count_mode_ignores_aggregation():
    graph = ships_at_ports({"aggregate": "count"}, {"group_by": True})
    query = generate_sparql(graph, namespaces=NAMESPACES, mode="count").query
    assert "__agg" not in query and "GROUP BY" not in query


def test_aggregate_kinds():
    assert aggregate_kind("xsd:double") == "number"
    assert aggregate_kind("xsd:nonNegativeInteger") == "number"
    assert aggregate_kind("<http://dbpedia.org/datatype/kilometre>") == "number"
    assert aggregate_kind("xsd:dateTime") == "date"
    assert aggregate_kind("xsd:gYear") == "date"
    assert aggregate_kind("xsd:string") == "text"
    assert aggregate_kind(None) == "text"
    assert aggregate_kind(TENSOR) == "tensor"
    assert aggregate_kind("<https://w3id.org/rdf-tensor/datatypes#DataTensor>") == "tensor"
    assert AggregateFunction.SUM in AGGREGATES_OF["number"]
    assert AggregateFunction.SUM not in AGGREGATES_OF["text"]
    assert AggregateFunction.TENSOR_STD in AGGREGATES_OF["tensor"]
    assert AggregateFunction.AVG not in AGGREGATES_OF["tensor"]
    assert aggregate_expression(AggregateFunction.TENSOR_STD, "?x") == "dta:std(?x)"
    assert aggregate_expression(AggregateFunction.SAMPLE, "?x") == "SAMPLE(?x)"


def test_rename_variables():
    text = '?a <http://x/?a> "?a" ?ab ?a.'
    assert rename_variables(text, {"a": "a__agg"}) == '?a__agg <http://x/?a> "?a" ?ab ?a__agg.'
