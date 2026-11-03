"""agent/graph_tools.py: the optional constraint tools (subqueries on subjects)."""

import pytest

from agent.agent import BASE_SYSTEM_PROMPT, CONSTRAINT_PROMPT, GraphAgent
from agent.graph_tools import CONSTRAINT_TOOLS, GraphEditorTools
from agent.llm import ResponseDone
from agent.protocol import diff_graphs
from agent.session import AgentSession
from assistant.assistant_model import AssistantSubject, NumberSubQuery, QueryGraph
from assistant.sparql_gen import SparqlOptions
from eval_config import AgentConfig
from explorative.exp_model import RELATION_TYPE, RETURN_TYPE

from fakes import ONTOLOGY_TTL, ScriptedLLM, StubGuidance, dbo, final_answer, function_call, make_ontology

CONSTRAINT_TOOL_NAMES = {"search_properties", "add_constraint", "restrict_to_instance", "remove_constraint"}

EXTRA_TTL = """
dbo:launchDate a owl:DatatypeProperty ; rdfs:label "launch date"@en ;
    rdfs:domain dbo:Ship ; rdfs:range xsd:date .
dbo:decommissioned a owl:DatatypeProperty ; rdfs:label "decommissioned"@en ;
    rdfs:domain dbo:Ship ; rdfs:range xsd:boolean .
dbo:motto a owl:DatatypeProperty ; rdfs:label "motto"@en ;
    rdfs:domain dbo:Ship ; rdfs:range xsd:string .
dbo:birthDate a owl:DatatypeProperty ; rdfs:label "birth date"@en ;
    rdfs:domain dbo:Person ; rdfs:range xsd:date .
dbo:wikiPageLength a owl:DatatypeProperty ; rdfs:label "page length"@en ;
    rdfs:range xsd:integer .
dbr:Victoria a dbo:Ship ; rdfs:label "Victoria"@en .
"""


@pytest.fixture
def ontology():
    return make_ontology(ONTOLOGY_TTL + EXTRA_TTL)


@pytest.fixture
def guidance(ontology):
    return StubGuidance(ontology)


@pytest.fixture
def tools(ontology, guidance):
    return GraphEditorTools(ontology, guidance, retrieve_k=3)


def ok(tools, name, **args):
    result = tools.call(name, args)
    assert result.ok, result.error
    return result.output


def error(tools, name, **args):
    result = tools.call(name, args)
    assert not result.ok, result.output
    return result.error


@pytest.fixture
def ship(tools):
    return ok(tools, "add_subject", uri=dbo("Ship"))["id"]


# --- the flag ---


def test_constraint_tools_enabled_by_default(tools):
    assert CONSTRAINT_TOOL_NAMES <= set(tools.tool_names())
    definitions = {d["name"]: d for d in tools.definitions()}
    add = definitions["add_constraint"]["parameters"]
    assert add["required"] == ["subject_id", "property_uri", "operator", "value"]
    assert "greater" in add["properties"]["operator"]["enum"]


def test_flag_hides_the_tools(ontology, guidance):
    tools = GraphEditorTools(ontology, guidance, constraint_tools=False)
    assert tools.disabled_groups == {CONSTRAINT_TOOLS}
    assert not CONSTRAINT_TOOL_NAMES & set(tools.tool_names())
    assert not CONSTRAINT_TOOL_NAMES & {d["name"] for d in tools.definitions()}
    # the other tools are unaffected
    assert {"search_classes", "add_subject", "add_link"} <= set(tools.tool_names())
    ship = ok(tools, "add_subject", uri=dbo("Ship"))["id"]
    result = tools.call("add_constraint", {"subject_id": ship, "property_uri": dbo("length"), "operator": "greater", "value": "1"})
    assert not result.ok and "Tool add_constraint not found" in result.error
    assert tools.graph.subjects[0].subqueries == []


@pytest.mark.parametrize("enabled", [True, False])
def test_flag_sets_the_system_prompt_and_tool_definitions(ontology, guidance, enabled):
    tools = GraphEditorTools(ontology, guidance, constraint_tools=enabled)
    llm = ScriptedLLM([final_answer("ok")])
    agent = GraphAgent(llm, tools)
    list(agent.run_turn("hi"))
    prompt = llm.calls[0][0]["content"]
    assert prompt.startswith(BASE_SYSTEM_PROMPT)
    assert (CONSTRAINT_PROMPT in prompt) == enabled
    assert ("add_constraint" in {t["name"] for t in llm.tools[0]}) == enabled


