from __future__ import annotations
from dataclasses import dataclass, field
from pydantic import BaseModel, Field
from rdflib import Graph, URIRef, Literal
from typing import List, Optional, Any

from sqlalchemy import ForeignKey, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session


class Base(DeclarativeBase):
    pass


class Subject(BaseModel):
    subject_id: str
    label: str
    spos: dict[str, list[str | Any]]
    subject_type: str = "class"
    refcount: int = 0
    descendants: dict[str, list[Subject]] = Field({})
    total_descendants: int = 0
    properties: dict[str, list[Subject]] = Field({})


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


Subject.model_rebuild()
