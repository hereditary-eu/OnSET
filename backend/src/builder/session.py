"""Ontology builder sessions: the ontology, its progressively built KG and a query.

Every schema change of the ontology restarts the build: a fresh triple store
is filled document by document (in a fixed shuffled order, so early results are
representative) by ``extract_instances`` extraction threads, while queries
already run against the partial KG. The store is Tentris (embedded, native
Linux x86_64 only) and an in-memory rdflib store elsewhere.
"""

import json
import os
import random
import re
import threading
import time
import uuid
from collections import OrderedDict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from functools import cached_property
from itertools import islice
from pathlib import Path
from typing import Literal as TLiteral

from pydantic import BaseModel
from rdflib import RDFS, Graph, Literal, URIRef

from builder.corpus import Corpus
from builder.extract import Extractor, LlamaExtractor
from builder.ontology import (
    PROV,
    Ontology,
    extraction_triples,
    ontology_from_graph,
    ontology_graph,
    rebase,
)
from eval_config import BuilderConfig

ExportContent = TLiteral["ontology", "kg", "all"]
# builds of sessions nobody looked at for this long pause (they share the extraction model)
IDLE_PAUSE_SECONDS = 60
# session ids are file names in the save dir: no dots or slashes (path traversal, suffixes)
SESSION_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")


def check_session_id(session_id: str) -> str:
    """``session_id`` if it is a valid session id (ValueError otherwise)."""
    if not SESSION_ID_PATTERN.fullmatch(session_id):
        raise ValueError(f"Invalid session id '{session_id}' (letters, digits, '-' and '_' only, at most 64)")
    return session_id


def new_store() -> Graph:
    try:
        from tentris import TentrisStore

        return Graph(store=TentrisStore())
    except Exception:
        # ponytail: native Tentris ships for x86_64 Linux only, rdflib's memory store elsewhere
        return Graph()


class BuildStatus(BaseModel):
    running: bool = False
    processed: int = 0
    total: int = 0
    triples: int = 0
    errors: int = 0
    last_error: str | None = None
    store: str = ""


class Cell(BaseModel):
    value: str
    kind: TLiteral["uri", "literal", "bnode"]
    # rdfs:label of an IRI
    label: str | None = None


class QueryResult(BaseModel):
    columns: list[str] = []
    rows: list[list[Cell | None]] = []
    error: str | None = None
    # build progress at the time of the query, so a client knows whether to refresh
    status: BuildStatus = BuildStatus()


class SessionState(BaseModel):
    session_id: str
    version: int
    ontology: Ontology
    query: str
    visual_query: str | None = None
    status: BuildStatus


def class_query(onto: Ontology, class_id: str, limit: int = 200) -> str:
    """SELECT of the instances of a class with their label, fields and links."""
    cls = onto.get_class(class_id)
    if cls is None:
        raise KeyError(f"Unknown class '{class_id}'")
    variables = [f.name for f in cls.fields] + [l.id for l in onto.links if l.source == class_id]
    optionals = "\n".join(f"  OPTIONAL {{ ?instance onto:{v} ?{v} }}" for v in variables)
    return (
        f"SELECT ?instance ?label {' '.join('?' + v for v in variables)}\nWHERE {{\n"
        f"  ?instance a onto:{class_id} ; rdfs:label ?label .\n{optionals}\n}}\nLIMIT {limit}"
    )


