"""Progressive discovery: counts of candidate modifications of a query graph.

Given the editor's QueryGraph, the sampler enumerates the modifications the
user could make next (links, starting points of an empty graph and, optionally,
constraints) and counts the results of every modified graph (and of the graph
itself), so the frontend can show how each step would change the result
(frontend/src/utils/progressive, the panel in components/explore/progressive).

Count all, optional sampling: by default every candidate is counted (every link,
every constrained property, every frequent category; with depth > 1 every child of
an expanded modification, deeper levels within max_total_queries). The size fields of
the request (or configuration) are optional limits that sample that many with the
request's seed; the modifications keep their enumeration order either way.

Modules
- sampler.py: ProgressiveSampler, with the details of the candidates, constraint
  candidates, counts, streaming, schema lookups and tree expansion
- models.py: the API models (request, result, modifications), cache key and complete()
- protocol.py: the streaming protocol's messages and events, replay() of cached results
- concurrency.py: the bounded job pool, cancellation, query metering and budget
- runners.py: counts and rows of SPARQL queries (endpoint or OntologyManager)
- values.py: value kinds of literal ranges, weighted percentiles and samples
- candidates.py: candidates before counting, ids, graph keys, seeds and expansions

Timeouts, parallelism, the optional sample sizes and the count/query caps are per configuration, the
``progressive`` object of backend/config.json (eval_config.ProgressiveConfig).
"""

from assistant.progressive.candidates import (
    Candidate,
    ConstraintCandidate,
    default_seed,
    graph_ids,
    graph_key,
    max_cost,
    select_expansions,
    slug,
    stable_seed,
)
from assistant.progressive.concurrency import (
    CancelToken,
    JobPool,
    QueryBudget,
    QueryMeter,
    SamplingCancelled,
    run_bounded,
)
from assistant.progressive.models import (
    CACHE_VERSION,
    ConstraintKind,
    ModificationKind,
    Percentile,
    ProgressiveConstraint,
    ProgressiveModification,
    ProgressiveRequest,
    ProgressiveResult,
    ProgressiveSummary,
    cache_key,
    complete,
    summary,
)
from assistant.progressive.protocol import (
    PROGRESSIVE_CLIENT_MESSAGE,
    PROGRESSIVE_EVENT,
    ProgressiveCancel,
    ProgressiveCount,
    ProgressiveDone,
    ProgressiveError,
    ProgressiveEvent,
    ProgressiveLevel,
    ProgressiveModifications,
    ProgressiveSample,
    ProgressiveStart,
    replay,
)
from assistant.progressive.runners import (
    CountRunner,
    SelectRunner,
    Term,
    counted_graph,
    endpoint_counter,
    endpoint_post,
    endpoint_selector,
    ontology_counter,
    ontology_selector,
)
from assistant.progressive.sampler import (
    CONSTRAINT_ROUNDS,
    RDFS_LABEL,
    UNTYPED_RANGES,
    VALUE_ID,
    ProgressiveSampler,
)
from assistant.progressive.values import (
    DATE_TYPES,
    LITERAL_RANGES,
    NUMERIC_TYPES,
    ORDERED_KINDS,
    STRING_RANGES,
    XSD,
    ValueDistribution,
    literal_value_kind,
    percentile_rank,
    sort_key,
    split_prologue,
    weighted_percentiles,
    weighted_sample,
)

__all__ = [
    "CACHE_VERSION",
    "CONSTRAINT_ROUNDS",
    "DATE_TYPES",
    "LITERAL_RANGES",
    "NUMERIC_TYPES",
    "ORDERED_KINDS",
    "PROGRESSIVE_CLIENT_MESSAGE",
    "PROGRESSIVE_EVENT",
    "RDFS_LABEL",
    "STRING_RANGES",
    "UNTYPED_RANGES",
    "VALUE_ID",
    "XSD",
    "Candidate",
    "CancelToken",
    "ConstraintCandidate",
    "ConstraintKind",
    "CountRunner",
    "JobPool",
    "ModificationKind",
    "Percentile",
    "ProgressiveCancel",
    "ProgressiveConstraint",
    "ProgressiveCount",
    "ProgressiveDone",
    "ProgressiveError",
    "ProgressiveEvent",
    "ProgressiveLevel",
    "ProgressiveModification",
    "ProgressiveModifications",
    "ProgressiveRequest",
    "ProgressiveResult",
    "ProgressiveSample",
    "ProgressiveSampler",
    "ProgressiveStart",
    "ProgressiveSummary",
    "QueryBudget",
    "QueryMeter",
    "SamplingCancelled",
    "SelectRunner",
    "Term",
    "ValueDistribution",
    "cache_key",
    "complete",
    "counted_graph",
    "default_seed",
    "endpoint_counter",
    "endpoint_post",
    "endpoint_selector",
    "graph_ids",
    "graph_key",
    "literal_value_kind",
    "max_cost",
    "ontology_counter",
    "ontology_selector",
    "percentile_rank",
    "replay",
    "run_bounded",
    "sort_key",
    "select_expansions",
    "slug",
    "split_prologue",
    "stable_seed",
    "summary",
    "weighted_percentiles",
    "weighted_sample",
]
