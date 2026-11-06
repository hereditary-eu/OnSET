"""The ontology being built: classes with typed fields and links between classes.

Terms are named by their ``id`` (a local name) below the ontology's ``prefix``:
class ``Person`` is ``<prefix>Person``, its field ``age`` the datatype property
``<prefix>age`` and link ``worksFor`` the object property ``<prefix>worksFor``.
Instances extracted from a document are ``<prefix><Class>/<slug of name>``, so
mentions of the same name in different documents become the same instance.
Every instance is ``prov:wasDerivedFrom`` each document it was extracted from
(``document_iri``), which has its title as ``rdfs:label`` and its corpus id
(builder/corpus.py) as ``dcterms:identifier``.

- ``extraction_schema``: the JSON schema the extraction model is constrained to,
- ``extraction_triples``: its output as triples,
- ``ontology_graph`` / ``ontology_from_graph``: Turtle (OWL) export and import.
"""

import json
import re
from collections.abc import Callable
from typing import Any, Literal as TLiteral
from urllib.parse import quote

from pydantic import BaseModel, Field
from rdflib import DCTERMS, OWL, RDF, RDFS, SKOS, XSD, Graph, Literal, Namespace, URIRef

FieldType = TLiteral["string", "integer", "float", "date", "boolean", "vector"]

PROV = Namespace("http://www.w3.org/ns/prov#")
TENSOR = URIRef("https://w3id.org/rdf-tensor/datatypes#NumericDataTensor")

FIELD_RANGES: dict[str, URIRef] = {
    "string": XSD.string,
    "integer": XSD.integer,
    "float": XSD.double,
    "date": XSD.date,
    "boolean": XSD.boolean,
    "vector": TENSOR,
}
RANGE_FIELDS = {v: k for k, v in FIELD_RANGES.items()} | {
    XSD.int: "integer", XSD.long: "integer", XSD.decimal: "float",
    XSD.float: "float", XSD.dateTime: "date", XSD.gYear: "date",
}
FIELD_SCHEMAS: dict[str, dict] = {
    "string": {"type": "string"},
    "integer": {"type": "integer"},
    "float": {"type": "number"},
    "date": {"type": "string", "format": "date"},
    "boolean": {"type": "boolean"},
    "vector": {"type": "array", "items": {"type": "number"}, "maxItems": 64},
}
# instances of one class extracted from one document at most
MAX_INSTANCES = 16
# longer "names" are sentences the model copied, not entities
MAX_NAME = 80


class OntoField(BaseModel):
    name: str
    type: FieldType = "string"
    description: str = ""


class OntoClass(BaseModel):
    id: str
    label: str = ""
    description: str = ""
    fields: list[OntoField] = Field(default_factory=list)
    # layout in the editor
    x: float | None = None
    y: float | None = None


class OntoLink(BaseModel):
    id: str
    label: str = ""
    source: str
    target: str
    description: str = ""


class Ontology(BaseModel):
    prefix: str = "http://example.org/onto/"
    classes: list[OntoClass] = Field(default_factory=list)
    links: list[OntoLink] = Field(default_factory=list)

    def get_class(self, class_id: str) -> OntoClass | None:
        return next((c for c in self.classes if c.id == class_id), None)

    def term(self, local: str) -> URIRef:
        return URIRef(self.prefix + local)

    def instance(self, class_id: str, name: str) -> URIRef:
        return URIRef(f"{self.prefix}{class_id}/{slug(name)}")

    def schema_key(self) -> str:
        """Changes iff the extraction schema (not the layout or descriptions) changes."""
        return json.dumps(
            [self.prefix, [(c.id, [(f.name, f.type) for f in c.fields]) for c in self.classes],
             [(l.id, l.source, l.target) for l in self.links]]
        )


def local_name(text: str, upper: bool = False) -> str:
    """A valid local name from free text: ``"works for"`` -> ``worksFor`` / ``WorksFor``."""
    words = re.findall(r"[A-Za-z0-9]+", text)
    if not words:
        return "x"
    name = words[0] + "".join(w[:1].upper() + w[1:] for w in words[1:])
    name = (name[:1].upper() if upper else name[:1].lower()) + name[1:]
    return name if not name[0].isdigit() else "_" + name


