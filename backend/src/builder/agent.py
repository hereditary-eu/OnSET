"""The ontology builder's agent: the tool-calling loop of agent/agent.py over a
builder session (ontology editing, text search, the KG query and export).

It speaks the agent chat protocol (agent/protocol.py), except that the state
message after a change is ``builder_state`` with the session's full state.
"""

import threading
from typing import Literal

from pydantic import BaseModel

from agent.agent import GraphAgent
from agent.session import AgentSession, SessionBusy
from agent.tools import ToolCollection, ToolError, ToolResult, tool
from builder.ontology import FieldType, OntoClass, OntoField, OntoLink, local_name
from builder.session import BuilderSession, ExportContent, SessionState, class_query

SYSTEM_PROMPT = """You are an agent that helps the user build an ontology (classes with typed fields, and links between classes) for a collection of text documents.
After every change of the ontology, a small extraction model re-reads the documents and fills a knowledge graph (KG) with the instances it finds: every instance has an rdfs:label (its name), its fields and links, and prov:wasDerivedFrom its document. The KG grows while you work, so query results are partial at first.

- Use search_text to learn what the documents talk about before proposing classes, and to check whether a class or field actually occurs in them.
- Keep classes concrete and extractable from single documents (e.g. Person, Organization, Meeting), give them short descriptions: the extraction model only sees the names and descriptions.
- Fields hold literal values (string, integer, float, date, boolean, vector); relations between entities are links between classes.
- Inspect the KG with set_query (SPARQL; the prefixes onto:, rdfs:, rdf:, xsd: and prov: are predefined, onto: is the ontology's namespace) or query_class, then get_results. The user sees the query and its results, which update live. The build takes minutes and restarts after every ontology change, so do not call get_results repeatedly to wait for it: report what is there and let the user come back to you.
- To export, call prepare_download; the user gets a download link.
Finish with a short answer summarising what you did.
"""


class BuilderStateMessage(BaseModel):
    type: Literal["builder_state"] = "builder_state"
    state: SessionState