@pytest.mark.parametrize("enabled", [True, False])
def test_session_threads_the_config_flag(ontology, guidance, enabled):
    session = AgentSession("s", ScriptedLLM([]), ontology, guidance, AgentConfig(constraint_tools=enabled))
    assert session.tools.constraint_tools is enabled
    assert ("add_constraint" in session.tools.tool_names()) == enabled
    assert (CONSTRAINT_PROMPT in session.agent.system_prompt) == enabled


def test_agent_config_flag_defaults_to_enabled():
    assert AgentConfig().constraint_tools is True
    assert AgentConfig.model_validate({"constraint_tools": "false"}).constraint_tools is False


# --- search_properties ---


def test_search_properties_lists_datatype_properties(tools, ship):
    properties = ok(tools, "search_properties", subject_id=ship)
    assert properties[0] == {"uri": "rdfs:label", "label": "label (name)", "value_type": "string", "range": "xsd:string"}
    by_uri = {p["uri"]: p for p in properties[1:]}
    # the class's own properties, then the generic ones (no domain); no object properties
    assert list(by_uri) == [dbo("decommissioned"), dbo("launchDate"), dbo("length"), dbo("motto"), dbo("wikiPageLength")]
    assert by_uri[dbo("length")] == {"uri": dbo("length"), "label": "length", "value_type": "number", "range": "xsd:double"}
    assert by_uri[dbo("launchDate")]["value_type"] == "date"
    assert by_uri[dbo("decommissioned")]["value_type"] == "boolean"
    assert by_uri[dbo("motto")]["value_type"] == "string"


def test_search_properties_inherits_from_parents(tools):
    warship = ok(tools, "add_subject", uri=dbo("Warship"))["id"]
    uris = [p["uri"] for p in ok(tools, "search_properties", subject_id=warship)]
    assert dbo("length") in uris and dbo("birthDate") not in uris


def test_search_properties_with_query(tools, guidance, ship):
    properties = ok(tools, "search_properties", subject_id=ship, query="length")
    query = guidance.queries[-1]
    assert (query.type, query.relation_type) == (RETURN_TYPE.LINK, RELATION_TYPE.PROPERTY)
    assert query.from_id == dbo("Ship") and query.limit == 3 and query.include_thing
    assert [p["uri"] for p in properties] == [dbo("decommissioned"), dbo("launchDate"), dbo("length")]


def test_search_properties_errors(tools):
    assert "Subject nope is not in the query graph" in error(tools, "search_properties", subject_id="nope")
    tools.graph.add_subject(AssistantSubject(id="thing_1", uri="", label="thing"))
    assert "has no class" in error(tools, "search_properties", subject_id="thing_1")


# --- add_constraint ---


def test_add_number_constraint(tools, ship):
    added = ok(tools, "add_constraint", subject_id=ship, property_uri=dbo("length"), operator="greater", value="20")
    assert added == {
        "type": "number",
        "id": "length_1",
        "property_id": dbo("length"),
        "property_label": "length",
        "property_type": "xsd:double",
        "value": 20.0,
        "operator": "greater",
    }
    subject = tools.graph.get_subject_by_id(ship)
    assert subject.subqueries == [NumberSubQuery.model_validate(added)]
    # an alias of the operator and a prefixed/unwrapped IRI work as well, ids stay unique
    second = ok(tools, "add_constraint", subject_id=ship, property_uri="http://dbpedia.org/ontology/length", operator="<", value="30.5")
    assert (second["id"], second["operator"], second["value"]) == ("length_2", "less", 30.5)
    # the constraints restrict the query: only the Bounty is 27.7 long
    options = SparqlOptions.from_ontology(tools.ontology_manager, mode="count", count_subject=ship)
    assert int(tools.ontology_manager.q_to_df(tools.graph.to_sparql(options)).iloc[0, 0]) == 1


def test_add_constraint_rejects_duplicates(tools, ship):
    ok(tools, "add_constraint", subject_id=ship, property_uri=dbo("length"), operator="greater", value="20")
    assert "already has this constraint (id length_1)" in error(
        tools, "add_constraint", subject_id=ship, property_uri=dbo("length"), operator="greater", value="20"
    )


@pytest.mark.parametrize(
    "value, expected",
    [("1787", "1787-01-01"), ("1787-12", "1787-12-01"), ("1787-12-23", "1787-12-23"), ("1787-12-23T10:00:00Z", "1787-12-23T10:00:00Z")],
)
def test_add_date_constraint(tools, ship, value, expected):
    added = ok(tools, "add_constraint", subject_id=ship, property_uri=dbo("launchDate"), operator="less", value=value)
    assert (added["type"], added["value"], added["operator"], added["property_type"]) == ("date", expected, "less", "xsd:date")
    assert added["id"] == "launch_date_1"
    tools.graph.to_sparql()


