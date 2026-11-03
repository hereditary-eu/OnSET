// State of the progressive panel: re-runs the source (debounced) when the editor graph
// changes (cancelling the running request), shows its partial results as they stream in, and derives the histogram, the modifications nearest to the scrubbed count and
// the tree of modifications (tree expansion, depth > 1).
//
// Graph changes are detected like the agent's sync (agentSession.ts): a deep watch of the
// editor store, compared by graphKey() so layout-only changes (dragging nodes) do not re-run.
import { computed, onBeforeUnmount, reactive, watch } from 'vue'
import { graphKey } from '@/utils/agent/graph_sync'
import { toQueryGraph } from '@/utils/sparql/querygraph'
import { OntoConfig } from '@/utils/sparql/ontoconfig'
import { RepositoryState, type NodeLinkRepository } from '@/utils/sparql/store'
import {
    countExtent, histogramBins, medianCount, nearestModifications, operationsToChange,
} from './histogram'
import { progressiveSource, type ProgressiveSource } from './source'
import { ancestorIds, buildTree, modificationPath, modificationsById } from './tree'
import type { ConstraintSettings, DepthSettings, ProgressiveModification, ProgressiveRequest, ProgressiveResult } from './types'

export type ProgressiveStatus = 'idle' | 'loading' | 'ready' | 'error'
/** what the panel lists: the modifications nearest to the scrubbed count, or the tree */
export type ProgressiveView = 'nearest' | 'tree'

export interface ProgressiveOptions {
    source?: ProgressiveSource
    /** initial sample size, by default the configuration's (GET /ontology/config); null or
     * left out there: every candidate is counted */
    sample_size?: number | null
    /** modifications shown as difference views */
    nearest?: number
    bin_count?: number
    debounce_ms?: number
}

