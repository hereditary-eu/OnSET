"""The ontology being built: classes with typed fields and links between classes.

Terms are named by their ``id`` (a local name) below the ontology's ``prefix``:
class ``Person`` is ``<prefix>Person``, its field ``age`` the datatype property
``<prefix>age`` and link ``worksFor`` the object property ``<prefix>worksFor``.
Instances extracted from a document are ``<prefix><Class>/<slug of name>``, so
mentions of the same name in different documents become the same instance.
Every instance is ``prov:wasDerivedFrom`` each document it was extracted from
(``document_iri``), a ``foaf:Document`` with its title as ``rdfs:label`` and its corpus
id (builder/corpus.py) as ``dcterms:identifier``. ``provenance_graph`` labels these terms,
so the query editor can show the documents as a class of their own.

Classes may have superclasses (``parents``, exported as ``rdfs:subClassOf``); an instance
is typed with its own class only, queries reach subclasses with ``rdfs:subClassOf*``.
An ``enum`` field takes one of its ``values`` (a closed vocabulary), exported as an
``xsd:string`` datatype property with each value as ``skos:example``. The ontology's
``examples`` (texts with their expected extraction output) are shown to the extraction model.
``annotation_map`` ties classes to paths into the builder's annotated examples (``annotation_values``):
their values give retrieved few-shot examples (``retrieved_examples``) and, for
``vocabulary_classes``, a vocabulary of known names matched in every text (``Vocabulary``).

- ``extraction_schema``: the JSON schema the extraction model is constrained to,
- ``extraction_triples``: its output as triples,
- ``ontology_graph`` / ``ontology_from_graph``: Turtle (OWL) export and import.
"""

import json
import re
import unicodedata
from collections.abc import Callable, Iterable
from functools import lru_cache
from typing import Any, Literal as TLiteral
from urllib.parse import quote

import inflection
from pydantic import BaseModel, Field
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
from rdflib import DCTERMS, FOAF, OWL, RDF, RDFS, SKOS, XSD, Graph, Literal, Namespace, URIRef

FieldType = TLiteral["string", "integer", "float", "date", "boolean", "vector", "enum"]

PROV = Namespace("http://www.w3.org/ns/prov#")
TENSOR = URIRef("https://w3id.org/rdf-tensor/datatypes#NumericDataTensor")

FIELD_RANGES: dict[str, URIRef] = {
    "string": XSD.string,
    "integer": XSD.integer,
    "float": XSD.double,
    "date": XSD.date,
    "boolean": XSD.boolean,
    "vector": TENSOR,
    "enum": XSD.string,
}
RANGE_FIELDS = {v: k for k, v in FIELD_RANGES.items() if k != "enum"} | {
    XSD.int: "integer", XSD.long: "integer", XSD.decimal: "float",
    XSD.float: "float", XSD.dateTime: "date", XSD.gYear: "date",
}
FIELD_SCHEMAS: dict[str, dict] = {
    "enum": {"type": "string"},
    "string": {"type": "string"},
    "integer": {"type": "integer"},
    "float": {"type": "number"},
    "date": {"type": "string", "format": "date"},
    "boolean": {"type": "boolean"},
    "vector": {"type": "array", "items": {"type": "number"}, "maxItems": 64},
}
# values of an enum field at most
MAX_VALUES = 256
# instances of one class extracted from one document at most
MAX_INSTANCES = 16
# longer "names" are sentences the model copied, not entities
MAX_NAME = 80


class OntoField(BaseModel):
    name: str
    type: FieldType = "string"
    description: str = ""
    # the values an ``enum`` field takes
    values: list[str] = Field(default_factory=list, max_length=MAX_VALUES)


class OntoClass(BaseModel):
    id: str
    label: str = ""
    description: str = ""
    fields: list[OntoField] = Field(default_factory=list)
    # ids of its superclasses
    parents: list[str] = Field(default_factory=list)
    # layout in the editor
    x: float | None = None
    y: float | None = None


class OntoLink(BaseModel):
    id: str
    label: str = ""
    source: str
    target: str
    description: str = ""


class ExtractionExample(BaseModel):
    """A text and the extraction output (``extraction_schema`` shaped) expected for it."""
    text: str
    output: dict


