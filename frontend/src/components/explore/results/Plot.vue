<template>
    <div class="result_plot_wrapper" ref="plot_container">
        <div v-if="!ui_data.loading" class="result_plot_container" >
            <VuePlotly :data="chart_data" :layout="chart_options" :config="{
                displayModeBar: false,
            }"></VuePlotly>
            <OnsetBtn @click="initDownloadData" :toggleable="false" size="small" icon="mdi-download">Download Data
            </OnsetBtn>
        </div>
        <div v-if="ui_data.message" class="message">{{ ui_data.message }}</div>
        <Loading v-if="ui_data.loading"></Loading>
    </div>
</template>
<script setup lang="ts">
import { ref, onMounted, defineProps, watch, computed, reactive } from 'vue'
import { Bar } from 'vue-chartjs'
import type { NodeLinkRepository } from '@/utils/sparql/store';
import { QueryProp, SubQueryType } from '@/utils/sparql/representation';
import Loading from '../../ui/Loading.vue';

import * as Plotly from "plotly.js-dist";
import { VuePlotly } from '@clalarco/vue3-plotly';
import type { NodeLinkRepositoryDiff } from '@/utils/sparql/diff';
import { ChartMode, PropSpecificType, PropType } from '@/utils/result-plot/plot-types';
import { bucketizeData, analyzeProps, buildChartTraces, combineTraces, downloadDataAsCSV, propColumn, tensorProps, type TraceData } from '@/utils/result-plot/plot-builder';
import { buildEmbeddingDiffTraces } from '@/utils/result-plot/plot-embedding-builder';
import { PlotCache, PlotCacheEntry } from '@/utils/result-plot/plot-cache';
import { jsonClone } from '@/utils/parsing';
import OnsetBtn from '@/components/ui/OnsetBtn.vue';
import { api } from '@/utils/api'

const { store, query_string, diff, refresh } = defineProps({
    store: {
        type: Object as () => NodeLinkRepository,
        required: true
    },
    query_string: {
        type: String,
        required: true
    },
    diff: {
        type: Object as () => NodeLinkRepositoryDiff | null,
        default: null
    },
    refresh: {
        type: Number,
        default: 0
    }
})
const plot_container = ref<HTMLDivElement | null>(null)
const chart_mode = ref(ChartMode.BAR)
const result_set = ref([] as Record<string, any>[])
const chart_data = ref<TraceData[]>([] as TraceData[])
const chart_options = ref({
    bargap: 0.05,
    bargroupgap: 0.2,
    title: {
        text: ""
    },
    xaxis: {
        title: {
            text: "Value"
        }
    },
    yaxis: {
        title: {
            text: "Count"
        }
    },
    dragmode: false,
    hovermode: 'closest'
} as Plotly.Layout)

const diff_options = reactive({
    plot_cache: new PlotCache(),
})
const ui_data = reactive({
    chart_mode: ChartMode.BAR,
    loading: false,
    message: null as string | null,
    buckets: 20
})
/**
 * Rows of the current query and, in a difference view, of the previous one. With tensor
 * properties both queries are reduced to 2D in one fit (dim-reduce with `compare`), so the
 * previous points are recomputed together with the current ones and lie in the same space.
 */