export function useProgressive(graphSource: () => NodeLinkRepository | null | undefined, options: ProgressiveOptions = {}) {
    const source = options.source ?? progressiveSource
    const debounce_ms = options.debounce_ms ?? 600
    const state = reactive({
        status: 'idle' as ProgressiveStatus,
        error: null as string | null,
        result: null as ProgressiveResult | null,
        /** links sampled and counted, null for all of them */
        sample_size: (options.sample_size ?? null) as number | null,
        nearest: options.nearest ?? 10,
        bin_count: options.bin_count ?? 24,
        /** row count selected by the scrubber, null to follow the base count */
        scrub_count: null as number | null,
        /** constraint modifications (subqueries) besides the links, defaults from the configuration
         * (null sizes: every property and frequent value) */
        constraints: {
            sample_constraints: false,
            constraint_sample_size: null,
            numeric_percentiles: [10, 25, 50, 75, 90],
            categorical_samples: null,
        } as ConstraintSettings,
        /** tree expansion, defaults and caps from the configuration (null: all links of a node) */
        tree: { depth: 1, branching: 4, child_sample_size: null } as DepthSettings,
        max_depth: null as number | null,
        max_branching: null as number | null,
        view: 'nearest' as ProgressiveView,
        /** modification selected in the tree (scrubbed to, highlighted in the histogram) */
        selected_id: null as string | null,
    })

    /** the request of the graph; the constraint settings only when they are sampled, the tree
     * settings only beyond depth 1; sizes that are null (all candidates) are left out */
    const request = (graph: ProgressiveRequest['graph']): ProgressiveRequest => {
        const constraints = state.constraints
        const body: ProgressiveRequest = constraints.sample_constraints
            ? { graph, ...constraints, numeric_percentiles: [...constraints.numeric_percentiles] }
            : { graph, sample_constraints: false }
        const full: ProgressiveRequest = {
            ...body,
            sample_size: state.sample_size,
            ...(state.tree.depth > 1 ? state.tree : {}),
        }
        const sizes = ['sample_size', 'constraint_sample_size', 'categorical_samples', 'child_sample_size'] as const
        for (const size of sizes) {
            if (full[size] == null) {
                delete full[size]
            }
        }
        return full
    }

    // key of the graph (and sample size) the result/the running request is for
    let request_key: string | null = null
    let controller: AbortController | null = null
    let timer: ReturnType<typeof setTimeout> | null = null

    const run = async (force = false) => {
        const store = graphSource()
        if (store && store.state != RepositoryState.STABLE) {
            // the deep watch fires again once the edit is done
            return
        }
        const graph = toQueryGraph(store, { payloads: false })
        const body = request(graph)
        const key = `${graphKey(graph)}#${JSON.stringify({ ...body, graph: null })}`
        if (!force && key == request_key) {
            return
        }
        request_key = key
        controller?.abort()
        const own = controller = new AbortController()
        state.status = 'loading'
        state.error = null
        // the previous result stays until the first update of this request
        let first = true
        const show = (result: ProgressiveResult) => {
            if (own.signal.aborted) {
                return
            }
            state.result = result
            if (first) {
                first = false
                state.scrub_count = null
                state.selected_id = null
            }
        }
        try {
            // counts stream in: placeholders (pending) are filled while the status is loading
            const result = await source.fetch(body, own.signal, show)
            if (own.signal.aborted) {
                return
            }
            show(result)
            state.status = 'ready'
        } catch (e) {
            if (own.signal.aborted) {
                return
            }
            console.warn('Progressive discovery failed', e)
            state.status = 'error'
            state.error = e instanceof Error ? e.message : String(e)
            // allow a retry of the same graph
            request_key = null
        }
    }
    const schedule = () => {
        if (timer) {
            clearTimeout(timer)
        }
        timer = setTimeout(() => {
            timer = null
            run()
        }, debounce_ms)
    }

    /** a sample size of at least ``min``, null (all candidates) for null or an empty input (NaN) */
    const optionalSize = (size: number | null | undefined, min: number) =>
        size == null || !Number.isFinite(size) ? null : Math.max(min, Math.round(size))
    /** sets the links to sample and count, null (or NaN, an empty input) for all of them */
    const setSampleSize = (size: number | null) => {
        state.sample_size = optionalSize(size, 1)
    }
    /** updates constraint settings; sizes at least 0/1 (null: all), percentiles kept within 0-100 and sorted */
    const setConstraints = (settings: Partial<ConstraintSettings>) => {
        const next = { ...state.constraints, ...settings }
        next.constraint_sample_size = optionalSize(next.constraint_sample_size, 0)
        next.categorical_samples = optionalSize(next.categorical_samples, 1)
        next.numeric_percentiles = [...new Set(next.numeric_percentiles
            .filter((p) => Number.isFinite(p) && p >= 0 && p <= 100))].sort((a, b) => a - b)
        state.constraints = next
    }
    /** updates the tree settings; depth within 1..max_depth, branching at least 1 (and capped),
     * links per node at least 1 (null: all) */
    const setTree = (settings: Partial<DepthSettings>) => {
        const next = { ...state.tree, ...settings }
        const clamp = (value: number, max: number | null) => Math.max(1, Math.min(Math.round(value) || 1, max ?? Infinity))
        next.depth = clamp(next.depth, state.max_depth)
        next.branching = clamp(next.branching, state.max_branching)
        next.child_sample_size = optionalSize(next.child_sample_size, 1)
        state.tree = next
    }
    // the defaults of the active configuration (sizes null: every candidate is counted)
    OntoConfig.ensureConfig().then(({ config }) => {
        const progressive = config.progressive
        setSampleSize(options.sample_size !== undefined ? options.sample_size : progressive.default_sample_size)
        if (progressive.numeric_percentiles) {
            setConstraints({
                sample_constraints: progressive.sample_constraints,
                constraint_sample_size: progressive.constraint_sample_size,
                numeric_percentiles: progressive.numeric_percentiles,
                categorical_samples: progressive.categorical_samples,
            })
        }
        if (progressive.max_depth) {
            state.max_depth = progressive.max_depth
            state.max_branching = progressive.max_branching
            setTree({ branching: progressive.default_branching, child_sample_size: progressive.child_sample_size })
        }
    }).catch((e) => console.warn('Progressive discovery: no configuration limits', e))

    watch(graphSource, schedule, { deep: true, immediate: true })
    watch(() => state.sample_size, schedule)
    watch(() => state.constraints, schedule)
    watch(() => state.tree, schedule)
    onBeforeUnmount(() => {
        if (timer) {
            clearTimeout(timer)
        }
        controller?.abort()
    })

    const modifications = computed(() => state.result?.modifications ?? [])
    const base_count = computed(() => state.result?.base_count ?? null)
    const extent = computed(() => countExtent(modifications.value, base_count.value))
    const bins = computed(() => histogramBins(modifications.value, extent.value, state.bin_count))
    /** the scrubbed count, defaulting to the base count (or the median of an empty graph's starts) */
    const scrub_count = computed(() => state.scrub_count ?? base_count.value ?? medianCount(modifications.value) ?? 0)
    const nearest = computed(() => nearestModifications(modifications.value, scrub_count.value, state.nearest))
    const nearest_ids = computed(() => new Set(nearest.value.map((m) => m.id)))
    const by_id = computed(() => modificationsById(modifications.value))
    const tree = computed(() => buildTree(modifications.value))
    const selected = computed(() => state.selected_id != null ? by_id.value.get(state.selected_id) ?? null : null)

    /** the change of a modification (its cumulative operations) against the editor graph */
    const changeOf = (modification: ProgressiveModification) =>
        operationsToChange(modification.operations, toQueryGraph(graphSource(), { payloads: false }))
    /** the steps leading to a modification, without itself (empty on the first level) */
    const pathOf = (modification: ProgressiveModification) => modificationPath(modification, by_id.value).slice(0, -1)

    /** the nearest modifications with their GraphChange against the editor graph (preview and
     * apply) and the steps before them */
    const nearest_changes = computed(() => {
        const graph = toQueryGraph(graphSource(), { payloads: false })
        return nearest.value.map((modification) => ({
            modification, path: pathOf(modification), ...operationsToChange(modification.operations, graph),
        }))
    })

    /** selects a modification (null to clear): scrubs to its count, so it is among the nearest */
    const select = (id: string | null) => {
        state.selected_id = id
        const count = id != null ? by_id.value.get(id)?.count : null
        if (count != null) {
            state.scrub_count = count
        }
    }

    return {
        state, source, modifications, base_count, extent, bins, scrub_count, nearest, nearest_ids,
        nearest_changes, by_id, tree, selected,
        changeOf, pathOf,
        ancestorsOf: (id: string) => ancestorIds(id, by_id.value),
        refresh: () => run(true),
        setScrub: (count: number | null) => { state.scrub_count = count },
        select,
        setSampleSize,
        setConstraints,
        setTree,
    }
}

export type ProgressiveState = ReturnType<typeof useProgressive>
