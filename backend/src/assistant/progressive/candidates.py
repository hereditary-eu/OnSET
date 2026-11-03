"""Candidates of modifications before counting, and the ids, keys and seeds of the
sampling: new element ids, duplicate detection and the choice of expanded modifications."""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from dataclasses import dataclass

from assistant.assistant_model import QueryGraph
from assistant.progressive.models import ProgressiveModification, ProgressiveRequest
from assistant.progressive.values import ORDERED_KINDS


@dataclass
class Candidate:
    """A modification before counting: the subject to add, linked from ``from_id`` by ``prop``."""

    # class of the added subject, "" for an untyped one
    target_uri: str
    # None: a starting point of an empty graph
    from_id: str | None = None
    prop: str | None = None

    @property
    def key(self) -> str:
        if self.from_id is None:
            return f"start|{self.target_uri}"
        return f"{self.from_id}|{self.prop}|{self.target_uri}"


@dataclass
class ConstraintCandidate:
    """A constrained property of a subject before sampling: ``prop`` None for its instance."""

    subject_id: str
    # number, date (percentiles), boolean, string, label, instance (categories)
    value_kind: str
    prop: str | None = None
    # literal range of prop, the property_type of the subqueries
    range_uri: str | None = None

    @property
    def key(self) -> str:
        return f"{self.subject_id}|{self.prop or 'instance'}"



def max_cost(candidate: ConstraintCandidate) -> int:
    """Endpoint queries a candidate's value distribution runs at most."""
    return 3 if candidate.value_kind in ORDERED_KINDS else 1


def slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or "subject"


def stable_seed(key: str) -> int:
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:4], "big")


def default_seed(request: ProgressiveRequest) -> int:
    """Seed derived from the graph and sampling parameters, stable across processes."""
    return stable_seed(request.model_dump_json(include={"graph", "subject_ids", "sample_size"}))


def graph_ids(graph: QueryGraph) -> set[str]:
    """Ids of the subjects, links and subqueries of a graph (taken for new elements)."""
    taken = {s.id for s in graph.subjects} | {l.id for l in graph.links}
    return taken | {sq.id for s in graph.subjects for sq in s.subqueries if sq.id}


def graph_key(graph: QueryGraph, base_ids: set[str]) -> str:
    """Key of a modified graph that does not depend on the ids the sampler assigned.

    Subjects of the request graph (``base_ids``) keep their ids, an added subject is
    named by the path of links that added it (``from>property>class``), a starting
    point by its class; subqueries and links are compared without their ids.
    """
    names = {s.id: s.id for s in graph.subjects if s.id in base_ids}
    changed = True
    while changed:
        changed = False
        for link in graph.links:
            if link.from_subject_id in names and link.to_subject_id not in names:
                target = graph.get_subject_by_id(link.to_subject_id)
                names[target.id] = f"{names[link.from_subject_id]}>{link.uri}>{target.uri}"
                changed = True
    for subject in graph.subjects:
        names.setdefault(subject.id, f"+{subject.uri}")

    def dump(model, exclude: set[str]) -> str:
        return json.dumps(model.model_dump(mode="json", exclude=exclude), sort_keys=True)

    subjects = sorted(
        (names[s.id], s.uri, sorted(dump(sq, {"id"}) for sq in s.subqueries)) for s in graph.subjects
    )
    link_fields = {"id", "from_subject_id", "to_subject_id", "label", "from_subject_label", "to_subject_label"}
    links = sorted(
        (names.get(l.from_subject_id, ""), names.get(l.to_subject_id, ""), dump(l, link_fields)) for l in graph.links
    )
    return json.dumps([subjects, links])


def select_expansions(
    modifications: list[ProgressiveModification], branching: int, limit: int, seed: str
) -> list[ProgressiveModification]:
    """The modifications of a level to expand, in their order (see "Tree expansion" in sampler.py).

    Eligible: counted, non-empty and below the count ``limit``. Of more than
    ``branching`` eligible ones, the nearest to ``branching`` targets evenly spread over
    their log-count range (the middle of the range for one), each chosen once; ties are
    broken by a seeded shuffle.
    """
    eligible = [m for m in modifications if m.count is not None and 0 < m.count < limit]
    if len(eligible) <= branching:
        return eligible
    order = {m.id: i for i, m in enumerate(modifications)}
    # the seeded shuffle orders ties of equal distance (min is stable)
    pool = random.Random(seed).sample(eligible, k=len(eligible))
    position = {m.id: math.log10(m.count + 1) for m in pool}
    lo, hi = min(position.values()), max(position.values())
    targets = [(lo + hi) / 2] if branching == 1 else [lo + i * (hi - lo) / (branching - 1) for i in range(branching)]
    chosen: list[ProgressiveModification] = []
    for target in targets:
        best = min(pool, key=lambda m: abs(position[m.id] - target))
        pool.remove(best)
        chosen.append(best)
    return sorted(chosen, key=lambda m: order[m.id])
