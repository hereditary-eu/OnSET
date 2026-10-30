// Data contract of progressive discovery: the backend samples candidate modifications
// (outgoing links) of the current query graph, runs a count query per modification and
// returns (modification, count) records; the side panel shows them as a histogram of
// counts and the modifications nearest to a scrubbed count as difference views.
//
// The generated types of POST /progressive/sample (backend/src/assistant/progressive.py),
// with the editor's graph (ids always set) and the fields the backend always fills required;
// source.ts normalises responses to these.
import type {
    ModificationKind,
    Operation,
    ProgressiveModification as ApiProgressiveModification,
    ProgressiveRequest as ApiProgressiveRequest,
    ProgressiveResult as ApiProgressiveResult,
} from '@/api/client.ts/Api'
import type { GraphDetails } from '@/utils/agent/protocol'
import type { EditorQueryGraph } from '@/utils/sparql/querygraph'

export type ProgressiveOperation = Operation

/**
 * graph: the current editor graph, toQueryGraph(store, { payloads: false });
 * sample_size: maximum number of candidates to sample and count; subject_ids: subjects
 * whose outgoing links are candidates (null for all); seed: of the sampling (null: derived
 * from the graph, so re-runs are stable); count_subject: subject whose distinct bindings are
 * counted (null: the first subject); count_limit: cap of the counts (null: backend default).
 */
export type ProgressiveRequest = Omit<ApiProgressiveRequest, 'graph' | 'sample_size'> & {
    graph: EditorQueryGraph
    sample_size: number
}

/**
 * kind: start (of an empty graph), link (a link to a new subject) or constraint (a subquery
 * of a subject, operation.subject_id); operations: applied to the request graph;
 * count: of the modified graph, null when it failed or timed out; label: e.g.
 * "ship → homeport → country" or "ship: length > 120 (p75)"; details: ontology data of the
 * added subjects/links, keyed by graph id (as the agent sends it); constraint: what a
 * constraint restricts (percentile threshold or sampled category with its frequency).
 */
export type ProgressiveModification = Omit<ApiProgressiveModification, 'operations' | 'details' | 'kind'> & {
    kind: ModificationKind | `${ModificationKind}`
    operations: ProgressiveOperation[]
    details?: GraphDetails | null
}

/** Constraint sampling settings the panel sends with a request (defaults: GET /ontology/config). */
export interface ConstraintSettings {
    sample_constraints: boolean
    /** constrained properties to sample */
    constraint_sample_size: number
    /** percentiles (0-100) of numeric/date values that become thresholds */
    numeric_percentiles: number[]
    /** values sampled per categorical property */
    categorical_samples: number
}

/**
 * base_count: of the request graph, null when it is empty or the count failed;
 * candidate_count: candidates before sampling (>= modifications.length); count_limit: cap
 * of the counts, a count equal to it is a lower bound; count_subject: the counted subject
 * (null for an empty graph).
 */
export type ProgressiveResult = Omit<ApiProgressiveResult, 'modifications'> & {
    modifications: ProgressiveModification[]
}
