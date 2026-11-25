"""The ontology builder's agent: the tool-calling loop of agent/agent.py over a
builder session (ontology editing, text search, the KG query and export).

It speaks the agent chat protocol (agent/protocol.py), except that the state
message after a change is ``builder_state`` with the session's full state.
"""

import json
import threading
from typing import Literal

from pydantic import BaseModel

from agent.agent import GraphAgent
from agent.protocol import AssistantMessage, Done, ErrorMessage, Thinking, ToolCall
from agent.session import AgentSession, SessionBusy
from agent.tools import ToolCollection, ToolError, ToolResult, tool
from builder.ontology import (
    MAX_VALUES, ExtractionExample, FieldType, OntoClass, OntoField, OntoLink, Ontology, annotation_values, local_name,
    normalize, validate_example,
)
from builder.session import BuilderSession, ExportContent, SessionState, class_query

SYSTEM_PROMPT = """You are an agent that helps the user build an ontology (classes with typed fields, and links between classes) for a collection of text documents.
After every change of the ontology, a small extraction model re-reads the documents and fills a knowledge graph (KG) with the instances it finds: every instance has an rdfs:label (its name), its fields and links, and prov:wasDerivedFrom its documents (each with an rdfs:label and its id as dcterms:identifier). The KG grows while you work, so query results are partial at first.

- Use search_text to learn what the documents talk about before proposing classes, and to check whether a class or field actually occurs in them.
- Keep classes concrete and extractable from single documents (e.g. Person, Organization, Meeting), give them short descriptions: the extraction model only sees the names and descriptions.
- Fields hold literal values (string, integer, float, date, boolean, vector, or enum: one of a fixed list of values); relations between entities are links between classes.
- Organise classes in a hierarchy with set_superclasses. An instance is typed with its own class only, so query a class with its subclasses as ?x a/rdfs:subClassOf* onto:Class.
- The extraction model is small: add_extraction_example with a short text and the exact output expected for it shows it what to extract (the examples precede every document).
- get_kg_stats summarises the KG: instances per class with their most frequent names, triples per link.
- Inspect the KG with set_query (SPARQL; the prefixes onto:, rdfs:, rdf:, xsd: and prov: are predefined, onto: is the ontology's namespace) or query_class, then get_results; GROUP BY with COUNT, SUM, AVG, MIN, MAX, SAMPLE or GROUP_CONCAT summarises it (e.g. instances per class or field value; every selected variable must be grouped or aggregated). The user sees the query and its results, which update live. The build takes minutes and restarts after every ontology change, so do not call get_results repeatedly to wait for it: report what is there and let the user come back to you.
- To export, call prepare_download; the user gets a download link.
Finish with a short answer summarising what you did.
"""

EXAMPLES_PROMPT = """
Example documents with gold annotations are available (get_annotated_examples): their annotations show what should be extracted from documents like these, so design the ontology to recover them. Copying a good example document with its annotation (rewritten as the extraction output of your ontology) into an extraction example can help the small extraction model, but it also tends to copy example outputs: check_extraction measures precision/recall on annotated documents, so compare variants (descriptions, examples, set_extraction_options) with it before relying on the build.
- map_annotations ties a class to a path into the annotations (e.g. "types", "terms.term"), so the annotation's values are known as instances of that class. With mapped classes, set_extraction_options(retrieved_examples=k) gives the small model, for every text it reads, the k annotated example sentences most similar to it with their mapped values as output: examples close to each text, which usually help more than fixed ones (map every class that should be extracted, unmapped classes appear empty in these examples).
- map_annotations(vocabulary=true) also adds every known value of that path (from all annotated documents) found in a document as an instance: high recall, but common words that are values somewhere may be added where they are not meant, so check precision.
- check_extraction never uses the checked document itself for retrieved examples or the vocabulary: compare these variants with it (on the same documents, e.g. the same query and n=5) and keep the best. It reports precision/recall per mapped class: decide per class (e.g. vocabulary for one class but not for another), as what helps one class can hurt another.
"""


