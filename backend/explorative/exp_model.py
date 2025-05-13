from __future__ import annotations
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column

from pydantic import Field, BaseModel

from model import Subject, SubjectLink
from pgvector.sqlalchemy import Vector
from enum import Enum
from ontology import OntologyManager


class BasePostgres(DeclarativeBase):
    pass


N_EMBEDDINGS = 1024
# N_EMBEDDINGS = 384


class SampledGraphDB(BasePostgres):
    __tablename__ = "sampled_graphs"
    graph_id: Mapped[int] = mapped_column(primary_key=True)
    graph_name: Mapped[str] = mapped_column()
    graph_query: Mapped[str] = mapped_column()
    onto_hash: Mapped[str | None] = mapped_column()
    instance_count: Mapped[int] = mapped_column(default=0)

    graph_links: Mapped[list[GraphLinkDB]] = relationship(
        "GraphLinkDB", back_populates="graph"
    )
    graph_entities: Mapped[list[GraphEntityDB]] = relationship(
        "GraphEntityDB", back_populates="graph"
    )


class GraphLinkDB(BasePostgres):
    __tablename__ = "graph_links"
    link_id: Mapped[int] = mapped_column(primary_key=True)
    subject_link_id: Mapped[int] = mapped_column(ForeignKey("subject_links.link_id"))
    graph_id: Mapped[int] = mapped_column(ForeignKey("sampled_graphs.graph_id"))

    from_entity_id: Mapped[int] = mapped_column(ForeignKey("graph_entity.entity_id"))
    to_entity_id: Mapped[int] = mapped_column(ForeignKey("graph_entity.entity_id"))

    from_entity: Mapped[GraphEntityDB] = relationship(
        "GraphEntityDB", back_populates="from_links", foreign_keys=[from_entity_id]
    )
    to_entity: Mapped[GraphEntityDB] = relationship(
        "GraphEntityDB", back_populates="to_links", foreign_keys=[to_entity_id]
    )

    graph: Mapped[SampledGraphDB] = relationship(
        "SampledGraphDB", back_populates="graph_links"
    )
    subject_link: Mapped[SubjectLinkDB] = relationship(
        "SubjectLinkDB", back_populates="graph_links"
    )


class GraphEntityDB(BasePostgres):
    __tablename__ = "graph_entity"
    entity_id: Mapped[int] = mapped_column(primary_key=True)
    graph_id: Mapped[int] = mapped_column(ForeignKey("sampled_graphs.graph_id"))
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.subject_id"))

    subject: Mapped[SubjectInDB] = relationship("SubjectInDB")

    graph: Mapped[SampledGraphDB] = relationship(
        "SampledGraphDB", back_populates="graph_entities"
    )
    from_links: Mapped[list[GraphLinkDB]] = relationship(
        "GraphLinkDB",
        back_populates="from_entity",
        primaryjoin=entity_id == GraphLinkDB.from_entity_id,
    )
    to_links: Mapped[list[GraphLinkDB]] = relationship(
        "GraphLinkDB",
        back_populates="to_entity",
        primaryjoin=entity_id == GraphLinkDB.to_entity_id,
    )


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
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("subjects.subject_id", deferrable=True)
    )
    label: Mapped[str | None] = mapped_column()
    comment: Mapped[str | None] = mapped_column()
    subject_type: Mapped[str] = mapped_column()
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.topic_id", deferrable=True)
    )
    instance_count: Mapped[int] = mapped_column(default=0)

    embedding: Mapped[Vector] = mapped_column(Vector(N_EMBEDDINGS))
    onto_hash: Mapped[str | None] = mapped_column()

    sub_classes: Mapped[list[SubjectInDB]] = relationship(
        "SubjectInDB",
        back_populates="parent",
        remote_side=[parent_id],
    )
    parent: Mapped[SubjectInDB] = relationship(
        "SubjectInDB",
        back_populates="sub_classes",
        remote_side=[subject_id],
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
    graph_entities: Mapped[list[GraphEntityDB]] = relationship(
        "GraphEntityDB", back_populates="subject"
    )

    def from_db(self, oman: OntologyManager):
        return oman.enrich_subject(self.subject_id)


class SubjectLinkDB(BasePostgres):
    __tablename__ = "subject_links"
    link_id: Mapped[int] = mapped_column(primary_key=True)
    # do not enforce foreign key constraints

    from_id: Mapped[str | None] = mapped_column(ForeignKey("subjects.subject_id"))
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

    description: Mapped[str | None] = mapped_column()
    embedding: Mapped[Vector | None] = mapped_column(Vector(N_EMBEDDINGS))

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

    graph_links: Mapped[list[GraphLinkDB]] = relationship(
        "GraphLinkDB", back_populates="subject_link"
    )

    def from_db(self, oman: OntologyManager):
        return SubjectLink(
            label=self.label,
            link_id=self.link_id,
            from_id=self.from_id,
            link_type=self.link_type,
            to_id=self.to_id,
            to_proptype=self.to_proptype,
            property_id=self.property_id,
            from_subject=oman.enrich_subject(self.from_id),
            to_subject=(
                oman.enrich_subject(self.to_id) if self.to_id is not None else None
            ),
            instance_count=self.instance_count,
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
    include_thing: bool = Field(True)


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
