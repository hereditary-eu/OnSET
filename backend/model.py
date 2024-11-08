from __future__ import annotations
from dataclasses import dataclass, field
from pydantic import BaseModel, Field
from rdflib import Graph, URIRef, Literal
from typing import List, Optional


class Subject(BaseModel):
    subject_id: str
    label: str
    spos: dict[str, list[str]]
    subject_type: str = "class"
    refcount: int = 0
    descendants: dict[str, list[Subject]] = Field({})
    total_descendants: int = 0
    properties: dict[str, list[Subject]] = Field({})


Subject.update_forward_refs()
