"""assistant/sparql_gen.py: SPARQL of the QueryGraph, checked as text, parsed and run with rdflib."""

import pytest
from rdflib import Graph
from rdflib.plugins.sparql import prepareQuery

from assistant.assistant_model import AssistantLink, AssistantSubject, QueryGraph
from assistant.sparql_gen import (
    SparqlGenerationError,
    SparqlGenerator,
    SparqlOptions,
    format_date,
    generate_sparql,
)
from eval_config import MultimodalConfig

from fakes import DBO, dbo, make_ontology
from test_assistant_model import full_graph

DBR = "http://dbpedia.org/resource/"
NAMESPACES = {"dbo": DBO, "dbr": DBR}
MULTIMODAL = MultimodalConfig(
    image_vector_properties=["dbo:thumbnail_embedding"],
    image_properties=[],
    image_types=[dbo("Image")],
)

DATA_TTL = """
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix foaf: <http://xmlns.com/foaf/0.1/> .
@prefix dbo: <http://dbpedia.org/ontology/> .
@prefix dbr: <http://dbpedia.org/resource/> .

dbr:Bounty a dbo:Ship ; rdfs:label "Bounty"@en, "Die Bounty"@de ;
    dbo:homeport dbr:Portsmouth ; dbo:length "27.7"^^xsd:double ; dbo:active false ;
    dbo:completionDate "1784-01-01T00:00:00Z"^^xsd:dateTime .
dbr:Victory a dbo:Ship ; rdfs:label "HMS Victory"@en ;
    dbo:homeport dbr:Portsmouth ; dbo:length "69.3"^^xsd:double ; dbo:active true ;
    dbo:completionDate "1765-05-07T00:00:00Z"^^xsd:dateTime .
dbr:Unnamed a dbo:Ship ; foaf:name "Nameless" ; dbo:homeport dbr:Plymouth, dbr:Portsmouth .
dbr:Portsmouth a dbo:Place ; rdfs:label "Portsmouth"@en ; dbo:country dbr:England .
dbr:Plymouth a dbo:Place ; rdfs:label "Plymouth"@en ; dbo:country dbr:England .
dbr:England a dbo:Place ; rdfs:label "England"@en .

# chain for property paths: a -p-> b -p-> c -p-> d -p-> e
dbr:a a dbo:Node ; dbo:next dbr:b . dbr:b a dbo:Node ; dbo:next dbr:c .
dbr:c a dbo:Node ; dbo:next dbr:d . dbr:d a dbo:Node ; dbo:next dbr:e .
dbr:e a dbo:Node .
"""


@pytest.fixture(scope="module")
def data():
    return Graph().parse(data=DATA_TTL, format="turtle")


def parse(query: str):
    """Parses (and algebra-translates) a query, fails the test on syntax errors."""
    return prepareQuery(query)


def run(data: Graph, query: str) -> list[dict[str, str]]:
    return [{str(k): str(v) for k, v in row.asdict().items()} for row in data.query(query)]


def ship_graph(subqueries=(), link=None, place=True) -> QueryGraph:
    subjects = [AssistantSubject(id="ship", uri="dbo:Ship", label="ship", subqueries=list(subqueries))]
    links = []
    if place:
        subjects.append(AssistantSubject(id="place", uri="dbo:Place", label="place"))
        links.append(
            AssistantLink(
                **{
                    "id": "home", "uri": "dbo:homeport", "label": "homeport",
                    "from_subject_id": "ship", "to_subject_id": "place", **(link or {}),
                }
            )
        )
    return QueryGraph(subjects=subjects, links=links)


def sparql(graph: QueryGraph, **options):
    return generate_sparql(graph, namespaces=NAMESPACES, multimodal=MULTIMODAL, **options)


# --- every subquery kind ---


