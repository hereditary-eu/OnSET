from pydantic import BaseModel, Field
import enum
from typing import Literal
from abc import ABC


class AssistantLink(BaseModel):
    type: Literal["link"] = "link"
    from_id: str
    to_id: str
    from_internal_id: str
    to_internal_id: str

    link_id: str


class AssistantSubQueryType(str, enum.Enum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    SUBJECT = "subject"
    QUERY_PROP = "query_prop"


class AssistantSubQuery(BaseModel, ABC):
    type: Literal["subquery"] = "subquery"
    constraint_type: AssistantSubQueryType
    field: str
    field: str
    from_internal_id: str
    from_id: str


class StringConstraintType(str, enum.Enum):
    EQUALS = "equals"
    CONTAINS = "contains"
    STARTSWITH = "startswith"
    ENDSWITH = "endswith"
    REGEX = "regex"


class StringSubQuery(AssistantSubQuery):
    constraint_type: Literal[AssistantSubQueryType.STRING]
    value: str
    op_type: StringConstraintType


class NumberConstraintType(str, enum.Enum):
    EQUALS = "equals"
    GREATERTHAN = "greaterthan"
    LESSTHAN = "lessthan"


class NumberSubQuery(AssistantSubQuery):
    constraint_type: Literal[AssistantSubQueryType.NUMBER]
    value: float
    op_type: NumberConstraintType


class BooleanSubQuery(AssistantSubQuery):
    constraint_type: Literal[AssistantSubQueryType.BOOLEAN]
    value: bool


class DateSubQuery(AssistantSubQuery):
    constraint_type: Literal[AssistantSubQueryType.DATE]
    value: str
    op_type: NumberConstraintType


class AssistantSubject(BaseModel):
    type: Literal["subject"] = "subject"
    subject_id: str
    internal_id: str
    subqueries: list[AssistantSubQuery] = Field([])
    x: float = 0.0
    y: float = 0.0


class QueryGraph(BaseModel):
    subjects: list[AssistantSubject] = Field([])
    links: list[AssistantLink] = Field([])


class OperationType(str, enum.Enum):
    ADD = "add"
    REMOVE = "remove"


class Operation(BaseModel):
    operation: OperationType
    data: AssistantLink | AssistantSubject | AssistantSubQuery


class Operations(BaseModel):
    operations: list[Operation] = Field([])
