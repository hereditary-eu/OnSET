from pydantic import BaseModel, Field
import enum
from typing import Annotated, Literal, TYPE_CHECKING

from model import Subject, SubjectLink

if TYPE_CHECKING:
    from api.config import ManMan


# Subject/Link/SubQuery for agentic graph editing.
# The subqueries mirror frontend/src/utils/sparql/representation/subqueries.ts


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

    def get_full(self, manman: "ManMan"):
        return manman.ontology_manager.enrich_subject(self.uri, load_properties=True)


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
        link: SubjectLink,
        from_subject_id: str,
        to_subject_id: str,
        id: str | None = None,
    ) -> "AssistantLink":
        """from_subject/to_subject are the internal ids of the linked AssistantSubjects."""
        return AssistantLink(
            uri=link.property_id,
            label=link.label or link.property_id,
            id=id,
            from_subject_id=from_subject_id,
            to_subject_id=to_subject_id,
            from_subject_label=link.from_subject.label,
            from_subject_uri=link.from_subject.subject_id,
            to_subject_label=link.to_subject.label,
            to_subject_uri=link.to_subject.subject_id,
        )

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
            subject.id = self.next_subject_id()
        self.subjects.append(subject)

    def add_link(self, link: AssistantLink):
        if link.id is None or link.id == "":
            link.id = self.next_link_id()
        self.links.append(link)

    def remove_subject(self, subject_id: str):
        self.subjects = [s for s in self.subjects if s.id != subject_id]
        self.links = [
            l
            for l in self.links
            if l.from_subject != subject_id and l.to_subject != subject_id
        ]

    def remove_link(self, link_id: str):
        self.links = [l for l in self.links if l.id != link_id]

    def has_subject(self, subject_id: str) -> bool:
        return any(s.id == subject_id for s in self.subjects)


class OperationType(str, enum.Enum):
    ADD = "add"
    REMOVE = "remove"


class Operation(BaseModel):
    operation: OperationType
    data: AssistantLink | AssistantSubject | AnyAssistantSubQuery


class Operations(BaseModel):
    operations: list[Operation] = Field([])