def clean_name(name) -> str | None:
    """An extracted entity name, None if it is no name (markup the model leaked, sentences)."""
    name = str(name or "").strip().strip(".,;:").strip()
    if not 0 < len(name) <= MAX_NAME or re.search(r"[<>{}\[\]\"]", name):
        return None
    return name


def document_iri(prefix: str, doc_id: str) -> URIRef:
    """The IRI of a corpus document, ``<prefix>doc/<percent-encoded id>`` (ids are paths,
    ``file#key`` or record keys, so they may contain characters an IRI cannot)."""
    return URIRef(f"{prefix}doc/{quote(doc_id, safe='/')}")


def document_triples(prefix: str, doc_id: str, title: str) -> list[tuple]:
    """The triples describing a document the instances are derived from."""
    iri = document_iri(prefix, doc_id)
    return [(iri, RDFS.label, Literal(title)), (iri, DCTERMS.identifier, Literal(doc_id))]


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "x"


# --- extraction ---


def extraction_schema(onto: Ontology) -> dict:
    """JSON schema of the extraction output: per class a list of instances, each with
    its name, field values and the names of the instances its links point to."""
    properties = {}
    for cls in onto.classes:
        props: dict[str, Any] = {"name": {"type": "string"}}
        for field in cls.fields:
            props[field.name] = FIELD_SCHEMAS[field.type]
        for link in onto.links:
            if link.source == cls.id:
                props[link.id] = {"type": "array", "items": {"type": "string"}, "maxItems": MAX_INSTANCES}
        properties[cls.id] = {
            "type": "array",
            "maxItems": MAX_INSTANCES,
            "items": {"type": "object", "properties": props, "required": ["name"]},
        }
    return {"type": "object", "properties": properties, "required": list(properties)}


def _literal(value: Any, field_type: str) -> Literal | None:
    if value is None or value == "" or value == []:
        return None
    if field_type == "vector":
        return Literal(json.dumps(value), datatype=TENSOR)
    if field_type == "string":
        return Literal(str(value))
    return Literal(value, datatype=FIELD_RANGES[field_type])


def extraction_triples(
    onto: Ontology, data: dict, doc: URIRef | None = None,
    resolve: Callable[[str, str], tuple[URIRef, str]] | None = None,
) -> list[tuple]:
    """Triples of one document's extraction output (``extraction_schema`` shaped).

    ``resolve(class_id, name)``: the IRI and canonical label of the instance a name refers to
    (builder/disambiguate.py); a name other than the canonical label becomes its ``skos:altLabel``.
    Without it an instance is its IRI slug (``Ontology.instance``) labelled with every name."""
    triples: list[tuple] = []
    classes = {c.id: c for c in onto.classes}
    links = {l.id: l for l in onto.links}

    # the extraction prompt's own texts, names copied from them are no entities
    prompt_text = " ".join(
        [c.label + " " + c.description for c in onto.classes] + [l.label + " " + l.description for l in onto.links]
    ).lower()

    def name_of(value) -> str | None:
        name = clean_name(value)
        return name if name and name.lower() not in prompt_text else None

    def entity(class_id: str, name: str) -> URIRef:
        iri, label = resolve(class_id, name) if resolve is not None else (onto.instance(class_id, name), name)
        triples.append((iri, RDF.type, onto.term(class_id)))
        triples.append((iri, RDFS.label, Literal(label)))
        if label != name:
            triples.append((iri, SKOS.altLabel, Literal(name)))
        if doc is not None:
            triples.append((iri, PROV.wasDerivedFrom, doc))
        return iri

    for class_id, instances in (data or {}).items():
        cls = classes.get(class_id)
        if cls is None or not isinstance(instances, list):
            continue
        fields = {f.name: f for f in cls.fields}
        for item in instances:
            if not isinstance(item, dict) or not (name := name_of(item.get("name"))):
                continue
            iri = entity(class_id, name)
            for key, value in item.items():
                if key in fields and (lit := _literal(value, fields[key].type)) is not None:
                    triples.append((iri, onto.term(key), lit))
                elif key in links and links[key].source == class_id and isinstance(value, list):
                    for target in filter(None, map(name_of, value)):
                        triples.append((iri, onto.term(key), entity(links[key].target, target)))
    return triples


# --- Turtle ---