def test_full_graph_select():
    generated = sparql(full_graph(), limit=10, offset=20, path_ranges="expand")
    query = generated.query
    parse(query)
    assert query.splitlines()[0].startswith("PREFIX")
    assert "SELECT DISTINCT ?node_1 ?node_2 ?lbl_node_1 ?lbl_node_2 ?sq_1 ?sq_2 ?sq_3" in query
    # query/image/instance props: output variables without filter
    assert "?node_1 rdfs:label ?sq_1 ." in query
    assert f"?node_1 {dbo('thumbnail')} ?sq_2 ." in query
    assert f"?node_1 {dbo('length')} ?sq_3 ." in query
    # subject: the instance, no triple of its own
    assert "VALUES ?node_1 { dbr:Bounty }" in query
    assert "?sq_4" not in query
    assert 'FILTER(STRSTARTS(STR(?sq_5), "HMS"))' in query
    assert 'FILTER(?sq_6 < "42.5"^^xsd:double)' in query
    assert "FILTER(?sq_7 = true)" in query
    assert 'FILTER(?sq_8 = "1900-01-01T00:00:00.000Z"^^xsd:dateTime)' in query
    # vector sort: distance to the vector, sorted by it
    assert f"?node_1 {dbo('thumbnail_embedding')} ?sq_9 ." in query
    assert (
        'BIND(dtf:euclideanDistance(?sq_9, "{\\"type\\":\\"float32\\",\\"shape\\":[2],\\"data\\":[0.25,-1.0]}"'
        "^^<https://w3id.org/rdf-tensor/datatypes#NumericDataTensor>) AS ?sim_9)"
    ) in query
    assert query.endswith("ORDER BY ASC(?sim_9)\nLIMIT 10\nOFFSET 20")
    # labels in the configured language
    assert 'OPTIONAL { ?node_1 rdfs:label ?lbl_node_1 . FILTER(LANG(?lbl_node_1) = "en" || LANG(?lbl_node_1) = "") }' in query
    assert "OPTIONAL { ?node_1 foaf:name ?lbl_node_1 ." in query
    # links: plain, quantified, arbitrary, similarity
    assert f"?node_1 {dbo('homeport')} ?node_2 ." in query
    assert "?node_1 ?p_l3 ?node_2 ." in query
    assert "SERVICE tensorIndex: {" in query

    kinds = {o.var: o.kind for o in generated.outputs}
    assert kinds["sq_1"] == "property" and kinds["sq_3"] == "property"
    # image detection by the image_prop type
    assert kinds["sq_2"] == "image"
    assert kinds["p_l3"] == "link" and kinds["sim_9"] == "similarity" and kinds["dist_l4"] == "distance"
    assert generated.var_of("label", "node_2") == "lbl_node_2"
    assert generated.var_of("property", "3") == "sq_3"
    assert generated.warnings == [] and generated.undeclared_prefixes == []


def test_image_detected_by_property_type():
    prop = {"type": "query_prop", "id": "1", "property_id": "dbo:thumbnail", "property_type": f"dbo:Image"}
    generated = sparql(ship_graph([prop], place=False))
    assert generated.outputs[-1].kind == "image"
    # without the multimodal config it is a plain property
    generated = generate_sparql(ship_graph([prop], place=False), namespaces=NAMESPACES)
    assert generated.outputs[-1].kind == "property"


def test_filters_on_data(data):
    def ships(*subqueries, **options):
        query = sparql(ship_graph(subqueries, place=False), **options).query
        return sorted(row["ship"].removeprefix(DBR) for row in run(data, query))

    assert ships() == ["Bounty", "Unnamed", "Victory"]
    label = {"type": "string", "property_id": "rdfs:label"}
    assert ships({**label, "value": "HMS", "operator": "startswith"}) == ["Victory"]
    assert ships({**label, "value": "Bounty", "operator": "equals"}) == ["Bounty"]
    assert ships({**label, "value": "Bounty", "operator": "!="}) == ["Bounty", "Victory"]  # "Die Bounty"@de
    assert ships({**label, "value": "ount", "operator": "contains"}) == ["Bounty"]
    assert ships({**label, "value": "tory", "operator": "endswith"}) == ["Victory"]
    assert ships({**label, "value": "^H.*y$", "operator": "regex"}) == ["Victory"]
    length = {"type": "number", "property_id": "dbo:length", "property_type": "xsd:double"}
    assert ships({**length, "value": 50, "operator": "less"}) == ["Bounty"]
    assert ships({**length, "value": 50, "operator": "greater"}) == ["Victory"]
    assert ships({**length, "value": 27.7, "operator": "equals"}) == ["Bounty"]
    assert ships({"type": "boolean", "property_id": "dbo:active", "value": True}) == ["Victory"]
    date = {"type": "date", "property_id": "dbo:completionDate", "value": "1770-01-01"}
    assert ships({**date, "operator": "greater"}) == ["Bounty"]
    assert ships({**date, "operator": "less"}) == ["Victory"]
    assert ships({"type": "subject", "instance_id": f"<{DBR}Victory>"}) == ["Victory"]
    assert ships({"type": "subject", "instance_id": None}) == ["Bounty", "Unnamed", "Victory"]
    # query props restrict to subjects that have the property
    assert ships({"type": "query_prop", "property_id": "dbo:length"}) == ["Bounty", "Victory"]