class BuilderSession:
    def __init__(self, session_id: str, builder: "Builder"):
        self.session_id = check_session_id(session_id)
        self.builder = builder
        self.ontology = Ontology(prefix=builder.config.prefix)
        self.query = ""
        # the visual query (the editor's serialized NodeLinkRepository) that generated
        # ``query``, None if the query is plain SPARQL (e.g. the agent's)
        self.visual_query: str | None = None
        # bumped on every change of the ontology or query (clients refetch the state)
        self.version = 0
        # instance triples of an imported TTL, kept across rebuilds
        self.imported = Graph()
        self.graph = new_store()
        # the ontology's own triples (ontology_graph), kept in the store so queries can join
        # classes and properties with the instances; refreshed on every ontology change
        self.schema = Graph()
        self.status = BuildStatus(store=type(self.graph.store).__name__)
        self._generation = 0
        self._lock = threading.RLock()
        self.last_access = time.monotonic()
        # the agent chat (builder.agent.BuilderChat), created by the first connection
        self.chat = None
        self.restore()

    # --- state ---

    def state(self) -> SessionState:
        self.last_access = time.monotonic()
        with self._lock:
            return SessionState(
                session_id=self.session_id, version=self.version,
                ontology=self.ontology.model_copy(deep=True), query=self.query, visual_query=self.visual_query,
                status=self.status.model_copy(),
            )

    def set_ontology(self, onto: Ontology):
        with self._lock:
            rebuild = onto.schema_key() != self.ontology.schema_key()
            self.ontology = onto
            self.version += 1
            if rebuild:
                self.rebuild()
            else:
                self._write_schema()
            self.persist()

    def set_query(self, query: str, visual_query: str | None = None):
        with self._lock:
            self.query = query
            self.visual_query = visual_query
            self.version += 1
            self.persist()

    @cached_property
    def kg(self):
        """This session as a configuration of the config-scoped API (builder/kg.py)."""
        from builder.kg import SessionKG

        return SessionKG(self)

    def _write_schema(self):
        with self._lock:
            for triple in self.schema:
                self.graph.remove(triple)
            self.schema = ontology_graph(self.ontology)
            for triple in self.schema:
                self.graph.add(triple)

    # --- progressive build ---

    def rebuild(self):
        with self._lock:
            self._generation += 1
            self.graph = new_store()
            for triple in self.imported:
                self.graph.add(triple)
            self.schema = Graph()
            self._write_schema()
            docs = list(self.builder.corpus.documents)
            random.Random(0).shuffle(docs)
            self.status = BuildStatus(
                running=bool(self.ontology.classes), total=len(docs),
                triples=len(self.imported), store=type(self.graph.store).__name__,
            )
            if self.ontology.classes:
                threading.Thread(
                    target=self._build, args=(self._generation, self.ontology.model_copy(deep=True), docs),
                    daemon=True,
                ).start()

    def _paused(self) -> bool:
        return time.monotonic() - self.last_access > IDLE_PAUSE_SECONDS

    def _build(self, generation: int, onto: Ontology, docs):
        """Extract ``docs`` with ``extract_instances`` threads and add each result as it
        arrives, until done or ``generation`` is outdated (schema change or stop).

        Only a few documents per thread are queued at a time, so a stop or an idle pause
        takes effect after the extractions in progress; their results are dropped on a stop."""
        workers = self.builder.config.extract_instances
        todo = iter(docs)
        pending = set()
        pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"extract-{self.session_id}")
        try:
            while generation == self._generation:
                if not self._paused():
                    for doc in islice(todo, 2 * workers - len(pending)):
                        pending.add(pool.submit(self._extract, onto, doc))
                elif not pending:
                    time.sleep(1)
                    continue
                if not pending:
                    break
                # with a timeout, to notice a stop while documents are being extracted
                done, pending = wait(pending, timeout=1, return_when=FIRST_COMPLETED)
                for future in done:
                    self._add_extraction(generation, *future.result())
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        with self._lock:
            if generation == self._generation:
                self.status.running = False

    def _extract(self, onto: Ontology, doc) -> tuple:
        """The triples of one document (and its IRI and title), or an error message."""
        doc_iri = URIRef(f"{onto.prefix}doc/{doc.id}".replace(" ", "_"))
        try:
            data = self.builder.extractor.extract(onto, doc.text[: self.builder.config.text_set.max_chars])
            return doc_iri, doc.title, extraction_triples(onto, data, doc_iri), None
        except Exception as e:
            return doc_iri, doc.title, [], f"{type(e).__name__}: {e}"

    def _add_extraction(self, generation: int, doc_iri: URIRef, title: str, triples: list, error: str | None):
        with self._lock:
            if generation != self._generation:
                return
            if triples:
                self.graph.add((doc_iri, RDFS.label, Literal(title)))
            for triple in triples:
                self.graph.add(triple)
            self.status.processed += 1
            self.status.triples = len(self.graph) - len(self.schema)
            if error:
                self.status.errors += 1
                self.status.last_error = error

    def stop(self):
        with self._lock:
            self._generation += 1
            self.status.running = False

    # --- querying ---

    def _prefixed(self, query: str) -> str:
        prologue = {
            "onto": self.ontology.prefix,
            "rdfs": str(RDFS),
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
            "prov": str(PROV),
        }
        lowered = query.lower()
        declared = "".join(
            f"PREFIX {p}: <{ns}>\n" for p, ns in prologue.items() if f"prefix {p}:" not in lowered
        )
        return declared + query

    def run_query(self, query: str | None = None, limit: int = 500) -> QueryResult:
        query = query if query is not None else self.query
        self.last_access = time.monotonic()
        with self._lock:
            status = self.status.model_copy()
            if not query.strip():
                return QueryResult(status=status)
            try:
                result = self.graph.query(self._prefixed(query))
                columns = [str(v) for v in (result.vars or [])]
                rows = []
                for row in result:
                    if len(rows) >= limit:
                        break
                    rows.append([self._cell(value) for value in row])
                return QueryResult(columns=columns, rows=rows, status=status)
            except Exception as e:
                return QueryResult(error=f"{type(e).__name__}: {e}", status=status)

    def _cell(self, value) -> Cell | None:
        if value is None:
            return None
        if isinstance(value, URIRef):
            label = self.graph.value(value, RDFS.label)
            return Cell(value=str(value), kind="uri", label=str(label) if label else None)
        if isinstance(value, Literal):
            return Cell(value=str(value), kind="literal")
        return Cell(value=str(value), kind="bnode")

    # --- import / export ---

    def export(self, content: ExportContent = "all", prefix: str | None = None) -> str:
        with self._lock:
            g = Graph()
            if content in ("ontology", "all"):
                g += ontology_graph(self.ontology)
            if content in ("kg", "all"):
                for triple in self.graph:
                    if triple not in self.schema:
                        g.add(triple)
            g.bind("onto", self.ontology.prefix)
            g.bind("prov", PROV)
            old = self.ontology.prefix
        return rebase(g, old, prefix or old).serialize(format="turtle")

    def import_ttl(self, data: str | bytes, prefix: str | None = None) -> Ontology:
        """Load an ontology (and its instance triples) from Turtle, replacing the current one."""
        g = Graph().parse(data=data, format="turtle")
        onto, instances = ontology_from_graph(g, prefix)
        with self._lock:
            # keep the layout of classes that are imported again
            for cls in onto.classes:
                if (old := self.ontology.get_class(cls.id)) is not None:
                    cls.x, cls.y = old.x, old.y
            self.imported = instances
            self.ontology = onto
            self.version += 1
            self.rebuild()
            self.persist(imported=True)
        return onto

    @property
    def save_path(self) -> Path:
        """``<save_dir>/<builder>/<session>``, the saved files add a suffix."""
        return Path(self.builder.config.save_dir) / self.builder.builder_id / self.session_id

    @property
    def state_path(self) -> Path:
        return self.builder.state_file(self.session_id)

    @property
    def imported_path(self) -> Path:
        return self.save_path.with_name(f"{self.session_id}.imported.ttl")

    def persist(self, imported: bool = False):
        """Write the session's state (ontology with layout, query, visual query) to the save
        dir, and with ``imported`` its imported instance triples; called on every change,
        so the session can be restored by its id after a restart (``restore``)."""
        with self._lock:
            state = {"ontology": self.ontology.model_dump(), "query": self.query, "visual_query": self.visual_query}
            files = {self.state_path: json.dumps(state, indent=2)}
            if imported:
                files[self.imported_path] = self.imported.serialize(format="turtle")
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            for path, text in files.items():
                tmp = path.with_name(path.name + ".tmp")
                tmp.write_text(text)
                os.replace(tmp, path)

    def save(self, content: ExportContent = "all", prefix: str | None = None) -> str:
        """Write the session's state and a TTL export to the save dir."""
        self.persist(imported=True)
        ttl = self.save_path.with_suffix(".ttl")
        ttl.write_text(self.export(content, prefix))
        return str(ttl)

    def restore(self) -> bool:
        """Load the saved state, if there is one, and restart the build."""
        if not self.state_path.exists():
            return False
        state = json.loads(self.state_path.read_text())
        self.ontology = Ontology(**state["ontology"])
        self.query = state.get("query", "")
        self.visual_query = state.get("visual_query")
        if self.imported_path.exists():
            self.imported = Graph().parse(self.imported_path, format="turtle")
        self.rebuild()
        return True