def ontology_graph(onto: Ontology) -> Graph:
    g = Graph()
    g.bind("onto", onto.prefix)
    g.bind("prov", PROV)
    g.add((URIRef(onto.prefix), RDF.type, OWL.Ontology))
    for cls in onto.classes:
        c = onto.term(cls.id)
        g.add((c, RDF.type, OWL.Class))
        g.add((c, RDFS.label, Literal(cls.label or cls.id)))
        if cls.description:
            g.add((c, RDFS.comment, Literal(cls.description)))
        for field in cls.fields:
            p = onto.term(field.name)
            g.add((p, RDF.type, OWL.DatatypeProperty))
            g.add((p, RDFS.label, Literal(field.name)))
            g.add((p, RDFS.domain, c))
            g.add((p, RDFS.range, FIELD_RANGES[field.type]))
            if field.description:
                g.add((p, RDFS.comment, Literal(field.description)))
    for link in onto.links:
        p = onto.term(link.id)
        g.add((p, RDF.type, OWL.ObjectProperty))
        g.add((p, RDFS.label, Literal(link.label or link.id)))
        g.add((p, RDFS.domain, onto.term(link.source)))
        g.add((p, RDFS.range, onto.term(link.target)))
        if link.description:
            g.add((p, RDFS.comment, Literal(link.description)))
    return g


def _split(iri: str) -> tuple[str, str]:
    """Namespace and local name of an IRI."""
    cut = max(iri.rfind("#"), iri.rfind("/")) + 1
    return iri[:cut], iri[cut:]


def ontology_from_graph(g: Graph, prefix: str | None = None) -> tuple[Ontology, Graph]:
    """The ontology (OWL/RDFS classes and properties) of ``g`` and its remaining
    (instance) triples. Terms outside the ontology's prefix keep their local name."""
    class_iris = sorted(
        {s for s in g.subjects(RDF.type, OWL.Class)} | {s for s in g.subjects(RDF.type, RDFS.Class)},
        key=str,
    )
    class_iris = [c for c in class_iris if isinstance(c, URIRef)]
    if prefix is None:
        declared = next(g.subjects(RDF.type, OWL.Ontology), None)
        prefix = str(declared) if declared else (_split(str(class_iris[0]))[0] if class_iris else Ontology().prefix)
    ids = {c: _split(str(c))[1] for c in class_iris}

    def text(s, p) -> str:
        return str(g.value(s, p) or "")

    classes = {
        c: OntoClass(id=ids[c], label=text(c, RDFS.label), description=text(c, RDFS.comment))
        for c in class_iris
    }
    schema_terms: set = set(class_iris) | {URIRef(prefix)}
    links = []
    for p in sorted(g.subjects(RDF.type, OWL.DatatypeProperty), key=str):
        schema_terms.add(p)
        field_type = RANGE_FIELDS.get(g.value(p, RDFS.range), "string")
        for domain in g.objects(p, RDFS.domain):
            if domain in classes:
                classes[domain].fields.append(
                    OntoField(name=_split(str(p))[1], type=field_type, description=text(p, RDFS.comment))
                )
    for p in sorted(g.subjects(RDF.type, OWL.ObjectProperty), key=str):
        schema_terms.add(p)
        domain, target = g.value(p, RDFS.domain), g.value(p, RDFS.range)
        if domain in classes and target in classes:
            links.append(
                OntoLink(id=_split(str(p))[1], label=text(p, RDFS.label), source=ids[domain],
                         target=ids[target], description=text(p, RDFS.comment))
            )
    instances = Graph()
    for triple in g:
        if triple[0] not in schema_terms:
            instances.add(triple)
    return Ontology(prefix=prefix, classes=list(classes.values()), links=links), instances


def rebase(g: Graph, old: str, new: str) -> Graph:
    """``g`` with every IRI starting with ``old`` moved below ``new``."""
    if old == new:
        return g

    def move(term):
        if isinstance(term, URIRef) and str(term).startswith(old):
            return URIRef(new + str(term)[len(old):])
        return term

    out = Graph()
    for prefix, ns in g.namespaces():
        out.bind(prefix, new if str(ns) == old else ns, replace=True)
    for s, p, o in g:
        out.add((move(s), move(p), move(o)))
    return out