def test_number_literals():
    def literal(**subquery):
        generator = SparqlGenerator(QueryGraph(), SparqlOptions(namespaces=NAMESPACES))
        from assistant.assistant_model import NumberSubQuery

        return generator.number_literal(NumberSubQuery(property_id="dbo:x", **subquery))

    assert literal(value=30, property_type="xsd:integer") == '"30"^^xsd:integer'
    assert literal(value=3.5, property_type="xsd:double") == '"3.5"^^xsd:double'
    # a fraction is no integer literal, the type of a missing range is unknown
    assert literal(value=3.5, property_type="xsd:integer") == "3.5"
    assert literal(value=3.5) == "3.5"
    assert literal(value=2, property_type="<http://dbpedia.org/datatype/centimetre>") == (
        '"2"^^<http://dbpedia.org/datatype/centimetre>'
    )


def test_labels_language_and_fallback(data):
    query = sparql(ship_graph(place=False)).query
    labels = {row["ship"].removeprefix(DBR): row.get("lbl_ship") for row in run(data, query)}
    # one row per ship: the english rdfs:label, else foaf:name
    assert labels == {"Bounty": "Bounty", "Victory": "HMS Victory", "Unnamed": "Nameless"}
    rows = run(data, sparql(ship_graph(place=False), language=None).query)
    assert len(rows) == 4  # both labels of the Bounty
    assert "lbl_" not in sparql(ship_graph(place=False), labels=False).query


def test_string_value_escaped(data):
    value = 'a "quoted" \\ value\n'
    query = sparql(ship_graph([{"type": "string", "property_id": "rdfs:label", "value": value}], place=False)).query
    assert '"a \\"quoted\\" \\\\ value\\n"' in query
    parse(query)
    assert run(data, query) == []


# --- links ---


@pytest.mark.parametrize(
    "quantifier, native, reached",
    [
        (None, "dbo:next", ["b"]),
        ({"type": "+"}, "dbo:next+", ["b", "c", "d", "e"]),
        ({"type": "*"}, "dbo:next*", ["a", "b", "c", "d", "e"]),
        ({"type": "?"}, "dbo:next?", ["a", "b"]),
        ({"type": "EXACTLY", "min": 2}, "dbo:next{2}", ["c"]),
        ({"type": "BETWEEN", "min": 2, "max": 3}, "dbo:next{2,3}", ["c", "d"]),
        ({"type": "BETWEEN", "min": 0, "max": 2}, "dbo:next{0,2}", ["a", "b", "c"]),
        ({"type": "BETWEEN", "min": 3, "max": None}, "dbo:next{3,}", ["d", "e"]),
        ({"type": "BETWEEN", "min": 1, "max": 1}, "dbo:next{1}", ["b"]),
    ],
)
def test_quantifiers(data, quantifier, native, reached):
    graph = QueryGraph(
        subjects=[
            AssistantSubject(id="from", uri="dbo:Node", label="node", subqueries=[{"type": "subject", "instance_id": "dbr:a"}]),
            AssistantSubject(id="to", uri="dbo:Node", label="node"),
        ],
        links=[AssistantLink(id="n", uri="dbo:next", label="next", from_subject_id="from", to_subject_id="to", quantifier=quantifier)],
    )
    assert f"?from {native} ?to ." in sparql(graph).query
    # SPARQL 1.1 spelling of the ranges, same semantics
    expanded = sparql(graph, path_ranges="expand").query
    parse(expanded)
    assert sorted(row["to"].removeprefix(DBR) for row in run(data, expanded)) == reached


@pytest.mark.parametrize(
    "quantifier",
    [{"type": "EXACTLY"}, {"type": "BETWEEN", "min": 3, "max": 2}, {"type": "BETWEEN", "min": 0, "max": 0}],
)
def test_invalid_quantifiers(quantifier):
    with pytest.raises(SparqlGenerationError):
        sparql(ship_graph(link={"quantifier": quantifier}))


def test_arbitrary_links(data):
    for link in ({"allow_arbitrary": True}, {"uri": ""}):
        generated = sparql(ship_graph(link=link))
        assert "?ship ?p_home ?place ." in generated.query
        assert generated.var_of("link", "home") == "p_home"
        rows = run(data, generated.query)
        assert {row["p_home"] for row in rows} == {f"{DBO}homeport"}
    # a variable has no property path
    generated = sparql(ship_graph(link={"allow_arbitrary": True, "quantifier": {"type": "+"}}))
    assert "?ship ?p_home ?place ." in generated.query
    assert generated.warnings and "quantifier" in generated.warnings[0]


