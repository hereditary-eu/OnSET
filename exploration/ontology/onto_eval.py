"""Scoring of ontologies built by the ontology builder (agent runs or user sessions) against
a reference ontology, and of their extracted instances against gold annotations.

Both sides are the builder's own ``Ontology`` (backend/src/builder/ontology.py), wrapped
in a ``Schema`` that adds what references need and the builder's model has no place for:
alternative class names (skos:altLabel) and superclasses. A reference property with
several (domain, range) pairs (``ref:signature [ rdfs:domain X ; rdfs:range Y ]`` in its
Turtle, or an owl:unionOf domain/range) becomes one ``OntoLink`` per pair, sharing the id.
References are parsed by the builder's importer (``ontology_from_graph``).

Schema metrics (``score_schema``), each as P/R/F1 at three strictness levels: ``exact``
(normalised names equal), ``fuzzy`` (rapidfuzz token-sort ratio) and ``sem`` (max of fuzzy
and sentence-embedding cosine):
- ``class_*``: one-to-one (Hungarian) alignment of classes by label/id; ``class_*_cov_*``
  is the many-to-one variant (a reference class is found if any predicted class matches it).
- ``rel_label_*``: link names only; ``rel_triple_*``: (link, source, target) against the
  reference pairs, the classes mapped by the many-to-one class alignment (a sub- or
  superclass of the reference domain/range counts).
- ``field_*``: datatype fields by name and class.
``schema_sem_f1`` averages the class, triple and (if the reference has fields) field F1.

Instance metrics (``score_mentions``): per-document mentions (normalised name, reference
class) and relations (subject, reference link, object) against gold annotations; the
predicted side is the triples the build adds (``extraction_triples``), mapped to the
reference by the schema alignment.

Term lists (``text2onto_metrics``): the LLMs4OL 2025 Task A score.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import inflection
import numpy as np
from rapidfuzz import fuzz
from rdflib import DCTERMS, OWL, RDF, RDFS, SKOS, BNode, Graph, URIRef
from rdflib.collection import Collection
from scipy.optimize import linear_sum_assignment

from builder.disambiguate import normalize
from builder.ontology import PROV, OntoClass, OntoLink, Ontology, _split, ontology_from_graph

HERE = Path(__file__).resolve().parent
REFERENCES = HERE / "references"
EMBEDDING_MODEL = os.getenv("ONSET_EVAL_EMBEDDING", "sentence-transformers/all-MiniLM-L6-v2")
# match thresholds (similarities in [0, 1])
FUZZY_THRESHOLD = float(os.getenv("ONSET_EVAL_FUZZY", "0.9"))
# all-MiniLM cosine: synonyms ("company"/"organization") ~0.6+, unrelated classes < 0.4
SEM_THRESHOLD = float(os.getenv("ONSET_EVAL_SEM", "0.6"))
LEVELS = ("exact", "fuzzy", "sem")

# --- names ---

def term_name(text: str) -> str:
    """A schema term's name as compared: ids split (``MicrobialMetabolites``,
    ``microbial_metabolite``), the builder's ``normalize`` and singular words (inflection)."""
    words = normalize(inflection.underscore(str(text or ""))).split()
    # short words are function words ("is" would become "i")
    return " ".join(inflection.singularize(w) if len(w) > 3 else w for w in words)


def _local(iri) -> str:
    return _split(str(iri))[1]


# --- schemas ---


@dataclass
class Schema:
    name: str
    onto: Ontology
    # class id -> other names / superclass ids
    aliases: dict[str, list[str]] = field(default_factory=dict)
    parents: dict[str, set[str]] = field(default_factory=dict)

    @property
    def classes(self) -> list[OntoClass]:
        return self.onto.classes

    @property
    def links(self) -> list[OntoLink]:
        return self.onto.links

    @property
    def fields(self) -> list[tuple[str, object]]:
        """(class id, OntoField) of every field."""
        return [(c.id, f) for c in self.onto.classes for f in c.fields]

    def link_ids(self) -> list[str]:
        return list(dict.fromkeys(l.id for l in self.onto.links))

    def names(self, cls: OntoClass) -> list[str]:
        return [cls.label or cls.id, cls.id, *self.aliases.get(cls.id, [])]

    def ancestors(self, cid: str) -> set[str]:
        seen, todo = set(), [cid]
        while todo:
            for p in self.parents.get(todo.pop(), ()):
                if p not in seen:
                    seen.add(p)
                    todo.append(p)
        return seen

    def related(self, a: str | None, b: str | None) -> bool:
        """``a`` is ``b`` or one of its sub- or superclasses (None: unconstrained)."""
        if a is None or b is None:
            return True
        return a == b or b in self.ancestors(a) or a in self.ancestors(b)

    def summary(self) -> dict:
        return {
            "classes": len(self.classes), "links": len(self.link_ids()), "signatures": len(self.links),
            "fields": len(self.fields), "subclass_edges": sum(len(p) for p in self.parents.values()),
        }


