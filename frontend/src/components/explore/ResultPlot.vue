<template>
    <div class="result_plot_wrapper">
        <div v-if="!ui_data.loading" class="result_plot_container">
            <VuePlotly :data="chart_data" :layout="chart_options" :config="{
                displayModeBar: false,
            }"></VuePlotly>
        </div>
        <h3 v-if="ui_data.message">{{ ui_data.message }}</h3>
        <Loading v-if="ui_data.loading"></Loading>
    </div>
</template>
<script setup lang="ts">
import { ref, onMounted, defineProps, watch, computed, reactive } from 'vue'
import { Bar } from 'vue-chartjs'
import type { NodeLinkRepository } from '@/utils/sparql/store';
import { Api } from '@/api/client.ts/Api';
import { BACKEND_URL } from '@/utils/config';
import { QueryProp, SubQueryType } from '@/utils/sparql/representation';
import Loading from '../ui/Loading.vue';
import type * as  Plotly from 'plotly.js';
import { VuePlotly } from '@clalarco/vue3-plotly';
import type { NodeLinkRepositoryDiff } from '@/utils/sparql/diff';
import { ChartMode, PropSpecificType, PropType } from '@/utils/result-plot/plot-data';
import { aggregateData, analyzeProps, buildChartTraces } from '@/utils/result-plot/plot-builder';
import { PlotCache, PlotCacheEntry } from '@/utils/result-plot/plot-cache';
import { jsonClone } from '@/utils/parsing';
const api = new Api(
    {
        baseURL: BACKEND_URL
    }
)

const { store, query_string, diff } = defineProps({
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
    }
})
const chart_mode = ref(ChartMode.BAR)
const result_set = ref([] as Record<string, any>[])
const chart_data = ref([] as Plotly.Data[])
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
const addDiffData = (cache_result: PlotCacheEntry) => {
    if (cache_result.chart_mode != chart_mode.value) {
        ui_data.message = "Chart mode mismatch, no diff added..."
    }
    let cached_trace = cache_result.traces[0]
    let existing_trace = chart_data.value[0] as Plotly.PlotData
    existing_trace.name = "Current"
    if (existing_trace.marker) {
        existing_trace.marker.opacity = 0.5
    }
    cached_trace.name = "Previous"
    if (cached_trace.marker) {
        cached_trace.marker.color = "red"
        cached_trace.marker.opacity = 0.5
    }
    chart_data.value.push(cached_trace)
}
const loadData = async () => {
    ui_data.loading = true
    let query_limitless = store.generateQuery(null, null);
    let data = await api.sparql.sparqlQuerySparqlPost({
        query: query_limitless
    })
    result_set.value = data.data
    let props_of_interest = store.nodes
        .map((node) => node.subqueries
            .filter((subquery) => subquery.constraint_type == SubQueryType.QUERY_PROP))
        .flat() as QueryProp[]
    let analyzed_props = props_of_interest.map(p => analyzeProps(p, result_set.value))
    console.log('Analyzed props', analyzed_props, result_set.value)
    try {
        let {
            chart_mode: mode,
            chart_options: options,
            trace
        } = buildChartTraces(analyzed_props, result_set.value)
        console.log('Chart mode', mode, 'Chart options', options, 'Trace', trace)

        ui_data.chart_mode = mode
        chart_options.value = options
        chart_data.value = [trace]
        ui_data.message = null
        console.log("setting cache for", query_limitless)
        diff_options.plot_cache.set(query_limitless, {
            results: data.data,
            chart_mode: mode,
            chart_options: options,
            traces: [trace],
            store: jsonClone(store)
        })
    } catch (error) {
        console.error('Error analyzing props', error)
        ui_data.message = error.message
    }
    if (diff) {
        let old_query = diff.left.generateQuery(null, null)
        console.log('Diff enabled, loading cache for', old_query)
        let cache_result = diff_options.plot_cache.get(old_query)
        if (cache_result) {
            console.log('Diff enabled, found cache results', cache_result)
            addDiffData(cache_result)
        } else {
            ui_data.message = "No diff data found for this query"
        }
    }
    ui_data.loading = false
}
onMounted(() => {
    loadData().catch((e) => {
        console.error(e)
        ui_data.message = "Error loading data: " + e.message
        ui_data.loading = false
    })
})
watch(() => query_string, () => {
    loadData().catch((e) => {
        console.error(e)
        ui_data.message = "Error loading data: " + e.message
        ui_data.loading = false
    })
})
watch(() => diff, () => {
    if (!diff && chart_data.value.length > 1) {
        chart_data.value.splice(1, chart_data.value.length - 1)
        let current_trace = chart_data.value[0] as Plotly.PlotData
        current_trace.name = "Current"
        if (current_trace.marker) {
            current_trace.marker.opacity = 1
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
    width: 100%;
    height: 100%;
}
</style>