const fetchRows = async (query_limitless: string) => {
    const vector_props = tensorProps(store)
    if (vector_props.length == 0) {
        const data = await api.sparql.sparqlQuerySparqlPost({ query: query_limitless })
        return { current: data.data as Record<string, any>[], previous: null as Record<string, any>[] | null }
    }
    const request = { query: query_limitless, target_properties: vector_props.map(propColumn) }
    const previous_props = diff ? tensorProps(diff.left) : []
    if (diff && previous_props.length > 0) {
        try {
            const data = await api.search.dimReduceSearchDimReducePost({
                ...request,
                compare: [{
                    query: diff.left.generateQuery(null, null, false),
                    target_properties: previous_props.map(propColumn),
                }],
            })
            const rows = data.data as Record<string, any>[]
            return {
                current: rows.filter((r) => r.query_index == 0),
                previous: rows.filter((r) => r.query_index == 1),
            }
        } catch (e) {
            // e.g. tensors of different sizes: only the current query
            console.error('Joint dimensionality reduction failed', e)
        }
    }
    const data = await api.search.dimReduceSearchDimReducePost(request)
    return { current: data.data as Record<string, any>[], previous: null as Record<string, any>[] | null }
}
const loadData = async () => {
    ui_data.loading = true
    let query_limitless = store.generateQuery(null, null, false);
    ui_data.message = "Loading data..."
    const rows = await fetchRows(query_limitless)
    const tensor_ids = new Set(tensorProps(store).map((p) => p.id))
    result_set.value = rows.current
    let props_of_interest = store.nodes
        .map((node) => node.subqueries
            .filter((subquery) => subquery.constraint_type == SubQueryType.QUERY_PROP))
        .flat() as QueryProp[]
    let analyzed_props = props_of_interest.map(p => analyzeProps(p, result_set.value, tensor_ids.has(p.id)))
    console.log('Analyzed props', analyzed_props, result_set.value)
    try {
        let {
            chart_mode: mode,
            chart_options: options,
            trace
        } = buildChartTraces(analyzed_props, result_set.value, query_limitless, store)
        console.log('Chart mode', mode, 'Chart options', options, 'Trace', trace)

        const rect = plot_container.value?.getBoundingClientRect()
        if (rect) {
            options.width = rect.width - 20
            options.height = rect.height - 128
            console.log('Plot container rect', rect, 'Setting chart options width and height to', options.width, options.height)
        } else {
            options.width = 800
            options.height = 600
        }
        ui_data.chart_mode = mode
        chart_options.value = options as Plotly.Layout
        chart_data.value = [trace]
        ui_data.message = ""
        console.log("setting cache for", query_limitless)
        let new_cache_entry = {
            results: rows.current,
            chart_mode: mode,
            chart_options: options,
            traces: [trace],
            store: jsonClone(store),
            analyzed_props
        }
        diff_options.plot_cache.set(query_limitless, new_cache_entry)
        if (diff && mode == ChartMode.DIM_REDUCED) {
            // the previous coordinates are only comparable from the joint reduction, not from the cache
            if (rows.previous) {
                const combined = buildEmbeddingDiffTraces(analyzed_props, rows.previous, rows.current, options as Plotly.Layout)
                chart_data.value = combined.traces
                chart_options.value = combined.chart_options
                ui_data.message = null
            } else {
                ui_data.message = "The previous query has no comparable tensors, no diff added..."
            }
        } else if (diff) {
            let old_query = diff.left.generateQuery(null, null, false)
            console.log('Diff enabled, loading cache for', old_query)
            let cache_result = diff_options.plot_cache.get(old_query)
            if (cache_result) {
                console.log('Diff enabled, found cache results', cache_result)
                if (cache_result.chart_mode != mode) {
                    console.log('Chart mode mismatch', cache_result.chart_mode, mode)
                    ui_data.message = "Chart mode mismatch, no diff added..."
                } else {
                    let combined_traces = combineTraces([cache_result, new_cache_entry])
                    console.log('Combined traces', combined_traces)
                    let cached_trace = combined_traces.traces[0]
                    let new_trace = combined_traces.traces[1]
                    new_trace.name = "Current"
                    if ((new_trace as Plotly.ScatterData).marker) {
                        (new_trace as Plotly.ScatterData).marker.opacity = 0.5
                    }
                    cached_trace.name = "Previous"
                    if ((cached_trace as Plotly.ScatterData).marker) {
                        (cached_trace as Plotly.ScatterData).marker.color = "red";
                        (cached_trace as Plotly.ScatterData).marker.opacity = 0.5
                    }
                    chart_data.value = [cached_trace, new_trace]
                    chart_options.value = combined_traces.chart_options
                    ui_data.chart_mode = combined_traces.chart_mode
                    ui_data.message = null
                }
            } else {
                ui_data.message = "No diff data found for this query"
            }
        }
    } catch (error) {
        console.error('Error analyzing props', error)
        ui_data.message = error.message
    }
    ui_data.loading = false
}
const initDownloadData = () => {
    let cache_result = diff_options.plot_cache.get(store.generateQuery(null, null, false))
    if (cache_result) {
        let old_cache_result = null
        if (diff) {
            old_cache_result = diff_options.plot_cache.get(diff.left.generateQuery(null, null, false))
        }
        downloadDataAsCSV(cache_result, old_cache_result)
    }
}

onMounted(() => {
    loadData().catch((e) => {
        console.error(e)
        ui_data.message = "Error loading data: " + e.message
        ui_data.loading = false
    })
})
watch(() => [query_string, refresh], () => {
    loadData().catch((e) => {
        console.error(e)
        ui_data.message = "Error loading data: " + e.message
        ui_data.loading = false
    })
})
watch(() => diff, () => {
    if (!diff && ui_data.chart_mode == ChartMode.DIM_REDUCED && chart_data.value.length > 1) {
        // back to the current query's trace, coloured by its property again
        const entry = diff_options.plot_cache.get(store.generateQuery(null, null, false))
        if (entry) {
            chart_data.value = [...entry.traces]
            chart_options.value = entry.chart_options
            return
        }
    }
    if (!diff && chart_data.value.length > 1) {
        chart_data.value.splice(0, chart_data.value.length - 1)
        let current_trace = chart_data.value[0] as TraceData
        current_trace.name = "Current"
        if ((current_trace as Plotly.ScatterData).marker) {
            (current_trace as Plotly.ScatterData).opacity = 1
        }
    }

}, { immediate: true })

</script>
<style lang="scss" scoped>
.result_plot_wrapper {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    width: 100%;
}

.result_plot_container {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-1);
    max-width: 100%;
    height: 100%;
}
</style>