def schema_from_ontology(onto: Ontology | dict, name: str = "predicted") -> Schema:
    """The schema of a builder ``Ontology`` (or a saved session's ``ontology`` dict)."""
    onto = onto if isinstance(onto, Ontology) else Ontology(**onto)
    parents = {c.id: set(getattr(c, "parents", None) or []) for c in onto.classes}
    return Schema(name, onto, parents={k: v for k, v in parents.items() if v})


def _class_set(g: Graph, node) -> list:
    """The classes a domain/range names: a class, or the members of an owl:unionOf."""
    if isinstance(node, BNode) and (union := g.value(node, OWL.unionOf)) is not None:
        return list(Collection(g, union))
    return [node]


def schema_from_graph(g: Graph, name: str) -> Schema:
    """The schema of OWL/RDFS Turtle (references, builder exports): the builder's import
    (``ontology_from_graph``) plus alt labels, subclass edges and multi-pair properties."""
    onto, _ = ontology_from_graph(g)
    schema = schema_from_ontology(onto, name)
    iris = {s for t in (OWL.Class, RDFS.Class) for s in g.subjects(RDF.type, t) if isinstance(s, URIRef)}
    for c in iris:
        if aliases := [str(a) for a in g.objects(c, SKOS.altLabel)]:
            schema.aliases[_local(c)] = aliases
        if parents := {_local(p) for p in g.objects(c, RDFS.subClassOf) if p in iris}:
            schema.parents.setdefault(_local(c), set()).update(parents)
    sig = next((URIRef(str(ns) + "signature") for prefix, ns in g.namespaces() if prefix == "ref"), None)
    known = {c.id for c in onto.classes}

    def cid(node) -> str | None:
        return _local(node) if node is not None and _local(node) in known else None

    links = []
    for p in sorted(set(g.subjects(RDF.type, OWL.ObjectProperty)), key=str):
        pairs = [(cid(g.value(s, RDFS.domain)), cid(g.value(s, RDFS.range)))
                 for s in (g.objects(p, sig) if sig is not None else [])]
        if not pairs:
            domains = [d for n in (list(g.objects(p, RDFS.domain)) or [None]) for d in _class_set(g, n)]
            ranges = [r for n in (list(g.objects(p, RDFS.range)) or [None]) for r in _class_set(g, n)]
            pairs = [(cid(d), cid(r)) for d in domains for r in ranges]
        label, comment = str(g.value(p, RDFS.label) or _local(p)), str(g.value(p, RDFS.comment) or "")
        # an unconstrained end is "" (OntoLink needs a class id; "" relates to every class)
        links += [OntoLink(id=_local(p), label=label, source=d or "", target=r or "", description=comment)
                  for d, r in sorted(set(pairs), key=str)]
    onto.links = links
    return schema


def extraction_ontology(schema: Schema) -> Ontology:
    """A schema as an ontology the builder can extract with (e.g. a reference, to benchmark the
    extractor with the true ontology): superclasses kept, every (domain, range) pair of a property
    its own link, labelled like the property (so the alignment maps it back); a link id repeated
    for the same source class gets its target appended (the extraction schema keys links by id
    per class), unconstrained ends are dropped."""
    onto = schema.onto.model_copy(deep=True)
    for cls in onto.classes:
        cls.parents = sorted(schema.parents.get(cls.id, ()))
    links, seen = [], set()
    for link in onto.links:
        if not link.source or not link.target:
            continue
        link_id = link.id if (link.id, link.source) not in seen else f"{link.id}{link.target}"
        seen.add((link.id, link.source))
        links.append(link.model_copy(update={"id": link_id}))
    onto.links = links
    return onto


def load_reference(name_or_path: str) -> Schema:
    path = Path(name_or_path)
    if not path.exists():
        path = REFERENCES / f"{name_or_path}.ttl"
    return schema_from_graph(Graph().parse(path, format="turtle"), path.stem)