class Builder:
    """Corpus, extraction model, agent LLM and sessions of one builder config."""

    def __init__(self, builder_id: str, config: BuilderConfig, max_sessions: int = 16):
        self.builder_id = builder_id
        self.config = config
        self.max_sessions = max_sessions
        self.sessions: OrderedDict[str, BuilderSession] = OrderedDict()
        self._lock = threading.Lock()

    @cached_property
    def corpus(self) -> Corpus:
        return Corpus.load(self.config.text_set)

    @cached_property
    def extractor(self) -> Extractor:
        return LlamaExtractor(self.config)

    @cached_property
    def agent_llm(self):
        from agent.llm import AgentLLM

        return AgentLLM(self.config.agent)

    def state_file(self, session_id: str) -> Path:
        """Where the state of a session is saved (BuilderSession.persist)."""
        return Path(self.config.save_dir) / self.builder_id / f"{check_session_id(session_id)}.json"

    def session(self, session_id: str | None = None, create: bool = True) -> BuilderSession:
        """The session ``session_id``: loaded, else restored from its save, else (``create``)
        a new one; KeyError if it does not exist and ``create`` is off, ValueError for an
        invalid id."""
        with self._lock:
            session_id = check_session_id(session_id or uuid.uuid4().hex)
            if session_id in self.sessions:
                self.sessions.move_to_end(session_id)
                return self.sessions[session_id]
            if not create and not self.state_file(session_id).exists():
                raise KeyError(f"No session '{session_id}'")
            session = self.sessions[session_id] = BuilderSession(session_id, self)
            while len(self.sessions) > self.max_sessions:
                self.sessions.popitem(last=False)[1].stop()
            return session
