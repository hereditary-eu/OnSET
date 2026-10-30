// Data contract of progressive discovery: the backend samples candidate modifications
// (outgoing links) of the current query graph, runs a count query per modification and
// returns (modification, count) records; the side panel shows them as a histogram of
// counts and the modifications nearest to a scrubbed count as difference views.
//
// The generated types of POST /progressive/sample (backend/src/assistant/progressive.py),
// with the editor's graph (ids always set) and the fields the backend always fills required;
// source.ts normalises responses to these.
import type {
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
 * operations: applied to the request graph (add a subject and the link to it);
 * count: of the modified graph, null when it failed or timed out; label: e.g.
 * "ship → homeport → country"; details: ontology data of the added subjects/links,
 * keyed by graph id (as the agent sends it).
 */
export type ProgressiveModification = Omit<ApiProgressiveModification, 'operations' | 'details'> & {
    operations: ProgressiveOperation[]
    details?: GraphDetails | null
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