def load_session(path: str | Path) -> dict | None:
    """The saved state of a builder session (``<save_dir>/<builder>/<id>.json``, as
    ``BuilderSession.persist`` writes it), None for other files (edit histories)."""
    path = Path(path)
    if path.name.endswith(".history.json"):
        return None
    try:
        state = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return state if isinstance(state, dict) and isinstance(state.get("ontology"), dict) else None


# --- similarity ---


@lru_cache(maxsize=1)
def _embedder():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL, device=os.getenv("ONSET_EVAL_DEVICE", "cpu"))


_EMB_CACHE: dict[str, np.ndarray] = {}


def embed(texts: list[str]) -> np.ndarray:
    missing = [t for t in dict.fromkeys(texts) if t not in _EMB_CACHE]
    if missing:
        vectors = _embedder().encode(missing, normalize_embeddings=True, batch_size=256, show_progress_bar=False)
        _EMB_CACHE.update(zip(missing, vectors))
    return np.stack([_EMB_CACHE[t] for t in texts]) if texts else np.zeros((0, 1))


def similarity(a: list[list[str]], b: list[list[str]], semantic: bool = True) -> dict[str, np.ndarray]:
    """Similarity matrices (len(a) x len(b)) per strictness level of items with one or more
    names each (the best pair of names counts)."""
    fa = [(i, term_name(n)) for i, names in enumerate(a) for n in names if term_name(n)]
    fb = [(j, term_name(n)) for j, names in enumerate(b) for n in names if term_name(n)]
    na, nb = [n for _, n in fa], [n for _, n in fb]
    flat = {
        "exact": np.array([[float(x == y) for y in nb] for x in na]).reshape(len(na), len(nb)),
        "fuzzy": np.array([[fuzz.token_sort_ratio(x, y) / 100 for y in nb] for x in na]).reshape(len(na), len(nb)),
    }
    # a fuzzy match below its own threshold is no match at the sem level either
    fuzzy_hit = np.where(flat["fuzzy"] >= FUZZY_THRESHOLD - 1e-9, flat["fuzzy"], 0.0)
    flat["sem"] = np.maximum(fuzzy_hit, embed(na) @ embed(nb).T) if semantic and na and nb else fuzzy_hit
    out = {}
    ia, ib = np.array([i for i, _ in fa], dtype=int), np.array([j for j, _ in fb], dtype=int)
    for level, mat in flat.items():
        res = np.zeros((len(a), len(b)))
        if mat.size:
            np.maximum.at(res, (ia[:, None], ib[None, :]), mat)
        out[level] = res
    return out


def threshold(level: str) -> float:
    return {"exact": 1.0, "fuzzy": FUZZY_THRESHOLD, "sem": SEM_THRESHOLD}[level] - 1e-9


def prf(tp: float, n_pred: int, n_ref: int) -> tuple[float, float, float]:
    p = tp / n_pred if n_pred else float("nan")
    r = tp / n_ref if n_ref else float("nan")
    if not (n_pred and n_ref):
        return p, r, (0.0 if n_ref else float("nan"))
    return p, r, (2 * p * r / (p + r) if p + r > 0 else 0.0)


def assign(score: np.ndarray, min_score: float) -> list[tuple[int, int, float]]:
    """One-to-one assignment maximising the summed score, pairs at least ``min_score``."""
    if score.size == 0:
        return []
    rows, cols = linear_sum_assignment(-score)
    return [(int(i), int(j), float(score[i, j])) for i, j in zip(rows, cols) if score[i, j] >= min_score]


def _put(m: dict, key: str, values: tuple):
    m[f"{key}_p"], m[f"{key}_r"], m[f"{key}_f1"] = values


# --- schema scoring ---


@dataclass
class SchemaScore:
    metrics: dict
    # level -> predicted class id -> reference class id (many-to-one, best match)
    class_map: dict[str, dict[str, str]]
    # predicted link id -> reference link id (sem level, best match by name)
    link_map: dict[str, str]
    # aligned pairs for inspection
    alignment: dict


