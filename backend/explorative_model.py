from __future__ import annotations
from model import *
from ontology import *
from pgvector.sqlalchemy import Vector


class BasePostgres(DeclarativeBase):
    pass


N_EMBEDDINGS = 384


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
    embedding: Mapped[Vector] = mapped_column(Vector(N_EMBEDDINGS))

    onto_hash: Mapped[str | None] = mapped_column()


class Topic(BaseModel):
    topic_id: int
    sub_topics: list[Topic]
    topic: str
    count: int
    # embedding: list[float]


class SubjectLinkDB(BasePostgres):
    __tablename__ = "subject_links"
    link_id: Mapped[int] = mapped_column(primary_key=True)

    from_id: Mapped[str] = mapped_column()
    link_type: Mapped[str] = mapped_column()
    to_id: Mapped[str] = mapped_column()

    embedding: Mapped[Vector] = mapped_column(Vector(N_EMBEDDINGS))


class SubjectInDB(BasePostgres):
    __tablename__ = "subjects"
    subject_id: Mapped[str] = mapped_column(primary_key=True)
    parent_id: Mapped[str | None] = mapped_column()
    label: Mapped[str | None] = mapped_column()
    comment: Mapped[str | None] = mapped_column()
    subject_type: Mapped[str] = mapped_column()

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
