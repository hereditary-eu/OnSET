from __future__ import annotations
from dataclasses import dataclass, field
from pydantic import BaseModel, Field
from typing import List, Optional, Any

from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session



class Base(DeclarativeBase):
    pass


class InstanceQuery(BaseModel):
    cls: str
    q: str | None = None
    limit: int = 10
    skip: int = 0


class Instance(BaseModel):
    id: str = ""
    label: str = ""


class PropertyValue(BaseModel):
    value: Any | None
    label: str | None


class Property(BaseModel):
    property: str | None = ""
    label: str | None = ""
    values: list[PropertyValue] = Field([])

    def first_value(self):
        if len(self.values) > 0:
            return self.values[0].value
        return ""


class Subject(BaseModel):
    subject_id: str
    label: str
    spos: dict[str, Property] = Field({})
    subject_type: str = "class"
    refcount: int = 0
    descendants: dict[str, list[Subject]] = Field({})
    total_descendants: int = 0
    properties: dict[str, list[Subject]] = Field({})
    instance_count: int = 0

    def is_of_type(self, subject_id: str):
        if self.subject_id == subject_id:
            return True
        subclasses = self.spos.get("rdfs:subClassOf")
        if subclasses:
            for subclass in subclasses.values:
                if subclass.value == subject_id:
                    return True
        return self.subject_id == subject_id



class MatchDB(Base):
    __tablename__ = "match"
    id: Mapped[int] = mapped_column(primary_key=True)
    colname: Mapped[str] = mapped_column()
    idx: Mapped[str] = mapped_column()
    score: Mapped[float] = mapped_column()
    rank: Mapped[int] = mapped_column()

    relationfound_id: Mapped[int] = mapped_column(ForeignKey("relationfound.id"))
    relationfound: Mapped[List["RelationsFoundDB"]] = relationship(
        back_populates="matches"
    )


class PathElementDB(Base):
    __tablename__ = "pathelement"
    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column()

    relationfound_id: Mapped[int] = mapped_column(ForeignKey("relationfound.id"))
    relationfound: Mapped[List["RelationsFoundDB"]] = relationship(
        back_populates="path"
    )


class RelationsFoundDB(Base):
    __tablename__ = "relationfound"
    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[List[PathElementDB]] = relationship(back_populates="relationfound")
    subject_id: Mapped[str] = mapped_column()
    text: Mapped[str] = mapped_column()
    matches: Mapped[List[MatchDB]] = relationship(back_populates="relationfound")

    # best_match_id: Mapped[int] = mapped_column(ForeignKey("match.id"))
    # best_match: Mapped[Match] = relationship(back_populates="relationfound")


@dataclass
class Match:
    colname: str = ""
    idx: str = ""
    score: float = -1
    rank: int = -1

    @staticmethod
    def from_db(match: MatchDB):
        return Match(
            colname=match.colname,
            idx=match.idx,
            score=match.score,
            rank=match.rank,
        )


@dataclass
class RelationsFound:
    id: int = 0
    path: list[str] = field(default_factory=list)
    subject_id: str = ""
    text: str = ""
    matches: list[Match] = field(default_factory=list)

    @staticmethod
    def from_db(rel: RelationsFoundDB):
        id = rel.id
        path = [p.path for p in rel.path]
        subject_id = rel.subject_id
        text = rel.text
        matches = [Match.from_db(m) for m in rel.matches]
        return RelationsFound(
            id=id, path=path, subject_id=subject_id, text=text, matches=matches
        )


@dataclass
class OutLink:
    target: RelationsFound = field(default_factory=lambda: RelationsFound())
    count: int = 0
    instances: list[str] = field(default_factory=list)


@dataclass
class SparseOutLinks:
    source: RelationsFound = field(default_factory=lambda: RelationsFound())
    targets: list[OutLink] = field(default_factory=list)


# Subject.update_forward_refs()
Subject.model_rebuild()