def score_schema(pred: Schema, ref: Schema, semantic: bool = True) -> SchemaScore:
    m: dict = {f"pred_{k}": v for k, v in pred.summary().items()} | {f"ref_{k}": v for k, v in ref.summary().items()}
    alignment: dict = {}
    pc, rc = pred.classes, ref.classes
    csim = similarity([pred.names(c) for c in pc], [ref.names(c) for c in rc], semantic)
    class_map: dict = {}
    for level in LEVELS:
        s, t = csim[level], threshold(level)
        pairs = assign(s, t)
        _put(m, f"class_{level}", prf(len(pairs), len(pc), len(rc)))
        alignment[f"class_{level}"] = [(pc[i].id, rc[j].id, round(v, 3)) for i, j, v in pairs]
        hit = s >= t
        m[f"class_{level}_cov_p"] = hit.any(axis=1).mean() if hit.size else float("nan")
        m[f"class_{level}_cov_r"] = hit.any(axis=0).mean() if hit.size else float("nan")
        class_map[level] = {c.id: rc[int(s[i].argmax())].id for i, c in enumerate(pc) if hit.size and hit[i].any()}

    # links by name (distinct ids), then as (link, source, target) triples against the pairs
    pids, rids = pred.link_ids(), ref.link_ids()
    plabel = {l.id: l.label for l in pred.links}
    rlabel = {l.id: l.label for l in ref.links}
    lsim = similarity([[plabel[i], i] for i in pids], [[rlabel[j], j] for j in rids], semantic)
    link_map: dict = {}
    for level in LEVELS:
        s, t = lsim[level], threshold(level)
        pairs = assign(s, t)
        _put(m, f"rel_label_{level}", prf(len(pairs), len(pids), len(rids)))
        if level == "sem":
            alignment["rel_label"] = [(pids[i], rids[j], round(v, 3)) for i, j, v in pairs]
            link_map = {p: rids[int(s[i].argmax())] for i, p in enumerate(pids) if s.size and s[i].max() >= t}
        cmap = class_map[level]
        tri = np.zeros((len(pred.links), len(ref.links)))
        for a, pl in enumerate(pred.links):
            src, dst = cmap.get(pl.source), cmap.get(pl.target)
            if (pl.source and src is None) or (pl.target and dst is None):
                continue
            for b, rl in enumerate(ref.links):
                v = s[pids.index(pl.id), rids.index(rl.id)]
                if v >= t and ref.related(src, rl.source or None) and ref.related(dst, rl.target or None):
                    tri[a, b] = v
        pairs = assign(tri, t)
        _put(m, f"rel_triple_{level}", prf(len(pairs), len(pred.links), len(ref.links)))
        if level == "sem":
            fmt = lambda l: f"{l.id}({l.source},{l.target})"
            alignment["rel_triple"] = [(fmt(pred.links[a]), fmt(ref.links[b]), round(v, 3)) for a, b, v in pairs]

    # fields by name, within mapped classes
    pf, rf = pred.fields, ref.fields
    fsim = similarity([[f.name] for _, f in pf], [[f.name] for _, f in rf], semantic)
    for level in LEVELS:
        cmap, s = class_map[level], fsim[level].copy()
        for i, (cid, _) in enumerate(pf):
            for j, (rcid, _) in enumerate(rf):
                if cmap.get(cid) is None or not ref.related(cmap[cid], rcid):
                    s[i, j] = 0
        pairs = assign(s, threshold(level))
        _put(m, f"field_{level}", prf(len(pairs), len(pf), len(rf)))
        if level == "sem":
            alignment["field"] = [(f"{pf[i][0]}.{pf[i][1].name}", f"{rf[j][0]}.{rf[j][1].name}", round(v, 3))
                                  for i, j, v in pairs]
    parts = [m["class_sem_f1"], m["rel_triple_sem_f1"]] + ([m["field_sem_f1"]] if rf else [])
    m["schema_sem_f1"] = float(np.mean([0.0 if np.isnan(x) else x for x in parts]))
    return SchemaScore(m, class_map, link_map, alignment)


# --- instance (mention) scoring ---


@dataclass
class Mentions:
    """Per-document entity mentions and relations, gold or predicted (predicted ones in the
    predicted ontology's class/link ids until mapped)."""
    # doc id -> {(normalised name, class id)}
    entities: dict[str, set[tuple[str, str]]] = field(default_factory=lambda: defaultdict(set))
    # doc id -> {(subject name, link id, object name)}
    relations: dict[str, set[tuple[str, str, str]]] = field(default_factory=lambda: defaultdict(set))