@pytest.mark.parametrize("operator, value, expected", [("equals", "yes", True), ("equals", "false", False), ("!=", "true", False)])
def test_add_boolean_constraint(tools, ship, operator, value, expected):
    added = ok(tools, "add_constraint", subject_id=ship, property_uri=dbo("decommissioned"), operator=operator, value=value)
    assert (added["type"], added["value"]) == ("boolean", expected)


def test_add_string_and_label_constraints(tools, ship):
    motto = ok(tools, "add_constraint", subject_id=ship, property_uri=dbo("motto"), operator="contains", value=" England ")
    assert (motto["type"], motto["value"], motto["operator"]) == ("string", "England", "contains")
    label = ok(tools, "add_constraint", subject_id=ship, property_uri="rdfs:label", operator="startswith", value="HMS")
    assert (label["property_id"], label["operator"], label["id"]) == ("rdfs:label", "startswith", "label_name_1")
    tools.graph.to_sparql()


def test_generic_property_applies_to_every_class(tools):
    person = ok(tools, "add_subject", uri=dbo("Person"))["id"]
    added = ok(tools, "add_constraint", subject_id=person, property_uri=dbo("wikiPageLength"), operator="greater", value="1000")
    assert added["property_type"] == "xsd:integer"


@pytest.mark.parametrize(
    "args, message",
    [
        (dict(subject_id="nope", property_uri=dbo("length"), operator="greater", value="1"), "Subject nope is not in the query graph"),
        # an object property, a class and a property of another class
        (dict(property_uri=dbo("homeport"), operator="equals", value="x"), "is no datatype property of ship"),
        (dict(property_uri=dbo("Country"), operator="equals", value="x"), "search_properties(subject_id='ship_1')"),
        (dict(property_uri=dbo("birthDate"), operator="less", value="1900"), "is no datatype property"),
        (dict(property_uri=dbo("length"), operator="contains", value="1"), "use one of ['equals', 'less', 'greater']"),
        (dict(property_uri=dbo("motto"), operator="less", value="a"), "Operator 'less' does not apply to motto"),
        (dict(property_uri=dbo("decommissioned"), operator="greater", value="true"), "boolean values"),
        (dict(property_uri=dbo("length"), operator="greater", value="long"), "is not a number"),
        (dict(property_uri=dbo("length"), operator="greater", value="nan"), "is not a number"),
        (dict(property_uri=dbo("launchDate"), operator="less", value="last year"), "is not a date"),
        (dict(property_uri=dbo("decommissioned"), operator="equals", value="maybe"), "is not a boolean"),
        (dict(property_uri=dbo("motto"), operator="regex", value="(unclosed"), "no valid regular expression"),
        (dict(property_uri=dbo("motto"), operator="equals", value="  "), "non-empty text"),
    ],
)
def test_add_constraint_errors(tools, ship, args, message):
    assert message in error(tools, "add_constraint", **{"subject_id": ship, **args})
    assert tools.graph.get_subject_by_id(ship).subqueries == []


def test_add_constraint_without_stored_schema(tools, guidance, ship, monkeypatch):
    def no_schema():
        raise RuntimeError("no stored schema")

    monkeypatch.setattr(guidance, "schema_index", no_schema)
    # from the ontology: the domain of the property fits the class
    added = ok(tools, "add_constraint", subject_id=ship, property_uri=dbo("length"), operator="greater", value="1")
    assert (added["property_type"], added["property_label"]) == ("xsd:double", "length")
    country = ok(tools, "add_subject", uri=dbo("Country"))["id"]
    assert "is no datatype property" in error(
        tools, "add_constraint", subject_id=country, property_uri=dbo("length"), operator="greater", value="1"
    )
    # nothing to list without a schema
    assert "search them with a query" in error(tools, "search_properties", subject_id=ship)


# --- restrict_to_instance ---


def test_restrict_to_instance(tools, ship):
    added = ok(tools, "restrict_to_instance", subject_id=ship, instance="bounty")
    assert added["type"] == "subject" and added["instance_id"] == "<http://dbpedia.org/resource/Bounty>"
    assert added["id"] == "bounty_1" and added["property_type"] == "owl:Thing"
    assert "already restricted to Bounty (constraint id bounty_1)" in error(tools, "restrict_to_instance", subject_id=ship, instance="victoria")
    options = SparqlOptions.from_ontology(tools.ontology_manager, mode="count", count_subject=ship)
    assert int(tools.ontology_manager.q_to_df(tools.graph.to_sparql(options)).iloc[0, 0]) == 1


