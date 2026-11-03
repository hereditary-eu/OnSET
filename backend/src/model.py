"""Ontology descriptors (classes, properties, instances) shared by the API.

Query graphs built from these live in assistant/assistant_model.py.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any


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

    def to_link(self):
        return SubjectLink(
            link_id=-1,
            label=self.label,
            property_id=self.subject_id,
            from_id=self.spos["rdfs:domain"].first_value()
            if self.spos.get("rdfs:domain")
            else "owl:Thing",
            to_id=self.spos["rdfs:range"].first_value()
            if self.spos.get("rdfs:range")
            else None,
            link_type="class",
            to_proptype=None,
            from_subject=None,
            to_subject=None,
            instance_count=self.instance_count,
        )


# Subject.update_forward_refs()
Subject.model_rebuild()


class SubjectLink(BaseModel):
    link_id: int
    label: str | None

    from_id: str | None
    link_type: str
    to_id: str | None
    to_proptype: str | None

    property_id: str | None

    from_subject: Subject | None
    to_subject: Subject | None

    instance_count: int = 0


class GeneralizationQuery(BaseModel):
    cls: str = Field("")
    out_link_ids: list[str] = Field([])
    in_link_ids: list[str] = Field([])


class LinkedSubject(Subject):
    """A subject with the links that attach to it (see OntologyManager.get_most_generic_classes)."""

    out_links: list[SubjectLink] = Field([])
    in_links: list[SubjectLink] = Field([])
