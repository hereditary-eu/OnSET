from __future__ import annotations
from model import *
from ontology import *
from pgvector.sqlalchemy import Vector
from enum import Enum


class BasePostgres(DeclarativeBase):
    pass


N_EMBEDDINGS = 1024
# N_EMBEDDINGS = 384


class TopicDB(BasePostgres):
    __tablename__ = "topics"
    topic_id: Mapped[int] = mapped_column(primary_key=True)
    parent_topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.topic_id", deferrable=True)
    )

    parent_topic: Mapped[TopicDB] = relationship(
        "TopicDB", remote_side=[topic_id], back_populates="sub_topics"
    )
    sub_topics: Mapped[list[TopicDB]] = relationship(
        "TopicDB", remote_side=[parent_topic_id], back_populates="parent_topic"
    )
    topic: Mapped[str] = mapped_column()
    count: Mapped[int] = mapped_column(default=0)
    embedding: Mapped[Vector | None] = mapped_column(Vector(N_EMBEDDINGS))
    doc_string: Mapped[str | None] = mapped_column()

    onto_hash: Mapped[str | None] = mapped_column()

    links: Mapped[list[SubjectLinkDB]] = relationship(
        "SubjectLinkDB", back_populates="topic"
    )
    subjects: Mapped[list[SubjectInDB]] = relationship(
        "SubjectInDB", back_populates="topic"
    )


class Topic(BaseModel):
    topic_id: int
    sub_topics: list[Topic]
    parent_topic_id: int | None
    topic: str
    count: int
    subjects_ids: list[str]
    property_ids: list[str]
    # embedding: list[float]


class SubjectInDB(BasePostgres):
    __tablename__ = "subjects"
    subject_id: Mapped[str] = mapped_column(primary_key=True)
    parent_id: Mapped[str | None] = mapped_column()
    label: Mapped[str | None] = mapped_column()
    comment: Mapped[str | None] = mapped_column()
    subject_type: Mapped[str] = mapped_column()
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.topic_id", deferrable=True)
    )
    instance_count: Mapped[int] = mapped_column(default=0)

    embedding: Mapped[Vector] = mapped_column(Vector(N_EMBEDDINGS))
    onto_hash: Mapped[str | None] = mapped_column()

    parent: Mapped[SubjectInDB] = relationship(
        "SubjectInDB",
        remote_side=[subject_id],
        back_populates="sub_classes",
        primaryjoin=parent_id == subject_id,
        foreign_keys=[parent_id],
    )
    sub_classes: Mapped[list[SubjectInDB]] = relationship(
        "SubjectInDB",
        back_populates="parent",
        primaryjoin=subject_id == parent_id,
        foreign_keys=[subject_id],
    )

    from_links: Mapped[list[SubjectLinkDB]] = relationship(
        "SubjectLinkDB",
        back_populates="from_subject",
        primaryjoin="SubjectInDB.subject_id == SubjectLinkDB.from_id",
    )
    to_links: Mapped[list[SubjectLinkDB]] = relationship(
        "SubjectLinkDB",
        back_populates="to_subject",
        primaryjoin="SubjectInDB.subject_id == SubjectLinkDB.to_id",
    )

    topic: Mapped[TopicDB] = relationship("TopicDB", back_populates="subjects")


class SubjectLinkDB(BasePostgres):
    __tablename__ = "subject_links"
    link_id: Mapped[int] = mapped_column(primary_key=True)
    # do not enforce foreign key constraints

    from_id: Mapped[str] = mapped_column(ForeignKey("subjects.subject_id"))
    link_type: Mapped[str] = mapped_column()
    # none means no specific target
    to_id: Mapped[str | None] = mapped_column(ForeignKey("subjects.subject_id"))
    to_proptype: Mapped[str | None] = mapped_column()
    property_id: Mapped[str | None] = mapped_column()
    label: Mapped[str | None] = mapped_column()
    instance_count: Mapped[int] = mapped_column(default=0)

    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.topic_id", deferrable=True)
    )

    embedding: Mapped[Vector] = mapped_column(Vector(N_EMBEDDINGS))

    onto_hash: Mapped[str | None] = mapped_column()

    topic: Mapped[TopicDB] = relationship("TopicDB", back_populates="links")

    from_subject: Mapped[SubjectInDB] = relationship(
        "SubjectInDB",
        back_populates="from_links",
        primaryjoin=from_id == SubjectInDB.subject_id,
    )
    to_subject: Mapped[SubjectInDB] = relationship(
        "SubjectInDB",
        back_populates="to_links",
        primaryjoin=to_id == SubjectInDB.subject_id,
    )


class SubjectLink(BaseModel):
    link_id: int
    label: str | None

    from_id: str
    link_type: str
    to_id: str | None
    to_proptype: str | None

    property_id: str | None

    from_subject: Subject | None
    to_subject: Subject | None

    instance_count: int = 0

    @classmethod
    def from_db(self, link: SubjectLinkDB, oman: OntologyManager):
        return SubjectLink(
            label=link.label,
            link_id=link.link_id,
            from_id=link.from_id,
            link_type=link.link_type,
            to_id=link.to_id,
            to_proptype=link.to_proptype,
            property_id=link.property_id,
            from_subject=oman.enrich_subject(link.from_id),
            to_subject=(
                oman.enrich_subject(link.to_id) if link.to_id is not None else None
            ),
            instance_count=link.instance_count,
        )


class RETURN_TYPE(str, Enum):
    SUBJECT = "subject"
    LINK = "link"
    BOTH = "both"


class RELATION_TYPE(str, Enum):
    PROPERTY = "property"
    INSTANCE = "instance"


class FUZZY_QUERY_ORDER(str, Enum):
    SCORE = "score"
    INSTANCES = "instances"


class FuzzyQuery(BaseModel):
    q: str | None = Field(None)
    topic_ids: list[int] | None = Field(None)
    mix_topic_factor: float | None = Field(0.5)
    from_id: str | list[str] | None = Field(None)

    to_id: str | None = Field(None)

    limit: int | None = Field(25)
    skip: int | None = Field(0)

    type: RETURN_TYPE = RETURN_TYPE.BOTH
    relation_type: RELATION_TYPE | None = RELATION_TYPE.INSTANCE

    order: FUZZY_QUERY_ORDER = Field(FUZZY_QUERY_ORDER.SCORE)


class ResultAttributionType(Enum):
    TOPIC = "topic"
    QUERY = "query"


class ResultAttribution(BaseModel):
    topic_id: int | None = Field(None)
    type: ResultAttributionType = Field(ResultAttributionType.TOPIC)
    score: float = Field(0.0)


class FuzzyQueryResult(BaseModel):
    link: SubjectLink | None = Field(None)
    subject: Subject | None = Field(None)
    score: float = Field(0.0)
    attributions: list[ResultAttribution] = Field([])


class FuzzyQueryResults(BaseModel):
    results: list[FuzzyQueryResult]


class SparqlQuery(BaseModel):
    query: str = Field()
    limit: int | None = Field(25)
    skip: int | None = Field(0)
