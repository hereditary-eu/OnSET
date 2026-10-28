from pydantic import BaseModel, Field
import enum
from typing import Annotated, Literal, TYPE_CHECKING

from model import Subject, SubjectLink

if TYPE_CHECKING:
    from api.config import ManMan


# Canonical query-graph representations of the backend.
#
# 1. QueryGraph (AssistantSubject/AssistantLink/subqueries) and Operations:
#    the state of the visual query editor, used for agentic graph editing.
#    The subqueries mirror frontend/src/utils/sparql/representation/subqueries.ts
# 2. EntitiesRelations and its Candidate*/Enriched* variants: the prototype
#    query graphs of the NL -> entities/relations pipeline (explorative.llm_query),
#    which double as the grammar for constrained LLM output, so their field
#    names are part of the prompts and must not change.
#
# NOTE: exploration/llm_tool_exploration.ipynb star-imports this module.


class AssistantSubQueryType(str, enum.Enum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    SUBJECT = "subject"
    QUERY_PROP = "query_prop"
    INSTANCE_PROP = "instance_prop"

    VECTOR_SORT = "vector_sort"
    IMAGE_PROP = "image_prop"


class AssistantSubQuery(BaseModel):
    type: AssistantSubQueryType
    id: str | None = None
    # property (URI) of the subject this subquery applies to
    property_id: str | None = None


class QueryPropSubQuery(AssistantSubQuery):
    type: Literal[AssistantSubQueryType.QUERY_PROP] = AssistantSubQueryType.QUERY_PROP
    property_id: str


class SubjectSubQuery(AssistantSubQuery):
    type: Literal[AssistantSubQueryType.SUBJECT] = AssistantSubQueryType.SUBJECT
    # id of the selected instance, no constraint if None
    instance_id: str | None = None
    instance_label: str | None = None


class AssistantStringConstraintType(str, enum.Enum):
    EQUALS = "equals"
    NEQUALS = "!="
    CONTAINS = "contains"
    STARTSWITH = "startswith"
    ENDSWITH = "endswith"
    REGEX = "regex"


class StringSubQuery(AssistantSubQuery):
    type: Literal[AssistantSubQueryType.STRING] = AssistantSubQueryType.STRING
    value: str = ""
    operator: AssistantStringConstraintType = AssistantStringConstraintType.CONTAINS


class AssistantNumberConstraintType(str, enum.Enum):
    EQUALS = "equals"
    LESS = "less"
    GREATER = "greater"


class NumberSubQuery(AssistantSubQuery):
    type: Literal[AssistantSubQueryType.NUMBER] = AssistantSubQueryType.NUMBER
    value: float = 0
    operator: AssistantNumberConstraintType = AssistantNumberConstraintType.GREATER


class BooleanSubQuery(AssistantSubQuery):
    type: Literal[AssistantSubQueryType.BOOLEAN] = AssistantSubQueryType.BOOLEAN
    value: bool = False


class DateSubQuery(AssistantSubQuery):
    type: Literal[AssistantSubQueryType.DATE] = AssistantSubQueryType.DATE
    # ISO 8601 date(time) string
    value: str
    operator: AssistantNumberConstraintType = AssistantNumberConstraintType.GREATER


class VectorSortModality(str, enum.Enum):
    IMAGE = "image"
    TEXT = "text"


class VectorSortDirection(str, enum.Enum):
    ASCENDING = "ascending"
    DESCENDING = "descending"


class VectorSortDistance(str, enum.Enum):
    COSINE = "cosine"
    EUCLIDEAN = "euclidean"
    MANHATTAN = "manhattan"


class VectorSortInputState(BaseModel):
    image: str | None = None
    text: str | None = None


class VectorSortSubQuery(AssistantSubQuery):
    type: Literal[AssistantSubQueryType.VECTOR_SORT] = AssistantSubQueryType.VECTOR_SORT
    modality: VectorSortModality = VectorSortModality.IMAGE
    direction: VectorSortDirection = VectorSortDirection.DESCENDING
    distance: VectorSortDistance = VectorSortDistance.COSINE
    vector: list[float] | None = None
    input_state: VectorSortInputState = Field(default_factory=VectorSortInputState)


AnyAssistantSubQuery = Annotated[
    QueryPropSubQuery
    | SubjectSubQuery
    | StringSubQuery
    | NumberSubQuery
    | BooleanSubQuery
    | DateSubQuery
    | VectorSortSubQuery,
    Field(discriminator="type"),
]


class AssistantSubject(BaseModel):
    uri: str
    label: str
    id: str | None = None
    subqueries: list[AnyAssistantSubQuery] = Field([])

    @staticmethod
    def from_subject(subject: Subject, id: str | None = None) -> "AssistantSubject":
        return AssistantSubject(
            uri=subject.subject_id,
            label=subject.label or subject.subject_id,
            id=id,
        )

    def get_full(self, manman: "ManMan", load_properties: bool = True) -> Subject:
        return manman.ontology_manager.enrich_subject(
            self.uri, load_properties=load_properties
        )


class AssistantLink(BaseModel):
    uri: str
    label: str
    id: str | None = None
    from_subject_id: str | None = None
    to_subject_id: str | None = None

    from_subject_label: str | None = None
    from_subject_uri: str | None = None

    to_subject_label: str | None = None
    to_subject_uri: str | None = None

    @staticmethod
    def from_link(
        graph: "QueryGraph",
        link: SubjectLink,
        from_subject_id: str,
        to_subject_id: str,
        id: str | None = None,
        force_complete: bool = True,
    ) -> "AssistantLink":
        """from_subject/to_subject are the internal ids of the linked AssistantSubjects."""
        from_subject = graph.get_subject_by_id(from_subject_id)
        to_subject = graph.get_subject_by_id(to_subject_id)
        if (from_subject is None or to_subject is None) and force_complete:
            raise ValueError(
                f"from_subject_id {from_subject_id} or to_subject_id {to_subject_id} not found in graph."
            )
        link = AssistantLink(
            uri=link.property_id,
            label=link.label or link.property_id,
            id=id,
            from_subject_id=from_subject_id,
            to_subject_id=to_subject_id,
        )
        if from_subject is not None:
            link.from_subject_label = from_subject.label
            link.from_subject_uri = from_subject.uri
        if to_subject is not None:
            link.to_subject_label = to_subject.label
            link.to_subject_uri = to_subject.uri
        return link

    def get_full(self, manman: "ManMan"):
        subject = manman.ontology_manager.enrich_subject(self.uri, load_properties=True)
        if subject is not None:
            return subject.to_link()
        return None


class QueryGraph(BaseModel):
    subjects: list[AssistantSubject] = Field([])
    links: list[AssistantLink] = Field([])

    def get_subject_by_id(self, id: str) -> AssistantSubject | None:
        for subject in self.subjects:
            if subject.id == id:
                return subject
        return None

    def has_subject(self, subject_id: str) -> bool:
        return any(s.id == subject_id for s in self.subjects)

    def has_link(self, link_id: str) -> bool:
        return any(l.id == link_id for l in self.links)

    def next_id(self, prefix: str) -> str:
        existing_ids = []
        existing_ids += [
            subject.id for subject in self.subjects if subject.id is not None
        ]
        existing_ids += [link.id for link in self.links if link.id is not None]
        next_id = 1
        while f"{prefix}{next_id}" in existing_ids:
            next_id += 1
        return f"{prefix}{next_id}"

    def next_subject_id(self) -> str:
        return self.next_id("subject_")

    def next_link_id(self) -> str:
        return self.next_id("link_")

    def add_subject(self, subject: AssistantSubject):
        if subject.id is None or subject.id == "":
            subject.id = self.next_id(
                prefix=subject.label.replace(" ", "_").lower() + "_"
            )
        self.subjects.append(subject)

    def add_link(self, link: AssistantLink):
        assert self.has_subject(link.from_subject_id), (
            f"from_subject_id {link.from_subject_id} not found in graph."
        )
        assert self.has_subject(link.to_subject_id), (
            f"to_subject_id {link.to_subject_id} not found in graph."
        )
        if link.id is None or link.id == "":
            link.id = self.next_id(prefix=link.label.replace(" ", "_").lower() + "_")
        assert not self.has_link(link.id), f"link id {link.id} already exists in graph."
        self.links.append(link)

    def remove_subject(self, subject_id: str):
        assert self.has_subject(subject_id), (
            f"subject_id {subject_id} not found in graph."
        )
        self.subjects = [s for s in self.subjects if s.id != subject_id]
        self.links = [
            l
            for l in self.links
            if l.from_subject_id != subject_id and l.to_subject_id != subject_id
        ]

    def remove_link(self, link_id: str):
        assert self.has_link(link_id), f"link_id {link_id} not found in graph."
        self.links = [l for l in self.links if l.id != link_id]


class OperationType(str, enum.Enum):
    ADD = "add"
    REMOVE = "remove"


class Operation(BaseModel):
    operation: OperationType
    data: AssistantLink | AssistantSubject | AnyAssistantSubQuery


class Operations(BaseModel):
    operations: list[Operation] = Field([])


# --- Prototype query graphs of the NL -> entities/relations (ERL) pipeline ---


class Constraint(BaseModel):
    property: str
    value: str | None
    modifier: str | None


class Entity(BaseModel):
    identifier: str
    type: str
    constraints: list[Constraint] = Field([])


class Relation(BaseModel):
    entity: str
    relation: str
    target: str


class EntitiesRelations(BaseModel):
    relations: list[Relation] = Field([])
    entities: list[Entity] = Field([])
    message: str = Field("Found Relations and Entities")


class CandidateRelation(Relation):
    score: float
    link: SubjectLink | None = Field(None)


class CandidateConstraint(Constraint):
    score: float
    type: str
    property: str
    entity: str
    link: SubjectLink | None = Field(None)


class CandidateEntity(Entity):
    score: float
    type: str
    subject: Subject | None = Field(None)


class Candidates(EntitiesRelations):
    relations: list[CandidateRelation] = Field([])
    entities: list[CandidateEntity] = Field([])
    # constraints: list[CandidateConstraint] = Field([])


class EnrichedConstraint(Constraint):
    constraint: SubjectLink | None


class EnrichedEntity(Entity):
    subject: Subject
    # constraints: list[EnrichedConstraint] = Field([])


class EnrichedRelation(Relation):
    link: SubjectLink | None


class EnrichedEntitiesRelations(EntitiesRelations):
    relations: list[EnrichedRelation] = Field([])
    entities: list[EnrichedEntity] = Field([])


class QueryProgress(BaseModel):
    id: str
    start_time: str
    progress: int = Field(0)
    max_steps: int
    message: str = Field("")
    relations_steps: list[
        EntitiesRelations | Candidates | EnrichedEntitiesRelations
    ] = Field([])
    enriched_relations: EnrichedEntitiesRelations | None = None
