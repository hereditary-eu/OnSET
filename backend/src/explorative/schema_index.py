"""In-memory index of the ontology schema stored by the initialisation (topic_init).

The ``subjects`` (classes and named individuals, with their first parent class,
label and instance count) and ``subject_links`` (one row per property: the
class it was stored for, its range class ``to_id`` or literal/other range
``to_proptype``, label and usage count) of one ontology (``onto_hash``) are
small (DBpedia: ~1k classes, ~3k properties), so they are read once, without
the embeddings, and answer the schema lookups of the progressive sampler with
dictionary lookups instead of one SPARQL query each:

- ``links_of(cls)``: the links (property, range) stored for the class or
  one of its ancestors (by ``parent_id``); links of owl:Thing (properties
  without a domain) only for owl:Thing itself, as search_fuzzy without
  ``include_thing``.
- ``label(uri)``, ``root_classes()``, ``subject(uri)``, ``link(uri)``.

What the stored schema does not capture, compared to OntologyManager's queries:
a property is stored for a single domain class (the last of a union domain)
with a single range, properties without a range are not stored, and a class
has a single parent. Ids are compared as full IRIs (``<...>`` and prefixed
names alike), see ``key``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from model import Property, PropertyValue, Subject, SubjectLink

OWL_THING = "http://www.w3.org/2002/07/owl#Thing"
PREFIXED = re.compile(r"^([A-Za-z_][A-Za-z0-9_.-]*):(.*)$")


@dataclass(frozen=True)
class SchemaClass:
    """A row of ``subjects``: a class or named individual."""

    subject_id: str
    label: str | None = None
    parent_id: str | None = None
    subject_type: str = "class"
    instance_count: int = 0
    comment: str | None = None


@dataclass(frozen=True)
class SchemaLink:
    """A row of ``subject_links``: a property with its domain class and range."""

    property_id: str
    from_id: str | None = None
    to_id: str | None = None
    to_proptype: str | None = None
    label: str | None = None
    link_type: str = ""
    instance_count: int = 0
    link_id: int = -1

    @property
    def range(self) -> str | None:
        return self.to_id if self.to_id is not None else self.to_proptype


class SchemaIndex:
    def __init__(
        self,
        classes: Iterable[SchemaClass],
        links: Iterable[SchemaLink],
        namespaces: dict[str, str] | None = None,
    ):
        self.namespaces = dict(namespaces or {})
        self.classes: dict[str, SchemaClass] = {}
        for cls in classes:
            # the first row of an id wins (individuals are stored once per class)
            self.classes.setdefault(self.key(cls.subject_id), cls)
        self.links: dict[str, SchemaLink] = {}
        self._by_domain: dict[str, list[SchemaLink]] = {}
        for link in links:
            if not link.property_id:
                continue
            key = self.key(link.property_id)
            if key in self.links:
                continue
            self.links[key] = link
            domain = self.key(link.from_id) if link.from_id else OWL_THING
            self._by_domain.setdefault(domain, []).append(link)
        for domain_links in self._by_domain.values():
            # deterministic order (the database's is not)
            domain_links.sort(key=lambda l: self.key(l.property_id))

    def __len__(self) -> int:
        return len(self.classes) + len(self.links)

    def key(self, uri: str) -> str:
        """Full IRI (without <>) of an IRI, wrapped IRI or prefixed name."""
        uri = uri.strip()
        if uri.startswith("<") and uri.endswith(">"):
            return uri[1:-1]
        match = PREFIXED.match(uri)
        if match and "://" not in uri and match.group(1) in self.namespaces:
            return self.namespaces[match.group(1)] + match.group(2)
        return uri

    def iri(self, uri: str) -> str:
        """Wrapped full IRI, the form of OntologyManager.outgoing_properties."""
        return f"<{self.key(uri)}>"

    # --- classes ---

    def has_class(self, uri: str) -> bool:
        cls = self.classes.get(self.key(uri))
        return cls is not None and cls.subject_type == "class"

    def ancestors(self, uri: str, include_thing: bool = False) -> list[str]:
        """Keys of the class and its parents, nearest first; owl:Thing only if
        ``include_thing`` or it is the class itself."""
        result: list[str] = []
        key: str | None = self.key(uri)
        while key is not None and key not in result:
            result.append(key)
            cls = self.classes.get(key)
            key = self.key(cls.parent_id) if cls is not None and cls.parent_id else None
        if not include_thing and len(result) > 1:
            result = [k for k in result if k != OWL_THING]
        return result

    def root_classes(self) -> list[str]:
        """Wrapped IRIs of the classes without a parent (or below owl:Thing), sorted."""
        roots = [
            key
            for key, cls in self.classes.items()
            if cls.subject_type == "class"
            and key != OWL_THING
            and (not cls.parent_id or self.key(cls.parent_id) == OWL_THING)
        ]
        return [f"<{key}>" for key in sorted(roots)]

    # --- properties ---

    def links_of(self, cls: str, include_thing: bool = False) -> list[SchemaLink]:
        """The stored links of ``cls`` and its ancestors, nearest class first, each
        property in the order of its IRI. A range class is in ``to_id``, a literal
        (or other non-class) range in ``to_proptype``."""
        return [link for key in self.ancestors(cls, include_thing) for link in self._by_domain.get(key, [])]

    # --- labels and details ---

    def label(self, uri: str) -> str | None:
        key = self.key(uri)
        cls = self.classes.get(key)
        if cls is not None and cls.label:
            return cls.label
        link = self.links.get(key)
        if link is not None and link.label:
            return link.label
        return None

    def subject(self, uri: str) -> Subject | None:
        """The stored class as the Subject the editor needs (no SPARQL), None if unknown."""
        cls = self.classes.get(self.key(uri))
        if cls is None:
            return None
        label = cls.label or cls.subject_id
        spos = {"rdfs:label": Property(property="rdfs:label", label=None, values=[PropertyValue(value=label, label=None)])}
        if cls.parent_id:
            spos["rdfs:subClassOf"] = Property(
                property="rdfs:subClassOf", label=None, values=[PropertyValue(value=cls.parent_id, label=None)]
            )
        if cls.comment:
            spos["rdfs:comment"] = Property(
                property="rdfs:comment", label=None, values=[PropertyValue(value=cls.comment, label=None)]
            )
        return Subject(
            subject_id=cls.subject_id,
            label=label,
            spos=spos,
            subject_type=cls.subject_type,
            instance_count=cls.instance_count or 0,
        )

    def link(self, uri: str) -> SubjectLink | None:
        """The stored property as a SubjectLink (as the link search returns it, without
        the enriched end subjects), None if unknown."""
        link = self.links.get(self.key(uri))
        if link is None:
            return None
        return SubjectLink(
            link_id=link.link_id,
            label=link.label,
            from_id=link.from_id,
            link_type=link.link_type,
            to_id=link.to_id,
            to_proptype=link.to_proptype,
            property_id=link.property_id,
            from_subject=None,
            to_subject=None,
            instance_count=link.instance_count or 0,
        )