def test_similarity_link():
    graph = ship_graph(link={"uri": "", "semantic_link_type": "similarity"})
    generated = sparql(graph)
    query = generated.query
    parse(query)
    # the config's embedding property on both sides, the neighbour bound to the target
    assert "?ship dbo:thumbnail_embedding ?emb_home_from ." in query
    assert "tensorIndex:payload ?place ;" in query
    assert "{ ?place a dbo:Place . ?place dbo:thumbnail_embedding ?emb_home_to . }" in query
    assert "tensorIndex:bindDistance ?dist_home ;" in query
    assert "??" not in query
    with pytest.raises(SparqlGenerationError, match="embedding property"):
        generate_sparql(graph, namespaces=NAMESPACES)


def test_vector_sort():
    sort = {"type": "vector_sort", "id": "v", "property_id": None, "direction": "descending", "vector": [1, 0]}
    generated = sparql(ship_graph([sort], place=False))
    assert "?ship dbo:thumbnail_embedding ?sq_v ." in generated.query
    assert "BIND(dtf:cosineSimilarity(?sq_v, " in generated.query
    assert "ORDER BY DESC(?sim_v)" in generated.query
    parse(generated.query)
    # two sorts form one ORDER BY
    second = {**sort, "id": "w", "direction": "ascending", "distance": "manhattan"}
    assert "ORDER BY DESC(?sim_v) ASC(?sim_w)" in sparql(ship_graph([sort, second], place=False)).query
    # without a vector the sort is left out (and does not restrict the subjects)
    generated = sparql(ship_graph([{**sort, "vector": None}], place=False))
    assert "?sq_v" not in generated.query and "ORDER BY ?lbl_ship" in generated.query
    assert generated.warnings
    # counting needs no distances
    counted = sparql(ship_graph([sort], place=False), mode="count").query
    assert "?sq_v" in counted and "BIND" not in counted and "ORDER BY" not in counted


# --- count mode ---


def test_count_mode(data):
    graph = ship_graph()
    query = sparql(graph, mode="count").query
    parse(query)
    assert "SELECT (COUNT(*) AS ?count) WHERE {" in query
    assert "SELECT DISTINCT ?ship ?place WHERE" in query
    assert "lbl_" not in query and "ORDER BY" not in query
    # Bounty, Victory to Portsmouth, Unnamed to Plymouth and Portsmouth
    assert run(data, query) == [{"count": "4"}]

    # distinct subjects of one node
    query = sparql(graph, mode="count", count_subject="ship").query
    assert "SELECT (COUNT(DISTINCT ?ship) AS ?count)" in query
    assert run(data, query) == [{"count": "3"}]
    # a limit caps the count
    query = sparql(graph, mode="count", count_subject="ship", limit=2).query
    assert "LIMIT 2" in query
    assert run(data, query) == [{"count": "2"}]
    # all solutions, labels included on request
    assert run(data, sparql(graph, mode="count", distinct=False).query) == [{"count": "4"}]
    query = sparql(graph, mode="count", labels=True).query
    assert "?lbl_ship" in query
    assert run(data, query) == [{"count": "4"}]
    assert sparql(graph, mode="count", count_var="n").outputs[0].var == "n"

    with pytest.raises(SparqlGenerationError, match="count_subject"):
        sparql(graph, mode="count", count_subject="nope")


def test_grouped_counts(data):
    from assistant.assistant_model import QueryPropSubQuery

    # distinct ships per homeport, most frequent first
    graph = ship_graph()
    query = sparql(graph, mode="count", count_subject="ship", group_by="place", group_order="count").query
    parse(query)
    assert "GROUP BY ?place" in query and "ORDER BY DESC(?count) ?place" in query
    assert run(data, query) == [
        {"place": DBR + "Portsmouth", "count": "3"},
        {"place": DBR + "Plymouth", "count": "1"},
    ]
    # per value of a query prop, by value, limited groups
    length = ship_graph([QueryPropSubQuery(id="len", property_id="dbo:length")], place=False)
    query = sparql(length, mode="count", count_subject="ship", group_by="len", limit=1).query
    assert "ORDER BY ?sq_len\nLIMIT 1" in query
    assert run(data, query) == [{"sq_len": "27.7", "count": "1"}]
    # without count subject: the distinct solutions per value
    assert run(data, sparql(graph, mode="count", group_by="place", group_order="count").query)[0] == {
        "place": DBR + "Portsmouth", "count": "3",
    }
    # values in the language (and untagged)
    label = ship_graph([QueryPropSubQuery(id="lbl", property_id="rdfs:label")], place=False)
    query = sparql(label, mode="count", count_subject="ship", group_by="lbl", group_language="en").query
    assert {r["sq_lbl"] for r in run(data, query)} == {"Bounty", "HMS Victory"}
    with pytest.raises(SparqlGenerationError, match="neither a subject nor a query prop"):
        sparql(graph, mode="count", group_by="nope")