def mentions_from_graph(graph: Graph, prefix: str) -> Mentions:
    """Mentions of the triples a build adds (``extraction_triples`` with ``document_triples``,
    or a whole KG): instances by their ``prov:wasDerivedFrom`` documents (their corpus id is
    the ``dcterms:identifier``), every name (rdfs:label, skos:altLabel) a mention; a relation
    counts for the documents both its ends come from."""
    docs_of, names_of, class_of = {}, {}, defaultdict(set)
    for s, _, cls in graph.triples((None, RDF.type, None)):
        if isinstance(s, URIRef) and str(cls).startswith(prefix):
            class_of[s].add(str(cls)[len(prefix):])
            names_of[s] = {normalize(str(n)) for p in (RDFS.label, SKOS.altLabel) for n in graph.objects(s, p)}
            docs_of[s] = {str(graph.value(d, DCTERMS.identifier) or d) for d in graph.objects(s, PROV.wasDerivedFrom)}
    out = Mentions()
    for s, docs in docs_of.items():
        for d in docs:
            out.entities[d].update((n, c) for n in names_of[s] for c in class_of[s])
    for s, p, o in graph:
        if s in docs_of and o in docs_of and str(p).startswith(prefix):
            for d in docs_of[s] & docs_of[o]:
                out.relations[d].update((a, str(p)[len(prefix):], b) for a in names_of[s] for b in names_of[o])
    return out


def _name_ok(a: str, b: str) -> bool:
    """Lenient name match: equal, one contains the other, or close (plural, articles)."""
    return a == b or (min(len(a), len(b)) >= 3 and (a in b or b in a)) or fuzz.ratio(a, b) >= 85


def _matches(pred: set, gold: set, lenient: bool) -> int:
    """Gold items matched one-to-one, names (all but a pair's class / a triple's link)
    compared exactly or leniently."""
    tp = len(pred & gold)
    if not lenient:
        return tp
    left = list(gold - pred)
    for p in pred - gold:
        names = (0, 2) if len(p) == 3 else (0,)
        for k, g in enumerate(left):
            if all(_name_ok(p[i], g[i]) if i in names else p[i] == g[i] for i in range(len(p))):
                tp += 1
                left.pop(k)
                break
    return tp


def score_mentions(pred: Mentions, gold: Mentions, class_map: dict[str, str], link_map: dict[str, str],
                   docs: Iterable[str] | None = None) -> dict:
    """Micro P/R/F1 over ``docs`` (default: the gold documents) of entities (``ent``: names,
    ``ent_typed``: names with their mapped reference class) and relations (``rel_typed``: with
    the mapped reference link, ``rel_pair``: unordered pairs), strict and lenient names."""
    docs = list(docs if docs is not None else gold.entities.keys() | gold.relations.keys())
    out: dict = {"docs": len(docs)}
    for tag, lenient in (("strict", False), ("len", True)):
        counts = defaultdict(lambda: [0, 0, 0])
        for d in docs:
            ge, pe = gold.entities.get(d, set()), pred.entities.get(d, set())
            gr, pr = gold.relations.get(d, set()), pred.relations.get(d, set())
            sets = {
                "ent": ({(n,) for n, _ in pe}, {(n,) for n, _ in ge}),
                "ent_typed": ({(n, class_map.get(c, "?")) for n, c in pe}, ge),
                "rel_typed": ({(s, link_map.get(p, "?"), o) for s, p, o in pr}, gr),
                "rel_pair": ({(*sorted((s, o)),) for s, _, o in pr}, {(*sorted((s, o)),) for s, _, o in gr}),
            }
            for k, (p, g) in sets.items():
                if k == "rel_pair":  # both ends are names
                    p, g = {(a, "", b) for a, b in p}, {(a, "", b) for a, b in g}
                counts[k][0] += _matches(p, g, lenient)
                counts[k][1] += len(p)
                counts[k][2] += len(g)
        for k, (tp, n_pred, n_gold) in counts.items():
            _put(out, f"{k}_{tag}", prf(tp, n_pred, n_gold))
    return out


# --- term lists (LLMs4OL 2025 Task A) ---


def _jaccard(a: str, b: str) -> float:
    sa, sb = set(a.lower().split()), set(b.lower().split())
    return 1.0 if not sa and not sb else len(sa & sb) / len(sa | sb)


def text2onto_metrics(pred: list[str], gold: list[str], prefix: str, threshold: float = 0.8) -> dict:
    """The LLMs4OL 2025 Task A score of a predicted list against the gold list
    (OntoLearner ``text2onto_metrics`` at the challenge's commit 056d477): a prediction is
    correct if its token-set Jaccard similarity to a not yet matched gold label is at least
    ``threshold`` (greedy in prediction order, lowercased whitespace tokens, no dedup)."""
    matched_gold: set[int] = set()
    correct = 0
    for p in pred:
        for j, g in enumerate(gold):
            if j not in matched_gold and _jaccard(p, g) >= threshold:
                matched_gold.add(j)
                correct += 1
                break
    out = {f"{prefix}_n_pred": len(pred), f"{prefix}_n_gold": len(gold)}
    _put(out, prefix, prf(correct, len(pred), len(gold)))
    return out