def test_restrict_to_instance_ambiguous_then_by_uri(tools, ship):
    message = error(tools, "restrict_to_instance", subject_id=ship, instance="vic")
    assert "Several instances of ship match 'vic'" in message and "Resource/Victoria" not in message
    assert "<http://dbpedia.org/resource/Victoria>" in message
    added = ok(tools, "restrict_to_instance", subject_id=ship, instance="<http://dbpedia.org/resource/Victoria>")
    assert (added["instance_id"], added["instance_label"]) == ("<http://dbpedia.org/resource/Victoria>", "Victoria")


def test_restrict_to_instance_prefers_exact_label(tools, ship):
    added = ok(tools, "restrict_to_instance", subject_id=ship, instance="Victoria")
    assert added["instance_label"] == "Victoria"


def test_restrict_to_instance_errors(tools, ship):
    assert "has a label containing 'Titanic'" in error(tools, "restrict_to_instance", subject_id=ship, instance="Titanic")
    assert "Pass the name" in error(tools, "restrict_to_instance", subject_id=ship, instance='"')


# --- remove_constraint ---


def test_remove_constraint(tools, ship):
    constraint = ok(tools, "add_constraint", subject_id=ship, property_uri=dbo("length"), operator="greater", value="1")["id"]
    assert "success" in ok(tools, "remove_constraint", subject_id=ship, constraint_id=constraint)
    assert tools.graph.get_subject_by_id(ship).subqueries == []
    assert "its constraints: []" in error(tools, "remove_constraint", subject_id=ship, constraint_id=constraint)


def test_remove_constraint_of_the_editor(tools):
    # subqueries synced from the editor have numeric ids
    tools.graph = QueryGraph(
        subjects=[AssistantSubject(id="node_1", uri=dbo("Ship"), label="ship", subqueries=[NumberSubQuery(id="3", property_id=dbo("length"))])]
    )
    ok(tools, "remove_constraint", subject_id="node_1", constraint_id="3")
    assert tools.graph.subjects[0].subqueries == []


# --- protocol / agent loop ---


def test_diff_graphs_reports_subquery_changes(tools, ship):
    before = tools.graph.model_copy(deep=True)
    constraint = ok(tools, "add_constraint", subject_id=ship, property_uri=dbo("length"), operator="greater", value="1")
    change = diff_graphs(before, tools.graph)
    assert not change.empty and change.added.subjects == [] and change.added.links == []
    assert [(c.operation, c.subject_id, c.subquery.id) for c in change.subqueries] == [("add", ship, constraint["id"])]
    assert [s.id for s in change.context] == [ship]

    before = tools.graph.model_copy(deep=True)
    ok(tools, "remove_constraint", subject_id=ship, constraint_id=constraint["id"])
    change = diff_graphs(before, tools.graph)
    assert [(c.operation, c.subquery.id) for c in change.subqueries] == [("remove", constraint["id"])]

    # a changed subquery is removed and added again
    before = tools.graph.model_copy(deep=True)
    tools.graph.subjects[0].subqueries = [NumberSubQuery(id="x", property_id=dbo("length"), value=1)]
    after = tools.graph.model_copy(deep=True)
    after.subjects[0].subqueries[0].value = 2
    change = diff_graphs(tools.graph, after)
    assert [c.operation for c in change.subqueries] == ["remove", "add"]
    # subqueries of added subjects are part of the added subject
    assert diff_graphs(QueryGraph(), after).subqueries == []


def test_agent_turn_with_constraint(tools, ship):
    llm = ScriptedLLM(
        [
            [ResponseDone(output=[function_call("c1", "add_constraint", subject_id=ship, property_uri=dbo("length"), operator="greater", value="20")])],
            final_answer("Kept ships longer than 20."),
        ]
    )
    messages = [m.model_dump(mode="json") for m in GraphAgent(llm, tools).run_turn("only ships longer than 20 m")]
    call = [m for m in messages if m["type"] == "tool_call" and m["status"] != "running"][0]
    assert call["status"] == "success"
    assert call["changes"]["subqueries"][0]["subject_id"] == ship
    assert call["changes"]["subqueries"][0]["subquery"]["id"] == "length_1"
    states = [m for m in messages if m["type"] == "graph_state"]
    assert len(states) == 1
    assert states[0]["graph"]["subjects"][0]["subqueries"][0]["value"] == 20.0
    # the model sees the constraint in the graph context of the next request
    assert "length_1" in llm.calls[-1][-1]["output"]