def has_annotated_examples(session: BuilderSession) -> bool:
    """Whether the builder has example documents with annotations (loads them)."""
    return session.builder.config.examples is not None and session.builder.examples.annotated


def ontology_summary(onto: Ontology, text_chars: int = 300) -> dict:
    """The ontology for the agent: without layout, example texts shortened."""
    out = onto.model_dump(exclude={"classes": {"__all__": {"x", "y"}}, "examples": True})
    out["examples"] = [
        {"index": i, "text": e.text[:text_chars] + ("..." if len(e.text) > text_chars else ""), "output": e.output}
        for i, e in enumerate(onto.examples)
    ]
    return out


def build_progress(status) -> str:
    return f"{status.processed}/{status.total} documents read, {status.triples} triples" + (
        " (still building)" if status.running else ""
    )


class BuilderStateMessage(BaseModel):
    type: Literal["builder_state"] = "builder_state"
    state: SessionState


class BuilderTools(ToolCollection):
    def __init__(self, session: BuilderSession, k: int = 8):
        self.session = session
        self.k = k
        if not has_annotated_examples(session):
            self.disabled_groups = frozenset({"examples"})

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
        """The current ontology: classes (with fields and superclasses), links, extraction examples and
        extraction options (chunk_chars, annotation_map, retrieved_examples, vocabulary_classes)."""
        return ontology_summary(self.session.ontology)

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
        self._class(onto, class_id)
        onto.remove_class(class_id)
        self.session.set_ontology(onto)
        return f"Removed {class_id}."

    @tool()
    def set_superclasses(self, class_id: str, parent_ids: list[str]) -> OntoClass:
        """Set the superclasses of a class (rdfs:subClassOf), replacing its previous ones.

        Args:
            class_id: id of the class.
            parent_ids: ids of its superclasses, [] for none.
        """
        onto = self._edit()
        cls = self._class(onto, class_id)
        for parent in parent_ids:
            self._class(onto, parent)
            if parent == class_id or class_id in onto.ancestors(parent):
                raise ToolError(f"{parent} is {class_id} or one of its subclasses (cycle).")
        cls.parents = list(dict.fromkeys(parent_ids))
        self.session.set_ontology(onto)
        return cls

    @tool()
    def add_field(
        self, class_id: str, name: str, type: FieldType, description: str, values: list[str] | None = None,
    ) -> OntoField:
        """Add a literal field to a class.

        Args:
            class_id: id of the class.
            name: field name, e.g. "birth date" (becomes camelCase).
            type: value type.
            description: what the value is, for the extraction model.
            values: the allowed values of an enum field (required for enum), null otherwise.
        """
        onto = self._edit()
        cls = self._class(onto, class_id)
        values = list(dict.fromkeys(v.strip() for v in values or [] if v.strip()))
        if type == "enum" and not values:
            raise ToolError("An enum field needs its values.")
        if len(values) > MAX_VALUES:
            raise ToolError(f"At most {MAX_VALUES} values.")
        field = OntoField(name=local_name(name), type=type, description=description,
                          values=values if type == "enum" else [])
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
    def add_extraction_example(self, text: str, output_json: str) -> dict:
        """Add a few-shot example for the extraction model: a short text and the output it should
        extract from it (the first 3 examples precede every document; the KG is rebuilt).

        Args:
            text: the example text (e.g. an annotated example document), shortened to 1500 characters.
            output_json: the expected output as JSON: per class id a list of instances, each
                {"name": ..., <field>: value, <link id>: [names of targets]}, e.g.
                {"Person": [{"name": "Alice Smith", "worksFor": ["Acme"]}], "Company": [{"name": "Acme"}]}.
        """
        try:
            output = json.loads(output_json)
        except json.JSONDecodeError as e:
            raise ToolError(f"output_json is not valid JSON: {e}")
        onto = self._edit()
        try:
            output = validate_example(onto, output)
        except ValueError as e:
            raise ToolError(str(e))
        onto.examples.append(ExtractionExample(text=text[:1500], output=output))
        self.session.set_ontology(onto)
        return {"index": len(onto.examples) - 1, "examples": len(onto.examples)}

    @tool()
    def remove_extraction_example(self, index: int) -> str:
        """Remove an extraction example.

        Args:
            index: its index, as get_ontology lists it.
        """
        onto = self._edit()
        if not 0 <= index < len(onto.examples):
            raise ToolError(f"No example {index}, there are {len(onto.examples)}.")
        onto.examples.pop(index)
        self.session.set_ontology(onto)
        return f"Removed example {index}."

    @tool(group="examples")
    def get_annotated_examples(self, n: int, query: str | None = None) -> list:
        """Example documents with their gold annotation (what should be extracted from them).

        Args:
            n: documents to return, at most 5.
            query: keywords to find relevant example documents, null for a fixed sample.
        """
        return self.session.builder.examples.annotated_examples(max(1, min(n, 5)), query)

    @tool(group="examples")
    def check_extraction(self, n: int, query: str | None = None) -> dict:
        """Run the extraction model with the current ontology on annotated example documents and
        compare with their annotation: per document what it extracted, missed and added, and the
        overall precision/recall. Use it to test ontology changes before relying on the build.

        Args:
            n: documents to check, at most 5.
            query: keywords to pick the documents, null for a fixed sample.
        """
        docs = self.session.builder.examples.annotated_examples(max(1, min(n, 5)), query, max_chars=4000)
        return self.session.check_extraction(docs)

    @tool(group="examples")
    def map_annotations(self, class_id: str, path: str, vocabulary: bool) -> dict:
        """Map a class to a path into the annotations of the example documents: its values are the
        instances of that class (for retrieved examples, see set_extraction_options). Restarts the build.

        Args:
            class_id: id of the class.
            path: dotted path into an annotation, lists are flattened: "types" (the strings of
                annotation["types"]), "terms.term" (each term's name), "terms.types"; "" removes the mapping.
            vocabulary: also add every value of this path (of all annotated documents) found in a
                document as an instance of the class.
        """
        onto = self._edit()
        self._class(onto, class_id)
        path = path.strip().strip(".")
        onto.vocabulary_classes = [c for c in onto.vocabulary_classes if c != class_id]
        if not path:
            onto.annotation_map.pop(class_id, None)
            if not onto.annotation_map:
                onto.retrieved_examples = 0
            self.session.set_ontology(onto)
            return {"class_id": class_id, "mapped": False, "retrieved_examples": onto.retrieved_examples}
        examples = self.session.builder.examples
        documents, values = 0, {}
        for doc in examples.documents:
            annotation = examples.annotation(doc.id)
            found = annotation_values(annotation, path) if annotation is not None else []
            documents += bool(found)
            values.update((normalize(v), v) for v in found)
        if not documents:
            sample = next((a for d in examples.documents if (a := examples.annotation(d.id)) is not None), None)
            raise ToolError(f"No annotation has values at '{path}'. An annotation: {json.dumps(sample)[:300]}")
        onto.annotation_map[class_id] = path
        if vocabulary:
            onto.vocabulary_classes.append(class_id)
        self.session.set_ontology(onto)
        return {
            "class_id": class_id, "path": path, "documents": documents, "distinct_values": len(values),
            "sample": list(values.values())[:10], "vocabulary": vocabulary,
            **({"vocabulary_entries": len(self.session.builder.vocabulary(path))} if vocabulary else {}),
        }

    @tool()
    def set_extraction_options(self, chunk_chars: int | None, retrieved_examples: int | None = None) -> str:
        """Set how documents are given to the extraction model: whole (null), or in pieces of whole
        sentences of at most chunk_chars characters (e.g. 250), which helps the small model find
        more mentions in long or dense texts; and how many few-shot examples are retrieved for
        every piece (the most similar annotated example sentences, needs map_annotations).
        Restarts the build.

        Args:
            chunk_chars: maximum piece length (at least 100), null for whole documents.
            retrieved_examples: retrieved examples per piece, 0 to 5 (0: none), null to keep the current setting.
        """
        if chunk_chars is not None and chunk_chars < 100:
            raise ToolError("chunk_chars must be at least 100 (or null).")
        onto = self._edit()
        if retrieved_examples is not None:
            if not 0 <= retrieved_examples <= 5:
                raise ToolError("retrieved_examples must be between 0 and 5.")
            if retrieved_examples and not onto.mapped_classes():
                raise ToolError("Map annotations to classes first (map_annotations).")
            onto.retrieved_examples = retrieved_examples
        onto.chunk_chars = chunk_chars
        self.session.set_ontology(onto)
        how = 'whole' if chunk_chars is None else f'in pieces of at most {chunk_chars} characters'
        return f"Documents are extracted {how}, with {onto.retrieved_examples} retrieved examples each."

    @tool()
    def get_kg_stats(self, top: int) -> dict:
        """Summary of the (partial) KG: per class its instance count and most frequent names
        (by the documents they were found in), per link its triple count, and the build progress.

        Args:
            top: names per class, at most 20.
        """
        stats = self.session.kg_stats(max(0, min(top, 20)))
        return {
            "classes": {
                c: {"instances": s.instances, **({"with_subclasses": s.with_subclasses} if s.with_subclasses is not None else {}),
                    "top": {t.label: t.documents for t in s.top}}
                for c, s in stats.classes.items()
            },
            "links": stats.links,
            "build": build_progress(stats.status),
        }

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
        return {"rows": rows, "build": build_progress(result.status)}

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
        config = session.builder.config
        super().__init__(
            llm, BuilderTools(session, config.search_k), max_steps=config.agent.max_steps,
            system_prompt=SYSTEM_PROMPT + (EXAMPLES_PROMPT if has_annotated_examples(session) else ""),
        )

    def describe_state(self) -> str:
        state = self.session.state()
        return json.dumps(ontology_summary(state.ontology)) + (
            f"\nCurrent query:\n{state.query}" if state.query else ""
        )

    def state_message(self):
        return BuilderStateMessage(state=self.session.state())

    def call_tool(self, name: str, arguments: str | None) -> tuple[ToolResult, dict]:
        return self.tools.call(name, arguments), {}


