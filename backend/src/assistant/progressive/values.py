"""Value kinds of literal ranges and the statistics of value distributions: weighted
percentiles (thresholds) and weighted samples (categories)."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Sequence, TypeVar

from assistant.progressive.runners import Term
from assistant.sparql_gen import INTEGER_TYPES

T = TypeVar("T")

XSD = "http://www.w3.org/2001/XMLSchema#"
# ranges that are literals, i.e. of datatype properties declared as rdf:Property
LITERAL_RANGES = {
    "http://www.w3.org/2000/01/rdf-schema#Literal",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#langString",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#HTML",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#XMLLiteral",
}

# value kinds of constraint candidates by literal range (local names of xsd types)
NUMERIC_TYPES = {"decimal", "double", "float"} | (INTEGER_TYPES - {"gYear"})
DATE_TYPES = {"date", "dateTime"}
STRING_RANGES = {
    XSD + "string",
    "http://www.w3.org/2000/01/rdf-schema#Literal",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#langString",
}
# value kinds with percentile thresholds, the others are categorical
ORDERED_KINDS = {"number", "date"}


def literal_value_kind(iri: str) -> str | None:
    """Constraint kind (number, date, boolean, string) of a literal range given as a
    full IRI (without <>), None if it has none."""
    local = iri[len(XSD):] if iri.startswith(XSD) else None
    if local in NUMERIC_TYPES:
        return "number"
    if local in DATE_TYPES:
        return "date"
    if local == "boolean":
        return "boolean"
    if iri in STRING_RANGES:
        return "string"
    return None


@dataclass
class ValueDistribution:
    """Values of a constraint candidate in the request graph's context.

    ordered kinds: the thresholds (percentile, value); categories: the most frequent
    (value, count of counted results) that pass min_category_count, most frequent first.
    """

    thresholds: list[tuple[float, Term]] = field(default_factory=list)
    categories: list[tuple[Term, int]] = field(default_factory=list)


def sort_key(kind: str, term: Term):
    """Order of numeric/date values, None for values that cannot be compared."""
    try:
        if kind == "number":
            return float(term.value)
        value = term.value.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(value)
        # dates and naive date-times compare as naive (time zones are dropped)
        return parsed.replace(tzinfo=None)
    except ValueError:
        return None


def percentile_rank(percentile: float, total: int) -> int:
    """1-based nearest rank of a percentile among ``total`` (weighted) values."""
    return min(total, max(1, math.ceil(percentile / 100 * total)))


def weighted_percentiles(kind: str, values: list[tuple[Term, int]], percentiles: Sequence[float]) -> list[tuple[float, Term]]:
    """(percentile, value) by weighted nearest rank; values that cannot be ordered are left out."""
    keyed = sorted(
        ((key, term, weight) for term, weight in values if weight > 0 and (key := sort_key(kind, term)) is not None),
        key=lambda v: v[0],
    )
    total = sum(weight for _, _, weight in keyed)
    if total == 0:
        return []
    thresholds = []
    for percentile in percentiles:
        rank, cumulative = percentile_rank(percentile, total), 0
        for _, term, weight in keyed:
            cumulative += weight
            if cumulative >= rank:
                thresholds.append((percentile, term))
                break
    return thresholds


def weighted_sample(items: Sequence[T], weights: Sequence[float], k: int, rng: random.Random) -> list[T]:
    """``k`` items drawn without replacement, each draw proportional to the weights.

    Efraimidis-Spirakis: the k largest keys u^(1/weight), u uniform from ``rng``, in the
    order of ``items`` (which must be deterministic for a seeded sample).
    """
    keys = [(rng.random() ** (1 / weight), i) for i, weight in enumerate(weights) if weight > 0]
    chosen = sorted(i for _, i in sorted(keys, reverse=True)[:k])
    return [items[i] for i in chosen]


def split_prologue(query: str) -> tuple[str, str]:
    """PREFIX lines and the rest of a generated query."""
    lines = query.split("\n")
    prologue = [line for line in lines if line.startswith("PREFIX ")]
    return "\n".join(prologue), "\n".join(lines[len(prologue):])
