<template>
    <div class="result_plot_wrapper">
        <div v-if="!ui_data.loading" class="result_plot_container">
            <VuePlotly :data="chart_data" :layout="chart_options" :config="{
                displayModeBar: false,
            }"></VuePlotly>
            <div class="spacer"></div>
            <OnsetBtn @click="initDownloadData" :toggleable="false">Download Data</OnsetBtn>
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
import { bucketizeData, analyzeProps, buildChartTraces, combineTraces, downloadDataAsCSV } from '@/utils/result-plot/plot-builder';
import { PlotCache, PlotCacheEntry } from '@/utils/result-plot/plot-cache';
import { jsonClone } from '@/utils/parsing';
import OnsetBtn from '@/components/ui/OnsetBtn.vue';
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
        ui_data.message = ""
        console.log("setting cache for", query_limitless)
        let new_cache_entry = {
            results: data.data,
            chart_mode: mode,
            chart_options: options,
            traces: [trace],
            store: jsonClone(store),
            analyzed_props
        }
        diff_options.plot_cache.set(query_limitless, new_cache_entry)
        if (diff) {
            let old_query = diff.left.generateQuery(null, null)
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
                    if (new_trace.marker) {
                        new_trace.marker.opacity = 0.5
                    }
                    cached_trace.name = "Previous"
                    if (cached_trace.marker) {
                        cached_trace.marker.color = "red"
                        cached_trace.marker.opacity = 0.5
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
    let cache_result = diff_options.plot_cache.get(store.generateQuery(null, null))
    if (cache_result) {
        let old_cache_result = null
        if (diff) {
            old_cache_result = diff_options.plot_cache.get(diff.left.generateQuery(null, null))
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
watch(() => query_string, () => {
    loadData().catch((e) => {
        console.error(e)
        ui_data.message = "Error loading data: " + e.message
        ui_data.loading = false
    })
})
watch(() => diff, () => {
    if (!diff && chart_data.value.length > 1) {
        chart_data.value.splice(0, chart_data.value.length - 1)
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
.spacer{
    margin: 10px;
}
</style>