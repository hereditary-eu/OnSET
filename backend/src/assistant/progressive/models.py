"""API models of progressive discovery (frontend/src/utils/progressive/types.ts): the
request, the result and its modifications, and what a cached result must satisfy."""

from __future__ import annotations

import enum
import hashlib
from typing import Annotated

from pydantic import BaseModel, Field

from agent.protocol import GraphDetails
from assistant.assistant_model import Operation, QueryGraph

Percentile = Annotated[float, Field(ge=0, le=100)]


class ProgressiveRequest(BaseModel):
    """A request of progressive discovery. Every candidate is counted unless a size is set:
    the sizes below are optional limits, None for the configured default (itself None, i.e.
    all candidates, unless the configuration sets one); a size samples that many candidates
    with ``seed`` (never more than there are), keeping their enumeration order."""

    graph: QueryGraph
    # links (or starting points of an empty graph) to sample and count, None for the
    # configured default (all)
    sample_size: int | None = Field(None, ge=1)
    # subjects whose outgoing links are candidates, None for all subjects
    subject_ids: list[str] | None = None
    # seed of the sampling (of explicit sizes and of the expanded modifications' ties),
    # None for one derived from the graph (stable re-runs)
    seed: int | None = None
    # subject whose distinct bindings are counted, None for the first subject
    count_subject: str | None = None
    # cap of every count, None for the configured default
    count_limit: int | None = Field(None, ge=1)
    # constraint modifications (subqueries of the graph's subjects); the settings
    # below are None for the configured defaults
    sample_constraints: bool | None = None
    # constrained properties with values to sample, None for the configured default (every one)
    constraint_sample_size: int | None = Field(None, ge=0)
    # percentiles (0-100) of numeric/date values that become thresholds
    numeric_percentiles: list[Percentile] | None = None
    # values sampled per categorical property (weighted by frequency), None for the
    # configured default (every value of at least min_category_count results)
    categorical_samples: int | None = Field(None, ge=1)
    # tree expansion: levels of modifications (1: of the request graph only), at most
    # the configured max_depth; each level below the first expands `branching`
    # modifications of the previous one (capped by max_branching), enumerating the links
    # and, with constraints, the constrained properties of each, or sampling
    # child_sample_size links and child_constraint_sample_size constrained properties
    # (0: none) if set; None for the configured defaults (all)
    depth: int = Field(1, ge=1)
    branching: int | None = Field(None, ge=1)
    child_sample_size: int | None = Field(None, ge=1)
    child_constraint_sample_size: int | None = Field(None, ge=0)


class ModificationKind(str, enum.Enum):
    # a starting point of an empty graph
    START = "start"
    # a link to a new subject
    LINK = "link"
    # a subquery of a subject
    CONSTRAINT = "constraint"


class ConstraintKind(str, enum.Enum):
    # a numeric/date threshold at a percentile
    PERCENTILE = "percentile"
    # equals a sampled value (or instance)
    CATEGORY = "category"


class ProgressiveConstraint(BaseModel):
    """What a constraint modification restricts, for display."""

    kind: ConstraintKind
    subject_id: str
    # constrained property, None for the instance of the subject
    property_id: str | None = None
    property_label: str | None = None
    # readable threshold, value or instance label
    value: str
    # percentile kind: the percentile of the threshold
    percentile: float | None = None
    # category kind: counted results with the value in the request graph
    frequency: int | None = None


class ProgressiveModification(BaseModel):
    id: str
    kind: ModificationKind = ModificationKind.LINK
    # operations applied to the request graph (add subjects, links, or a subquery
    # of the subject operation.subject_id)
    operations: list[Operation] = Field([])
    # count of the modified graph, None if it failed or timed out
    count: int | None = None
    label: str
    description: str | None = None
    # ontology data of the added subjects/links keyed by graph id (as the agent sends it)
    details: GraphDetails | None = None
    # constraint modifications: what they restrict
    constraint: ProgressiveConstraint | None = None
    # tree expansion: the modification this one continues (None on the first level),
    # its level (1: a modification of the request graph), and its own operations after
    # the parent's (None on the first level, where they are `operations`); `operations`
    # are cumulative, label/description/constraint describe the own step
    parent_id: str | None = None
    depth: int = 1
    step_operations: list[Operation] | None = None


class ProgressiveSummary(BaseModel):
    """The fields of a result besides its modifications (the ``done`` event's)."""

    # count of the request graph, None for an empty graph or a failed count
    base_count: int | None = None
    # link candidates (== the number of first-level link modifications unless sample_size is set)
    candidate_count: int | None = None
    # cap of the counts, a count equal to it is a lower bound
    count_limit: int | None = None
    # subject id the counts are of (of the request graph, None if empty)
    count_subject: str | None = None
    seed: int | None = None
    # constrained properties (all tried unless constraint_sample_size is set), None without constraints
    constraint_candidate_count: int | None = None
    # keys (subject|property) of tried constraint candidates whose value
    # distribution failed or timed out, so they have no modifications
    failed_constraints: list[str] = Field([])
    # tree expansion: levels sampled (fewer than requested if none could be expanded),
    # ids of the modifications whose children were sampled, children left out as their
    # graph is another modification's (same steps in another order), endpoint queries
    # (counts, value distributions) of the request, their cap (max_total_queries) and
    # whether deeper levels were cut short by it
    depth: int = 1
    expanded_ids: list[str] = Field([])
    duplicate_count: int = 0
    query_count: int | None = None
    query_budget: int | None = None
    budget_exhausted: bool = False


class ProgressiveResult(ProgressiveSummary):
    modifications: list[ProgressiveModification] = Field([])


def summary(result: ProgressiveResult) -> ProgressiveSummary:
    return ProgressiveSummary(**result.model_dump(exclude={"modifications"}))


# version of the cached results, bumped whenever their content changes for the same request
# 2: details from the stored schema (before: Subject.to_link, instance_count 0)
# 3: all candidates counted by default (before: samples of 48 links, 8 properties, 3 values)
CACHE_VERSION = 3


def cache_key(request: ProgressiveRequest) -> str:
    digest = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
    return f"progressive:v{CACHE_VERSION}:{digest}"


def complete(result: ProgressiveResult) -> bool:
    """Whether every count and lookup succeeded, only then a result is worth caching."""
    counts = [m.count for m in result.modifications]
    if result.count_subject is not None:
        # an empty graph has no base count
        counts.append(result.base_count)
    return (
        all(c is not None for c in counts)
        and all(m.details is not None for m in result.modifications)
        and not result.failed_constraints
    )
