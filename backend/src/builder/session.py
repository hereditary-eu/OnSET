"""Ontology builder sessions: the ontology, its progressively built KG and a query.

Every schema change of the ontology (and every change of the session's disambiguation
settings, builder/disambiguate.py) restarts the build: a fresh triple store
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
from functools import cached_property, wraps
from itertools import islice
from pathlib import Path
from typing import Literal as TLiteral

from pydantic import BaseModel
from rdflib import DCTERMS, RDF, RDFS, SKOS, Graph, Literal, URIRef

from builder.corpus import Corpus
from builder.disambiguate import Disambiguator, Judge, LlamaJudge, Merge
from builder.extract import Extractor, LlamaExtractor
from builder.ontology import (
    PROV,
    Ontology,
    document_iri,
    document_triples,
    extraction_triples,
    ontology_from_graph,
    ontology_graph,
    rebase,
)
from eval_config import BuilderConfig, DisambiguationSettings

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


def add_all(graph: Graph, triples, chunk: int = 10_000):
    """Add ``triples`` in a few batched updates: Tentris runs every ``Graph.add`` as an update
    of its own whose cost grows with the store (5 ms per triple at 160k triples, a batch of
    300 takes 20 ms), which kept the session lock busy during long builds."""
    batch = []
    for s, p, o in triples:
        batch.append((s, p, o, graph))
        if len(batch) >= chunk:
            graph.addN(batch)
            batch = []
    if batch:
        graph.addN(batch)


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
    # extracted names merged into an instance with another name (disambiguation)
    merged: int = 0


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


class LinkCount(BaseModel):
    """Triples of a link (or field) of the ontology between instances of its classes in the KG."""
    # prefixed as the query editor's ids (``onto:Person``)
    from_id: str
    property_id: str
    # None for a field (a datatype property)
    to_id: str | None = None
    count: int


class LinkCounts(BaseModel):
    # the build status' triple count the counts are of (clients refetch when it changes)
    triples: int
    links: list[LinkCount] = []


class SourceDocument(BaseModel):
    """A corpus document an instance was extracted from."""
    iri: str
    # its corpus id (the documents route's ``doc_id``), None if the KG names no document
    # of the corpus (e.g. imported from another corpus)
    doc_id: str | None = None
    title: str = ""


class InstanceProvenance(BaseModel):
    iri: str
    label: str | None = None
    # the other names it was extracted as (merged by disambiguation)
    aliases: list[str] = []
    documents: list[SourceDocument] = []


class SessionState(BaseModel):
    session_id: str
    version: int
    ontology: Ontology
    query: str
    visual_query: str | None = None
    status: BuildStatus
    disambiguation: DisambiguationSettings = DisambiguationSettings()


class DisambiguationState(BaseModel):
    settings: DisambiguationSettings
    # names merged in the current build, judge calls, and the latest merges (newest first)
    merged: int = 0
    judged: int = 0
    merges: list[Merge] = []


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
        # how extracted names are merged into instances (saved with the session)
        self.disambiguation = builder.config.disambiguation.model_copy()
        # the current build's disambiguator, and the judge's verdicts (kept across builds)
        self.disambiguator: Disambiguator | None = None
        self._judgments: OrderedDict = OrderedDict()
        self._generation = 0
        self._lock = threading.RLock()
        # (key, LinkCounts) of the last link_counts, see there
        self._link_counts: tuple | None = None
        self.last_access = time.monotonic()
        # the agent chat (builder.agent.BuilderChat), created by the first connection
        self.chat = None
        # the chat's history, saved with the session and only reset by the user (clear_chat):
        # the model's input items after the system prompt, and the chat as the UI shows it
        # (``user_message`` frames and the final protocol frames, agent.protocol.ChatHistory)
        self.chat_history: list[dict] = []
        self.chat_log: list[dict] = []
        self.restore()

    # --- state ---

    def state(self) -> SessionState:
        self.last_access = time.monotonic()
        with self._lock:
            return SessionState(
                session_id=self.session_id, version=self.version,
                ontology=self.ontology.model_copy(deep=True), query=self.query, visual_query=self.visual_query,
                status=self.status.model_copy(), disambiguation=self.disambiguation.model_copy(),
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

    def set_disambiguation(self, settings: DisambiguationSettings):
        """Change how names are merged: a different setting rebuilds the KG from scratch."""
        with self._lock:
            if settings == self.disambiguation:
                return
            self.disambiguation = settings.model_copy()
            self.version += 1
            self.rebuild()
            self.persist()

    def disambiguation_state(self) -> DisambiguationState:
        self.last_access = time.monotonic()
        with self._lock:
            dis = self.disambiguator
            return DisambiguationState(
                settings=self.disambiguation.model_copy(),
                merged=dis.merged if dis else 0, judged=dis.judged if dis else 0,
                merges=list(dis.merges)[::-1] if dis else [],
            )

    def set_query(self, query: str, visual_query: str | None = None):
        with self._lock:
            self.query = query
            self.visual_query = visual_query
            self.version += 1
            self.persist()

    # --- agent chat history ---

    def chat_transcript(self) -> list[dict]:
        with self._lock:
            return list(self.chat_log)

    def log_chat(self, entry: dict):
        """Add an entry to the chat as the UI shows it (saved with the next persist)."""
        with self._lock:
            self.chat_log.append(entry)

    def save_chat(self, history: list[dict]):
        """Keep the model's chat history (after a turn) and save the session."""
        with self._lock:
            self.chat_history = list(history)
            self.persist()

    def clear_chat(self):
        with self._lock:
            self.chat_history, self.chat_log = [], []
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
            add_all(self.graph, self.schema)

    # --- progressive build ---

    def rebuild(self):
        with self._lock:
            self._generation += 1
            self.graph = new_store()
            add_all(self.graph, self.imported)
            self.schema = Graph()
            self._write_schema()
            docs = list(self.builder.corpus.documents)
            random.Random(0).shuffle(docs)
            self.status = BuildStatus(
                running=bool(self.ontology.classes), total=len(docs),
                triples=len(self.imported), store=type(self.graph.store).__name__,
            )
            onto = self.ontology.model_copy(deep=True)
            self.disambiguator = self._disambiguator(onto)
            if self.ontology.classes:
                threading.Thread(
                    target=self._build, args=(self._generation, onto, docs, self.disambiguator),
                    daemon=True,
                ).start()

    def _disambiguator(self, onto: Ontology) -> Disambiguator:
        """The disambiguator of a new build, knowing the imported instances (and their aliases)."""
        dis = Disambiguator(onto, self.disambiguation.model_copy(), lambda: self.builder.judge, self._judgments)
        if dis.active:
            classes = {onto.term(c.id): c.id for c in onto.classes}
            for s, _, cls in self.imported.triples((None, RDF.type, None)):
                label = self.imported.value(s, RDFS.label)
                if cls in classes and isinstance(s, URIRef) and label is not None:
                    aliases = [str(a) for a in self.imported.objects(s, SKOS.altLabel)]
                    dis.register(classes[cls], str(label), s, aliases)
        return dis

    def _paused(self) -> bool:
        return time.monotonic() - self.last_access > IDLE_PAUSE_SECONDS

    def _build(self, generation: int, onto: Ontology, docs, dis: Disambiguator | None = None):
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
                        pending.add(pool.submit(self._extract, onto, doc, dis))
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

    def _extract(self, onto: Ontology, doc, dis: Disambiguator | None = None) -> tuple:
        """The triples of one document (its instances' plus, if it has any, the document's
        own: provenance), or an error message; names are resolved to their instances by ``dis``
        (in this extraction thread)."""
        doc_iri = document_iri(onto.prefix, doc.id)
        try:
            text = doc.text[: self.builder.config.text_set.max_chars]
            data = self.builder.extractor.extract(onto, text)
            resolve = dis.resolver(text) if dis is not None else None
            triples = extraction_triples(onto, data, doc_iri, resolve)
            if triples:
                triples = document_triples(onto.prefix, doc.id, doc.title) + triples
            return triples, None
        except Exception as e:
            return [], f"{type(e).__name__}: {e}"

    def _add_extraction(self, generation: int, triples: list, error: str | None):
        with self._lock:
            if generation != self._generation:
                return
            if triples:
                add_all(self.graph, triples)
            self.status.processed += 1
            self.status.triples = len(self.graph) - len(self.schema)
            if self.disambiguator is not None:
                self.status.merged = self.disambiguator.merged
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
            "skos": str(SKOS),
            "dcterms": str(DCTERMS),
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

    def link_counts(self) -> LinkCounts:
        """The triple count of every link (subject class, predicate, object class) and field
        (class, predicate) of the ontology in the KG, e.g. for the link widths of the query editor.

        One COUNT per link/field, each under the session lock on its own (so extraction goes on
        in between); cached until the KG (its triple count or build) or the schema changes."""
        with self._lock:
            onto, graph = self.ontology, self.graph
            key = (self._generation, self.status.triples, onto.schema_key())
            if self._link_counts is not None and self._link_counts[0] == key:
                return self._link_counts[1]
        a = "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>"
        patterns = [
            (l.source, l.id, l.target, f"?s <{onto.term(l.id)}> ?o . ?s {a} <{onto.term(l.source)}> . "
                                       f"?o {a} <{onto.term(l.target)}> .")
            for l in onto.links
        ] + [
            (c.id, f.name, None, f"?s <{onto.term(f.name)}> ?o . ?s {a} <{onto.term(c.id)}> .")
            for c in onto.classes for f in c.fields
        ]
        links = []
        for source, prop, target, pattern in patterns:
            with self._lock:
                try:
                    rows = list(graph.query(f"SELECT (COUNT(*) AS ?n) WHERE {{ {pattern} }}"))
                    count = int(rows[0][0]) if rows and rows[0][0] is not None else 0
                except Exception:
                    count = 0
            links.append(LinkCount(
                from_id=f"onto:{source}", property_id=f"onto:{prop}",
                to_id=f"onto:{target}" if target else None, count=count,
            ))
        counts = LinkCounts(triples=key[1], links=links)
        with self._lock:
            self._link_counts = (key, counts)
        return counts

    def provenance(self, iri: str) -> InstanceProvenance:
        """The documents the instance ``iri`` was extracted from (``prov:wasDerivedFrom``), with
        its label and aliases (to find it in their text)."""
        self.last_access = time.monotonic()
        corpus = self.builder.corpus.by_id
        node = URIRef(iri)
        with self._lock:
            graph = self.graph
            label = graph.value(node, RDFS.label)
            # without disambiguation an instance has every name as a label
            names = [*graph.objects(node, RDFS.label), *graph.objects(node, SKOS.altLabel)]
            aliases = sorted({str(a) for a in names} - {str(label)})
            documents = []
            for doc in sorted(set(graph.objects(node, PROV.wasDerivedFrom)), key=str):
                doc_id = graph.value(doc, DCTERMS.identifier)
                title = graph.value(doc, RDFS.label)
                documents.append(SourceDocument(
                    iri=str(doc), doc_id=str(doc_id) if doc_id is not None and str(doc_id) in corpus else None,
                    title=str(title) if title is not None else str(doc),
                ))
        return InstanceProvenance(
            iri=iri, label=str(label) if label is not None else None, aliases=aliases, documents=documents,
        )

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
            g.bind("dcterms", DCTERMS)
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
        """Write the session's state (ontology with layout, query, visual query, agent chat,
        disambiguation settings) to
        the save dir, and with ``imported`` its imported instance triples; called on every change,
        so the session can be restored by its id after a restart (``restore``)."""
        with self._lock:
            state = {
                "ontology": self.ontology.model_dump(), "query": self.query, "visual_query": self.visual_query,
                "chat": {"history": self.chat_history, "log": self.chat_log},
                "disambiguation": self.disambiguation.model_dump(),
            }
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
        # saves from before the chat was kept have none
        chat = state.get("chat") or {}
        self.chat_history = list(chat.get("history") or [])
        self.chat_log = list(chat.get("log") or [])
        # saves from before disambiguation keep the builder's default
        if state.get("disambiguation"):
            self.disambiguation = DisambiguationSettings(**state["disambiguation"])
        if self.imported_path.exists():
            self.imported = Graph().parse(self.imported_path, format="turtle")
        self.rebuild()
        return True