def test_projection_and_order_by(data):
    from assistant.assistant_model import QueryPropSubQuery

    graph = ship_graph([QueryPropSubQuery(id="len", property_id="dbo:length")])
    query = sparql(graph, projection=["len", "ship"], order_by=["len"], labels=False, limit=1, offset=1).query
    parse(query)
    assert "SELECT DISTINCT ?sq_len ?ship WHERE" in query
    assert "ORDER BY ?sq_len\nLIMIT 1\nOFFSET 1" in query
    assert run(data, query) == [{"sq_len": "69.3", "ship": DBR + "Victory"}]
    # counted variables: the distinct (ship, length) pairs
    query = sparql(graph, mode="count", projection=["ship", "len"]).query
    assert run(data, query) == [{"count": "2"}]


def test_count_of_full_graph_parses():
    parse(sparql(full_graph(), mode="count", limit=1000, path_ranges="expand").query)


# --- terms, variables, errors ---


def test_variable_names_sanitized_and_unique():
    graph = QueryGraph(
        subjects=[
            AssistantSubject(id="a-b", uri="dbo:Ship", label="ship"),
            AssistantSubject(id="a b", uri="dbo:Ship", label="ship"),
            AssistantSubject(id="lbl_a_b", uri="dbo:Ship", label="ship"),
        ],
        links=[AssistantLink(id="x.y", uri="", label="*", from_subject_id="a-b", to_subject_id="a b")],
    )
    generated = sparql(graph)
    parse(generated.query)
    variables = generated.variables
    assert len(variables) == len(set(variables))
    assert variables[:3] == ["a_b", "a_b_2", "lbl_a_b"]
    assert "?a_b ?p_x_y ?a_b_2 ." in generated.query


def test_iris_and_prefixes():
    graph = QueryGraph(
        subjects=[
            AssistantSubject(id="s", uri="http://dbpedia.org/ontology/Ship", label="ship", subqueries=[
                {"type": "subject", "instance_id": "dbr:Foo_(bar)"},
                {"type": "query_prop", "property_id": "ex:prop"},
            ]),
        ]
    )
    generated = sparql(graph)
    assert "?s a <http://dbpedia.org/ontology/Ship> ." in generated.query
    # not a valid prefixed name, expanded
    assert f"VALUES ?s {{ <{DBR}Foo_(bar)> }}" in generated.query
    assert generated.undeclared_prefixes == ["ex"]
    assert "PREFIX" not in sparql(graph, prefixes=False).query


def test_errors():
    with pytest.raises(SparqlGenerationError, match="no subjects"):
        sparql(QueryGraph())
    graph = ship_graph()
    graph.links[0].to_subject_id = "nope"
    with pytest.raises(SparqlGenerationError, match="not in the graph"):
        sparql(graph)
    with pytest.raises(SparqlGenerationError, match="invalid date"):
        sparql(ship_graph([{"type": "date", "property_id": "dbo:x", "value": "yesterday"}], place=False))


def test_dates_of_date_properties():
    from assistant.assistant_model import DateSubQuery

    date = DateSubQuery(id="d", property_id="dbo:launch", property_type="xsd:date", value="1900-01-01", operator="less")
    assert 'FILTER(?sq_d < "1900-01-01"^^xsd:date)' in sparql(ship_graph([date], place=False)).query


def test_format_date():
    assert format_date("1900-01-01") == "1900-01-01T00:00:00.000Z"
    assert format_date("1900-01-01T12:30:00.123456+02:00") == "1900-01-01T10:30:00.123Z"


def test_query_graph_methods_and_ontology_manager():
    """QueryGraph.to_sparql through the OntologyManager, which prepends its own prefixes."""
    ontology = make_ontology()
    options = SparqlOptions.from_ontology(ontology, mode="count", count_subject="ship")
    assert options.language == "en" and "rdfs" in options.namespaces
    graph = QueryGraph(
        subjects=[AssistantSubject(id="ship", uri=dbo("Ship"), label="ship")],
    )
    assert int(ontology.q_to_df(graph.to_sparql(options)).iloc[0, 0]) == 2
    rows = ontology.q_to_df_values(graph.to_sparql(options, mode="select"))
    assert sorted(rows["lbl_ship"]) == ["Bounty", "HMS Victory"]
    assert graph.sparql(options).outputs[0].kind == "count"