class Ontology(BaseModel):
    prefix: str = "http://example.org/onto/"
    classes: list[OntoClass] = Field(default_factory=list)
    links: list[OntoLink] = Field(default_factory=list)
    # few-shot examples of the extraction model
    examples: list[ExtractionExample] = Field(default_factory=list)
    # extract documents in pieces of whole sentences of at most this many characters (None:
    # the builder's ``extract_chunk_chars``), set by the agent after checking the extraction
    chunk_chars: int | None = Field(None, ge=100)
    # class id -> path into an annotation of the builder's annotated examples (annotation_values)
    annotation_map: dict[str, str] = Field(default_factory=dict)
    # few-shot examples retrieved per extraction call: the most similar annotated example
    # sentences, their output from annotation_map (0: none)
    retrieved_examples: int = Field(0, ge=0, le=5)
    # mapped classes whose annotation values found in a text are added as instances
    vocabulary_classes: list[str] = Field(default_factory=list)

    def get_class(self, class_id: str) -> OntoClass | None:
        return next((c for c in self.classes if c.id == class_id), None)

    def ancestors(self, class_id: str) -> set[str]:
        """Ids of the (transitive) superclasses of a class."""
        out: set[str] = set()
        todo = [class_id]
        while todo:
            cls = self.get_class(todo.pop())
            for parent in cls.parents if cls else []:
                if parent not in out:
                    out.add(parent)
                    todo.append(parent)
        return out

    def remove_class(self, class_id: str):
        """Remove a class with the links from or to it and its use as a superclass."""
        self.classes = [c for c in self.classes if c.id != class_id]
        self.links = [l for l in self.links if class_id not in (l.source, l.target)]
        for cls in self.classes:
            cls.parents = [p for p in cls.parents if p != class_id]
        self.annotation_map.pop(class_id, None)
        self.vocabulary_classes = [c for c in self.vocabulary_classes if c != class_id]
        if not self.annotation_map:
            self.retrieved_examples = 0

    def mapped_classes(self) -> dict[str, str]:
        """``annotation_map`` of the classes that exist."""
        return {c: p for c, p in self.annotation_map.items() if p and self.get_class(c) is not None}

    def term(self, local: str) -> URIRef:
        return URIRef(self.prefix + local)

    def instance(self, class_id: str, name: str) -> URIRef:
        return URIRef(f"{self.prefix}{class_id}/{slug(name)}")

    def schema_key(self) -> str:
        """Changes iff the extraction schema (not the layout or descriptions) changes."""
        return json.dumps(
            [self.prefix, [(c.id, [(f.name, f.type, f.values) for f in c.fields]) for c in self.classes],
             [(l.id, l.source, l.target) for l in self.links],
             [(e.text, e.output) for e in self.examples], self.chunk_chars,
             self.annotation_map, self.retrieved_examples, sorted(self.vocabulary_classes)],
            sort_keys=True,
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


def normalize(name: str) -> str:
    """``"Enron  Corp."`` -> ``"enron corp"`` (case folding, punctuation and whitespace)."""
    text = unicodedata.normalize("NFKC", name).casefold()
    text = re.sub(r"[\W_]+", " ", text)
    return " ".join(text.split())


@lru_cache(maxsize=1 << 16)
def _singular(word: str) -> str:
    return inflection.singularize(word) if len(word) > 3 else word


def _singular_words(text: str) -> str:
    return " ".join(map(_singular, normalize(text).split()))


def grounded(name: str, text: str) -> bool:
    """``name`` occurs in ``text``: normalised, at word boundaries, words compared in their
    singular form (``"drumlin field"`` is in ``"Drumlin fields are ..."``)."""
    key = _singular_words(name)
    return bool(key) and f" {key} " in f" {_singular_words(text)} "


def document_iri(prefix: str, doc_id: str) -> URIRef:
    """The IRI of a corpus document, ``<prefix>doc/<percent-encoded id>`` (ids are paths,
    ``file#key`` or record keys, so they may contain characters an IRI cannot)."""
    return URIRef(f"{prefix}doc/{quote(doc_id, safe='/')}")


def document_triples(prefix: str, doc_id: str, title: str) -> list[tuple]:
    """The triples describing a document the instances are derived from."""
    iri = document_iri(prefix, doc_id)
    return [
        (iri, RDF.type, FOAF.Document), (iri, RDFS.label, Literal(title)), (iri, DCTERMS.identifier, Literal(doc_id)),
    ]


def provenance_graph() -> Graph:
    """Labels of the provenance terms (``document_triples``), for the query editor."""
    g = Graph()
    g.add((FOAF.Document, RDFS.label, Literal("Document")))
    g.add((PROV.wasDerivedFrom, RDFS.label, Literal("extracted from")))
    g.add((DCTERMS.identifier, RDFS.label, Literal("identifier")))
    return g


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "x"


# --- extraction ---


def field_schema(field: OntoField) -> dict:
    """JSON schema of a field's value (an enum without values takes any string)."""
    if field.type == "enum" and field.values:
        return {"type": "string", "enum": list(field.values)}
    return FIELD_SCHEMAS[field.type]


def extraction_schema(onto: Ontology) -> dict:
    """JSON schema of the extraction output: per class a list of instances, each with
    its name, field values and the names of the instances its links point to."""
    properties = {}
    for cls in onto.classes:
        props: dict[str, Any] = {"name": {"type": "string"}}
        for field in cls.fields:
            props[field.name] = field_schema(field)
        for link in onto.links:
            if link.source == cls.id:
                props[link.id] = {"type": "array", "items": {"type": "string"}, "maxItems": MAX_INSTANCES}
        properties[cls.id] = {
            "type": "array",
            "maxItems": MAX_INSTANCES,
            "items": {"type": "object", "properties": props, "required": ["name"]},
        }
    return {"type": "object", "properties": properties, "required": list(properties)}


def example_output(onto: Ontology, output: dict) -> dict:
    """An example's output for the current ontology: every class (empty if not given), the
    instance keys the ontology still has (examples outlive ontology changes)."""
    schema = extraction_schema(onto)["properties"]
    out = {}
    for class_id, prop in schema.items():
        keys = prop["items"]["properties"]
        items = output.get(class_id) or []
        out[class_id] = [
            {k: v for k, v in item.items() if k in keys} for item in items if isinstance(item, dict)
        ]
    return out


def validate_example(onto: Ontology, output: dict) -> dict:
    """``output`` completed for ``onto`` (``example_output``); ValueError if it uses unknown
    classes or keys or does not fit ``extraction_schema``."""
    if not isinstance(output, dict):
        raise ValueError("The output must be a JSON object of class ids.")
    schema = extraction_schema(onto)
    for class_id, items in output.items():
        if class_id not in schema["properties"]:
            raise ValueError(f"Unknown class '{class_id}', classes: {list(schema['properties'])}")
        keys = schema["properties"][class_id]["items"]["properties"]
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and (unknown := set(item) - set(keys)):
                raise ValueError(f"{class_id} has no fields or links {sorted(unknown)}, only {list(keys)}")
    try:
        import jsonschema
    except ImportError:
        jsonschema = None
    if jsonschema is not None:
        try:
            jsonschema.validate(output | {k: [] for k in schema["properties"] if k not in output}, schema)
        except jsonschema.ValidationError as e:
            raise ValueError(f"{e.message} at {'/'.join(map(str, e.absolute_path))}") from None
    else:
        for class_id, items in output.items():
            if not isinstance(items, list) or not all(isinstance(i, dict) and i.get("name") for i in items):
                raise ValueError(f"{class_id} must be a list of objects with a \"name\".")
    return example_output(onto, output)


def _literal(value: Any, field_type: str) -> Literal | None:
    if value is None or value == "" or value == []:
        return None
    if field_type == "vector":
        return Literal(json.dumps(value), datatype=TENSOR)
    if field_type in ("string", "enum"):
        return Literal(str(value))
    return Literal(value, datatype=FIELD_RANGES[field_type])


def extraction_triples(
    onto: Ontology, data: dict, doc: URIRef | None = None,
    resolve: Callable[[str, str], tuple[URIRef, str]] | None = None, text: str | None = None,
) -> list[tuple]:
    """Triples of one document's extraction output (``extraction_schema`` shaped).

    ``text``: the document; if given, only names that occur in it are kept (``grounded``), which
    drops what a small extraction model copies from the prompt (descriptions, few-shot examples)
    while keeping real mentions that also happen to be in a description. Without it, names that
    occur in the class/link descriptions are dropped.

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
        if not name:
            return None
        if text is not None:
            return name if grounded(name, text) else None
        return name if name.lower() not in prompt_text else None

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
        for parent in cls.parents:
            if onto.get_class(parent) is not None:
                g.add((c, RDFS.subClassOf, onto.term(parent)))
        for field in cls.fields:
            p = onto.term(field.name)
            g.add((p, RDF.type, OWL.DatatypeProperty))
            g.add((p, RDFS.label, Literal(field.name)))
            g.add((p, RDFS.domain, c))
            g.add((p, RDFS.range, FIELD_RANGES[field.type]))
            if field.description:
                g.add((p, RDFS.comment, Literal(field.description)))
            if field.type == "enum":
                for value in field.values:
                    g.add((p, SKOS.example, Literal(value)))
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
    for c, cls in classes.items():
        cls.parents = sorted(ids[p] for p in g.objects(c, RDFS.subClassOf) if p in classes)
    schema_terms: set = set(class_iris) | {URIRef(prefix)}
    links = []
    for p in sorted(g.subjects(RDF.type, OWL.DatatypeProperty), key=str):
        schema_terms.add(p)
        field_type = RANGE_FIELDS.get(g.value(p, RDFS.range), "string")
        values = sorted(str(v) for v in g.objects(p, SKOS.example))
        if field_type == "string" and values:
            field_type = "enum"
        for domain in g.objects(p, RDFS.domain):
            if domain in classes:
                classes[domain].fields.append(OntoField(
                    name=_split(str(p))[1], type=field_type, description=text(p, RDFS.comment),
                    values=values[:MAX_VALUES] if field_type == "enum" else [],
                ))
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


def extracted_names(onto: Ontology, data: dict, text: str | None = None) -> list[tuple[str, str]]:
    """(class id, name) of every instance an extraction output adds (``extraction_triples``,
    link targets included, ``text`` grounding the names)."""
    triples = extraction_triples(onto, data, text=text)
    classes = {onto.term(c.id): c.id for c in onto.classes}
    class_of = {s: classes[o] for s, p, o in triples if p == RDF.type and o in classes}
    return sorted({(class_of[s], str(o)) for s, p, o in triples if p == RDFS.label and s in class_of})


def annotation_strings(annotation) -> list[str]:
    """Every string of a gold annotation (any JSON value), e.g. LLMs4OL's types and terms."""
    if isinstance(annotation, str):
        return [annotation]
    if isinstance(annotation, dict):
        return [s for v in annotation.values() for s in annotation_strings(v)]
    if isinstance(annotation, list):
        return [s for v in annotation for s in annotation_strings(v)]
    return []


def annotation_values(annotation, path: str) -> list[str]:
    """The strings at a dotted ``path`` of an annotation, lists flattened on the way:
    ``"types"`` -> the strings of ``annotation["types"]``, ``"terms.term"`` -> each term's name,
    ``"terms.types"`` -> the types of each term. An empty path: every string (``annotation_strings``)."""
    keys = [k for k in path.split(".") if k]
    if not keys:
        return annotation_strings(annotation)

    def flat(value):
        if isinstance(value, list):
            for v in value:
                yield from flat(v)
        else:
            yield value

    values = [annotation]
    for key in keys:
        values = [v[key] for item in values for v in flat(item) if isinstance(v, dict) and key in v]
    return [v.strip() for item in values for v in flat(item) if isinstance(v, str) and v.strip()]


class Vocabulary:
    """The annotation values at ``path`` of a set of annotated documents, matched in texts as
    ``grounded`` does (normalised, singular words, at word boundaries): every n-gram of a text's
    words is looked up, so a match costs a few dict lookups per word whatever the vocabulary's size.
    Stop words and values shorter than 2 characters are left out."""

    # longer values are not matched
    MAX_WORDS = 12

    def __init__(self, annotations: Iterable[tuple[str, Any]], path: str):
        entries: dict[str, tuple[str, set]] = {}
        for doc_id, annotation in annotations:
            if annotation is None:
                continue
            for value in annotation_values(annotation, path):
                key = _singular_words(value)
                if (len(key) < 2 or len(value) > MAX_NAME or key in ENGLISH_STOP_WORDS
                        or normalize(value) in ENGLISH_STOP_WORDS or len(key.split()) > self.MAX_WORDS):
                    continue
                entries.setdefault(key, (value, set()))[1].add(doc_id)
        # normalised singular form -> (surface form, ids of the documents annotated with it)
        self.entries = {k: (v, frozenset(docs)) for k, (v, docs) in entries.items()}
        self.max_words = max((len(k.split()) for k in self.entries), default=0)

    def __len__(self) -> int:
        return len(self.entries)

    def matches(self, text: str, exclude_doc: str | None = None) -> list[str]:
        """The values occurring in ``text`` (surface forms, in order of first occurrence), without
        those only ``exclude_doc`` is annotated with."""
        words = _singular_words(text).split()
        found: dict[str, int] = {}
        for n in range(1, self.max_words + 1):
            for i in range(len(words) - n + 1):
                key = " ".join(words[i:i + n])
                if key in self.entries and key not in found:
                    found[key] = i
        out = []
        for key in sorted(found, key=found.get):
            surface, docs = self.entries[key]
            if exclude_doc is None or docs - {exclude_doc}:
                out.append(surface)
        return out
