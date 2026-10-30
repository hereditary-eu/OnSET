// State of the progressive panel: re-runs the source (debounced) when the editor graph
// changes, and derives the histogram and the modifications nearest to the scrubbed count.
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
import type { ProgressiveResult } from './types'

export type ProgressiveStatus = 'idle' | 'loading' | 'ready' | 'error'

export interface ProgressiveOptions {
    source?: ProgressiveSource
    /** initial sample size, by default the configuration's (GET /ontology/config) */
    sample_size?: number
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
        sample_size: options.sample_size ?? 48,
        /** cap of the sample size of the active configuration, null until it is loaded */
        max_sample_size: null as number | null,
        nearest: options.nearest ?? 10,
        bin_count: options.bin_count ?? 24,
        /** row count selected by the scrubber, null to follow the base count */
        scrub_count: null as number | null,
    })

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
        const key = `${graphKey(graph)}#${state.sample_size}`
        if (!force && key == request_key) {
            return
        }
        request_key = key
        controller?.abort()
        const own = controller = new AbortController()
        state.status = 'loading'
        state.error = null
        try {
            const result = await source.fetch({ graph, sample_size: state.sample_size }, own.signal)
            if (own.signal.aborted) {
                return
            }
            state.result = result
            state.status = 'ready'
            state.scrub_count = null
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

    const setSampleSize = (size: number) => {
        if (!Number.isFinite(size)) {
            return
        }
        const max = state.max_sample_size ?? Infinity
        state.sample_size = Math.max(1, Math.min(Math.round(size), max))
    }
    // the backend caps larger sizes anyway, clamping shows the cap
    OntoConfig.ensureConfig().then(({ config }) => {
        state.max_sample_size = config.progressive.max_sample_size
        setSampleSize(options.sample_size ?? config.progressive.default_sample_size)
    }).catch((e) => console.warn('Progressive discovery: no configuration limits', e))

    watch(graphSource, schedule, { deep: true, immediate: true })
    watch(() => state.sample_size, schedule)
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

    /** the nearest modifications with their GraphChange against the editor graph (preview and apply) */
    const nearest_changes = computed(() => {
        const graph = toQueryGraph(graphSource(), { payloads: false })
        return nearest.value.map((modification) => ({ modification, ...operationsToChange(modification.operations, graph) }))
    })

    return {
        state, source, modifications, base_count, extent, bins, scrub_count, nearest, nearest_ids,
        nearest_changes,
        refresh: () => run(true),
        setScrub: (count: number | null) => { state.scrub_count = count },
        setSampleSize,
    }
}

export type ProgressiveState = ReturnType<typeof useProgressive>