def chat_log_entry(message) -> dict | None:
    """The frame of a turn as the chat transcript keeps it (final frames only), or None."""
    if isinstance(message, (Thinking, AssistantMessage)):
        return message.model_dump(mode="json") if message.final and message.content else None
    if isinstance(message, ToolCall):
        return message.model_dump(mode="json") if message.status != "running" else None
    if isinstance(message, (ErrorMessage, Done)):
        return message.model_dump(mode="json")
    return None


class BuilderChat(AgentSession):
    """The busy/cancel handling of an agent chat session, around a BuilderAgent.

    The chat is kept in the BuilderSession (``chat_history`` for the model, ``chat_log``
    for the UI) and saved with it after every turn, so it survives reconnects, reloads,
    restarts and evictions; only ``clear`` resets it."""

    def __init__(self, session: BuilderSession):
        self.session_id = session.session_id
        self.session = session
        self.agent = BuilderAgent(session.builder.agent_llm, session)
        with session._lock:
            self.agent.history.extend(session.chat_history)
        self._lock = threading.Lock()
        self._busy = False
        self._cancel = threading.Event()

    def on_turn_start(self, content: str):
        self.session.log_chat({"type": "user_message", "content": content})

    def on_message(self, message):
        if (entry := chat_log_entry(message)) is not None:
            self.session.log_chat(entry)

    def on_turn_end(self):
        # writes the session file: called in the turn's worker thread
        self.session.save_chat(self.agent.history[1:])

    def clear(self):
        """Reset the chat and its saved history (blocking: file I/O)."""
        with self._lock:
            if self._busy:
                raise SessionBusy("Cancel the running turn before clearing.")
            self._busy = True
        try:
            self.agent.reset()
            self.session.clear_chat()
        finally:
            with self._lock:
                self._busy = False
