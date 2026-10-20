"""Tools the agent uses to search the ontology and edit the query graph."""

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

from agent.protocol import GraphDetails
from agent.tools import ToolCollection, ToolError, tool
from assistant.assistant_model import AssistantLink, AssistantSubject, QueryGraph
from explorative.exp_model import RETURN_TYPE, FuzzyQuery
from model import Subject, SubjectLink
from utils import wrap_iri

if TYPE_CHECKING:
    from explorative.explorative_support import GuidanceManager
    from ontology import OntologyManager


class ClassCandidate(BaseModel):
    uri: str
    label: str


class LinkCandidate(BaseModel):
    uri: str
    label: str
    # domain and range of the property
    from_uri: str | None = None
    from_label: str | None = None
    to_uri: str | None = None
    to_label: str | None = None


def same_uri(a: str | None, b: str | None) -> bool:
    return a is not None and b is not None and wrap_iri(a) == wrap_iri(b)


class GraphEditorTools(ToolCollection):
    """Ontology search and query graph editing on ``graph``.

    ``details`` keeps the ontology data of the subjects/links the agent added,
    which the frontend needs to render them (see protocol.GraphDetails).
    """

    def __init__(
        self,
        ontology_manager: "OntologyManager",
        guidance: "GuidanceManager",
        graph: QueryGraph | None = None,
        retrieve_k: int = 5,
    ):
        self.ontology_manager = ontology_manager
        self.guidance = guidance
        self.graph = graph if graph is not None else QueryGraph()
        self.retrieve_k = retrieve_k
        self.details = GraphDetails()
        # links seen in search results, by URI; they carry domain/range and counts
        self._known_links: dict[str, SubjectLink] = {}

    def prune_details(self):
        """Forget details of elements that are no longer in the graph."""
        subject_ids = {s.id for s in self.graph.subjects}
        link_ids = {l.id for l in self.graph.links}
        self.details.subjects = {
            k: v for k, v in self.details.subjects.items() if k in subject_ids
        }
        self.details.links = {k: v for k, v in self.details.links.items() if k in link_ids}

    def details_for(self, graph: QueryGraph) -> GraphDetails:
        return GraphDetails(
            subjects={
                s.id: self.details.subjects[s.id]
                for s in graph.subjects
                if s.id in self.details.subjects
            },
            links={
                l.id: self.details.links[l.id]
                for l in graph.links
                if l.id in self.details.links
            },
        )

    def _subject(self, subject_id: str) -> AssistantSubject:
        subject = self.graph.get_subject_by_id(subject_id)
        if subject is None:
            raise ToolError(
                f"Subject {subject_id} is not in the query graph, existing subjects: "
                f"{[s.id for s in self.graph.subjects]}"
            )
        return subject

    @tool()
    def search_classes(self, query: str) -> list[ClassCandidate]:
        """Search the ontology for classes matching a description of a subject.

        Args:
            query: what the user is looking for, e.g. "ship" or "military person".

        Returns:
            The best matching classes as [{"uri": "<http://dbpedia.org/ontology/Ship>", "label": "ship"}, ...].
            Use their uri with add_subject.
        """
        results = self.guidance.search_fuzzy(
            FuzzyQuery(q=query, type=RETURN_TYPE.SUBJECT, limit=self.retrieve_k)
        )
        candidates: dict[str, ClassCandidate] = {}
        for result in results.results:
            if result.subject is not None and result.subject.subject_id not in candidates:
                candidates[result.subject.subject_id] = ClassCandidate(
                    uri=result.subject.subject_id,
                    label=result.subject.label or result.subject.subject_id,
                )
        return list(candidates.values())

    @tool()
    def search_links(
        self,
        query: str,
        class_uri: str,
        side: Literal["source", "target"] = "source",
    ) -> list[LinkCandidate]:
        """Search the ontology for properties (links) connecting a class to other classes.

        Args:
            query: how the user wants to connect the subjects, e.g. "homeport" or "commander".
            class_uri: URI of the class the link attaches to, e.g. "<http://dbpedia.org/ontology/Ship>".
            side: "source" for links going out of the class, "target" for links pointing to it.

        Returns:
            Matching links with their domain (from_*) and range (to_*), e.g.
            [{"uri": "<http://dbpedia.org/ontology/homeport>", "label": "homeport",
              "from_uri": "<http://dbpedia.org/ontology/Ship>", "to_uri": "<http://dbpedia.org/ontology/Port>"}, ...].
            Use their uri with add_link.
        """
        results = self.guidance.search_fuzzy(
            FuzzyQuery(
                q=query,
                type=RETURN_TYPE.LINK,
                from_id=class_uri if side == "source" else None,
                to_id=class_uri if side == "target" else None,
                limit=self.retrieve_k,
                include_thing=False,
            )
        )
        candidates: dict[str, LinkCandidate] = {}
        for result in results.results:
            link = result.link
            if link is None or link.property_id is None or link.property_id in candidates:
                continue
            self._known_links[wrap_iri(link.property_id)] = link
            candidates[link.property_id] = LinkCandidate(
                uri=link.property_id,
                label=link.label or link.property_id,
                from_uri=link.from_id,
                from_label=link.from_subject.label if link.from_subject else None,
                to_uri=link.to_id,
                to_label=link.to_subject.label if link.to_subject else None,
            )
        return list(candidates.values())

    @tool()
    def add_subject(self, uri: str) -> AssistantSubject:
        """Add a class as a new subject (node) to the query graph.

        Args:
            uri: URI of the class, as returned by search_classes.

        Returns:
            The added subject; reference it by its "id" in add_link and remove_subject.
        """
        # same data as GET /classes/subjects, which the editor loads for new nodes
        subject: Subject | None = self.ontology_manager.enrich_subject(uri)
        # unknown URIs enrich to a subject without any statements
        if subject is None or not subject.spos:
            raise ToolError(f"Class {uri} does not exist, search it with search_classes.")
        added = AssistantSubject.from_subject(subject, id="")
        self.graph.add_subject(added)
        self.details.subjects[added.id] = subject
        return added

    @tool()
    def add_link(self, from_id: str, to_id: str, uri: str) -> AssistantLink:
        """Connect two subjects of the query graph with a link (property).

        Args:
            from_id: id of the source subject in the query graph (not its URI).
            to_id: id of the target subject in the query graph (not its URI).
            uri: URI of the property, as returned by search_links.

        Returns:
            The added link; reference it by its "id" in remove_link.
        """
        self._subject(from_id)
        self._subject(to_id)
        link = self._known_links.get(wrap_iri(uri))
        if link is None:
            prop = self.ontology_manager.enrich_subject(uri)
            if prop is None or "rdfs:domain" not in prop.spos:
                raise ToolError(f"Property {uri} does not exist, search it with search_links.")
            link = prop.to_link()
        added = AssistantLink.from_link(
            graph=self.graph,
            link=link,
            from_subject_id=from_id,
            to_subject_id=to_id,
            id="",
        )
        self.graph.add_link(added)
        self.details.links[added.id] = link
        return added

    @tool()
    def remove_subject(self, subject_id: str) -> dict:
        """Remove a subject and all links attached to it from the query graph.

        Args:
            subject_id: id of the subject in the query graph.
        """
        self._subject(subject_id)
        self.graph.remove_subject(subject_id)
        self.prune_details()
        return {"success": f"Subject {subject_id} removed from the query graph."}

    @tool()
    def remove_link(self, link_id: str) -> dict:
        """Remove a link from the query graph.

        Args:
            link_id: id of the link in the query graph.
        """
        if not self.graph.has_link(link_id):
            raise ToolError(
                f"Link {link_id} is not in the query graph, existing links: "
                f"{[l.id for l in self.graph.links]}"
            )
        self.graph.remove_link(link_id)
        self.prune_details()
        return {"success": f"Link {link_id} removed from the query graph."}

    @tool()
    def get_query_graph(self) -> QueryGraph:
        """Get the current query graph: its subjects (nodes) and the links between them."""
        return self.graph