class BuilderTools(ToolCollection):
    def __init__(self, session: BuilderSession, k: int = 8):
        self.session = session
        self.k = k

    def _edit(self):
        """A copy of the ontology to change and set again (which restarts the build)."""
        return self.session.ontology.model_copy(deep=True)

    def _class(self, onto, class_id: str) -> OntoClass:
        cls = onto.get_class(class_id)
        if cls is None:
            raise ToolError(f"No class '{class_id}', classes: {[c.id for c in onto.classes]}")
        return cls

    @tool()
    def get_ontology(self) -> dict:
        """The current ontology: classes (with fields) and links."""
        return self.session.ontology.model_dump(exclude={"classes": {"__all__": {"x", "y"}}})

    @tool()
    def search_text(self, query: str) -> list:
        """Search the documents, returns the most relevant sentences with their document.

        Args:
            query: keywords or a short phrase.
        """
        return self.session.builder.corpus.search(query, self.k)

    @tool()
    def add_class(self, name: str, description: str) -> OntoClass:
        """Add a class to the ontology.

        Args:
            name: class name, e.g. "Person" (becomes its id in CamelCase).
            description: what its instances are, for the extraction model.
        """
        onto = self._edit()
        class_id = local_name(name, upper=True)
        if onto.get_class(class_id):
            raise ToolError(f"Class '{class_id}' exists already.")
        cls = OntoClass(id=class_id, label=name, description=description)
        onto.classes.append(cls)
        self.session.set_ontology(onto)
        return cls

    @tool()
    def remove_class(self, class_id: str) -> str:
        """Remove a class, its fields and all links from or to it.

        Args:
            class_id: id of the class.
        """
        onto = self._edit()
        onto.classes.remove(self._class(onto, class_id))
        onto.links = [l for l in onto.links if class_id not in (l.source, l.target)]
        self.session.set_ontology(onto)
        return f"Removed {class_id}."

    @tool()
    def add_field(self, class_id: str, name: str, type: FieldType, description: str) -> OntoField:
        """Add a literal field to a class.

        Args:
            class_id: id of the class.
            name: field name, e.g. "birth date" (becomes camelCase).
            type: value type.
            description: what the value is, for the extraction model.
        """
        onto = self._edit()
        cls = self._class(onto, class_id)
        field = OntoField(name=local_name(name), type=type, description=description)
        if any(f.name == field.name for f in cls.fields):
            raise ToolError(f"{class_id} has a field '{field.name}' already.")
        cls.fields.append(field)
        self.session.set_ontology(onto)
        return field

    @tool()
    def remove_field(self, class_id: str, name: str) -> str:
        """Remove a field of a class.

        Args:
            class_id: id of the class.
            name: name of the field.
        """
        onto = self._edit()
        cls = self._class(onto, class_id)
        fields = [f for f in cls.fields if f.name != name]
        if len(fields) == len(cls.fields):
            raise ToolError(f"{class_id} has no field '{name}', fields: {[f.name for f in cls.fields]}")
        cls.fields = fields
        self.session.set_ontology(onto)
        return f"Removed {class_id}.{name}."

    @tool()
    def add_link(self, name: str, source: str, target: str, description: str) -> OntoLink:
        """Add a link (relation) from instances of one class to instances of another.

        Args:
            name: link name, e.g. "works for" (becomes its id in camelCase).
            source: id of the class the link starts at.
            target: id of the class it points to.
            description: what the relation means, for the extraction model.
        """
        onto = self._edit()
        self._class(onto, source), self._class(onto, target)
        link = OntoLink(id=local_name(name), label=name, source=source, target=target, description=description)
        if any(l.id == link.id for l in onto.links):
            raise ToolError(f"Link '{link.id}' exists already.")
        onto.links.append(link)
        self.session.set_ontology(onto)
        return link

    @tool()
    def remove_link(self, link_id: str) -> str:
        """Remove a link.

        Args:
            link_id: id of the link.
        """
        onto = self._edit()
        links = [l for l in onto.links if l.id != link_id]
        if len(links) == len(onto.links):
            raise ToolError(f"No link '{link_id}', links: {[l.id for l in onto.links]}")
        onto.links = links
        self.session.set_ontology(onto)
        return f"Removed {link_id}."

    @tool()
    def set_query(self, sparql: str) -> dict:
        """Set the SPARQL SELECT query over the KG that the user sees, returns the first results.

        Args:
            sparql: the query; prefixes onto:, rdfs:, rdf:, xsd:, prov: are predefined.
        """
        self.session.set_query(sparql)
        return self.get_results(10)

    @tool()
    def query_class(self, class_id: str) -> dict:
        """Set the query to the instances of a class with their label, fields and links.

        Args:
            class_id: id of the class.
        """
        try:
            return self.set_query(class_query(self.session.ontology, class_id))
        except KeyError as e:
            raise ToolError(str(e))

    @tool()
    def get_results(self, limit: int) -> dict:
        """The current query's results (labels of instances) and the build progress.

        Args:
            limit: rows to return, at most 50.
        """
        result = self.session.run_query(limit=max(1, min(limit, 50)))
        if result.error:
            raise ToolError(result.error)
        rows = [
            {c: (cell.label or cell.value) if cell else None for c, cell in zip(result.columns, row)}
            for row in result.rows
        ]
        s = result.status
        return {
            "rows": rows,
            "build": f"{s.processed}/{s.total} documents read, {s.triples} triples"
            + (" (still building)" if s.running else ""),
        }

    @tool()
    def prepare_download(self, content: ExportContent, prefix: str | None) -> dict:
        """Prepare a Turtle download of the ontology, the KG or both for the user.

        Args:
            content: "ontology", "kg" or "all".
            prefix: IRI prefix of the exported terms, null for the ontology's own.
        """
        return {"download": {"content": content, "prefix": prefix or self.session.ontology.prefix}}


class BuilderAgent(GraphAgent):
    state_name = "ontology"

    def __init__(self, llm, session: BuilderSession):
        self.session = session
        super().__init__(
            llm, BuilderTools(session, session.builder.config.search_k),
            max_steps=session.builder.config.agent.max_steps, system_prompt=SYSTEM_PROMPT,
        )

    def describe_state(self) -> str:
        state = self.session.state()
        return state.ontology.model_dump_json(exclude={"classes": {"__all__": {"x", "y"}}}) + (
            f"\nCurrent query:\n{state.query}" if state.query else ""
        )

    def state_message(self):
        return BuilderStateMessage(state=self.session.state())

    def call_tool(self, name: str, arguments: str | None) -> tuple[ToolResult, dict]:
        return self.tools.call(name, arguments), {}


class BuilderChat(AgentSession):
    """The busy/cancel handling of an agent chat session, around a BuilderAgent."""

    def __init__(self, session: BuilderSession):
        self.session_id = session.session_id
        self.agent = BuilderAgent(session.builder.agent_llm, session)
        self._lock = threading.Lock()
        self._busy = False
        self._cancel = threading.Event()

    def clear(self):
        with self._lock:
            if self._busy:
                raise SessionBusy("Cancel the running turn before clearing.")
            self.agent.reset()
