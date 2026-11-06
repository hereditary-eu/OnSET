"""A builder session as a configuration of the config-scoped API (api/config.py).

``get_manman`` resolves the config id ``builder:<builder_id>:<session_id>`` to the
session's ``SessionKG``, which has the ManMan attributes the visual query editor
and the results view use: a real ``OntologyManager`` over the session's store
(ontology triples + extracted KG) and ``SessionGuidance``, the class/link search
of ``GuidanceManager`` by substring over the session's ontology (no embeddings).
Routes needing other services (topics, embeddings, LLM search, agent) fail.
"""

from rdflib import Graph

from builder.ontology import FIELD_RANGES, Ontology
from eval_config import EvalConfig, MultimodalConfig
from explorative.exp_model import RELATION_TYPE, RETURN_TYPE, FuzzyQuery, FuzzyQueryResult, FuzzyQueryResults
from model import SubjectLink
from ontology import OntologyConfig, OntologyManager


class LockedGraph(Graph):
    """A Graph on the session graph's store and context whose queries run (and are read) under the session
    lock, as the build thread adds triples concurrently."""

    def __init__(self, graph: Graph, lock):
        super().__init__(store=graph.store, identifier=graph.identifier)
        self._session_lock = lock

    def query(self, *args, **kwargs):
        with self._session_lock:
            result = super().query(*args, **kwargs)
            if result.type == "SELECT":
                result.bindings  # materialise while locked
            return result


def score(q: str, *texts: str | None) -> float | None:
    """0 for an empty query or a prefix match, 0.5 for a substring match, None otherwise."""
    q = (q or "").strip().lower()
    if not q:
        return 0.0
    texts = [t.lower() for t in texts if t]
    if any(t.startswith(q) for t in texts):
        return 0.0
    if any(q in t for t in texts):
        return 0.5
    return None


class SessionGuidance:
    """``GuidanceManager``'s search over the classes, links and fields of a session's ontology.

    Ids are prefixed (``onto:Person``) as OntologyManager renders them. There is no class
    hierarchy, so a class's subclasses are the class itself and its links are its own."""

    def __init__(self, onto: Ontology, oman: OntologyManager):
        self.onto = onto
        self.oman = oman

    def _local(self, uri: str | None) -> str | None:
        if uri is None:
            return None
        uri = uri.strip().strip("<>")
        for ns in ("onto:", self.onto.prefix):
            if uri.startswith(ns):
                return uri[len(ns):]
        return uri

    def _links(self, relation_type: RELATION_TYPE | None) -> list[SubjectLink]:
        """Object links (INSTANCE) and/or fields as datatype properties (PROPERTY), unenriched."""
        links = []
        if relation_type in (RELATION_TYPE.INSTANCE, None):
            for i, l in enumerate(self.onto.links):
                links.append(SubjectLink(
                    link_id=i, label=l.label or l.id, from_id=f"onto:{l.source}", link_type="owl:ObjectProperty",
                    to_id=f"onto:{l.target}", to_proptype=None, property_id=f"onto:{l.id}",
                    from_subject=None, to_subject=None,
                ))
        if relation_type in (RELATION_TYPE.PROPERTY, None):
            for c in self.onto.classes:
                for f in c.fields:
                    links.append(SubjectLink(
                        link_id=-1, label=f.name, from_id=f"onto:{c.id}", link_type="owl:DatatypeProperty",
                        to_id=None, to_proptype=self.oman.to_prefix(str(FIELD_RANGES[f.type])),
                        property_id=f"onto:{f.name}", from_subject=None, to_subject=None,
                    ))
        return links

    def _enrich(self, link: SubjectLink) -> SubjectLink:
        link.from_subject = self.oman.enrich_subject(link.from_id)
        link.to_subject = self.oman.enrich_subject(link.to_id) if link.to_id else None
        return link

    def search_fuzzy(self, query: FuzzyQuery) -> FuzzyQueryResults:
        results: list[FuzzyQueryResult] = []
        if query.type in (RETURN_TYPE.SUBJECT, RETURN_TYPE.BOTH):
            for c in self.onto.classes:
                s = score(query.q, c.label, c.id, c.description)
                if s is not None:
                    results.append(FuzzyQueryResult(subject=self.oman.enrich_subject(f"onto:{c.id}"), score=s))
        if query.type in (RETURN_TYPE.LINK, RETURN_TYPE.BOTH):
            from_ids = query.from_id if isinstance(query.from_id, list) else [query.from_id] if query.from_id else None
            from_ids = {self._local(f) for f in from_ids} if from_ids else None
            to_id = self._local(query.to_id)
            for link in self._links(query.relation_type):
                if from_ids is not None and self._local(link.from_id) not in from_ids:
                    continue
                if to_id is not None and self._local(link.to_id) != to_id:
                    continue
                s = score(query.q, link.label, link.property_id)
                if s is not None:
                    results.append(FuzzyQueryResult(link=link, score=s))
        results.sort(key=lambda r: r.score)
        results = results[query.skip or 0:][: query.limit or None]
        for r in results:
            if r.link is not None:
                self._enrich(r.link)
        return FuzzyQueryResults(results=results)

    def search_subclasses(self, query: FuzzyQuery) -> FuzzyQueryResults:
        cls = self.onto.get_class(self._local(query.from_id) or "")
        if cls is None:
            return FuzzyQueryResults(results=[])
        return FuzzyQueryResults(results=[FuzzyQueryResult(subject=self.oman.enrich_subject(f"onto:{cls.id}"))])

    def search_links(self, q: str | None = None, from_id: str | None = None, to_id: str | None = None) -> list[SubjectLink]:
        query = FuzzyQuery(q=q, from_id=from_id, to_id=to_id, type=RETURN_TYPE.LINK, relation_type=None)
        return [r.link for r in self.search_fuzzy(query).results]

    def get_link(self, property_id: str) -> SubjectLink | None:
        local = self._local(property_id)
        link = next((l for l in self._links(None) if self._local(l.property_id) == local), None)
        return self._enrich(link) if link else None


class SessionKG:
    """The ManMan attributes the config-scoped routes of the query editor use, for a builder session."""

    def __init__(self, session):
        self.session = session
        self.config_id = f"builder:{session.builder.builder_id}:{session.session_id}"
        self.db_config = EvalConfig(
            name=session.builder.config.name, description=session.builder.config.description,
        )
        self._graph = None

    @property
    def config(self) -> OntologyConfig:
        return self.ontology_manager.config

    @property
    def ontology_manager(self) -> OntologyManager:
        # a new store on every rebuild (and with it a new prefix)
        if self._graph is not self.session.graph:
            self._graph = self.session.graph
            config = OntologyConfig(
                multimodal_config=MultimodalConfig(image_vector_properties=[], image_properties=[], image_types=[]),
            )
            config.additional_namespaces["onto"] = self.session.ontology.prefix
            self._oman = OntologyManager(config, LockedGraph(self._graph, self.session._lock))
        return self._oman

    @property
    def guidance_man(self) -> SessionGuidance:
        return SessionGuidance(self.session.ontology, self.ontology_manager)