def _locked_cached_property(fn):
    """cached_property computed once under the instance's ``_init_lock`` (functools'
    cached_property has no lock, so concurrent first uses would e.g. load the models twice)."""
    name = fn.__name__

    @property
    @wraps(fn)
    def prop(self):
        try:
            return self.__dict__[name]
        except KeyError:
            pass
        with self._init_lock:
            if name not in self.__dict__:
                self.__dict__[name] = fn(self)
            return self.__dict__[name]

    @prop.setter
    def prop(self, value):
        self.__dict__[name] = value

    return prop


class Builder:
    """Corpus, extraction model, agent LLM and sessions of one builder config."""

    def __init__(self, builder_id: str, config: BuilderConfig, max_sessions: int = 16):
        self.builder_id = builder_id
        self.config = config
        self.max_sessions = max_sessions
        self.sessions: OrderedDict[str, BuilderSession] = OrderedDict()
        self._lock = threading.Lock()
        self._session_locks: dict[str, threading.Lock] = {}
        self._init_lock = threading.RLock()

    @_locked_cached_property
    def corpus(self) -> Corpus:
        return Corpus.load(self.config.text_set)

    @_locked_cached_property
    def extractor(self) -> Extractor:
        return LlamaExtractor(self.config)

    @_locked_cached_property
    def judge(self) -> Judge:
        """The llm_judge disambiguation's judge (its model loads on the first judgment)."""
        return LlamaJudge(self.config)

    @_locked_cached_property
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
        session_id = check_session_id(session_id or uuid.uuid4().hex)
        with self._lock:
            if session_id in self.sessions:
                self.sessions.move_to_end(session_id)
                return self.sessions[session_id]
            if not create and not self.state_file(session_id).exists():
                raise KeyError(f"No session '{session_id}'")
            session_lock = self._session_locks.setdefault(session_id, threading.Lock())
        # restoring a session (corpus load, imported KG) is slow: done outside the builder's
        # lock so other sessions stay responsive, once per id
        with session_lock:
            with self._lock:
                if session_id in self.sessions:
                    return self.sessions[session_id]
            session = BuilderSession(session_id, self)
            evicted = []
            with self._lock:
                self.sessions[session_id] = session
                self._session_locks.pop(session_id, None)
                while len(self.sessions) > self.max_sessions:
                    evicted.append(self.sessions.popitem(last=False)[1])
        # stopping waits for the session's lock (a running query), so not under the builder's
        for old in evicted:
            old.stop()
        return session
