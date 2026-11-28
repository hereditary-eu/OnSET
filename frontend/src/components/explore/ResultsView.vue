<template>
    <section class="panel results_view">
        <header class="panel_header">
            <span class="panel_title">Results</span>
            <span class="toolbar_spacer"></span>
            <SelectorGroup v-model="ui_state.result_mode" :options="mode_options"></SelectorGroup>
        </header>
        <div class="panel_body">
            <ResultMinitatures v-if="ui_state.result_mode == ResultMode.MINI" :diff="diff" :store="store"
                :query_string="query_string" :refresh="refresh"></ResultMinitatures>
            <ResultGeoMap v-else-if="ui_state.result_mode == ResultMode.MAP" :store="store"
                :query_string="query_string" :refresh="refresh"></ResultGeoMap>
            <ResultPlot v-else :store="store" :query_string="query_string" :diff="diff" :refresh="refresh"></ResultPlot>
        </div>
    </section>
</template>
<script setup lang="ts">
import { watch, reactive, computed, onMounted } from 'vue'
import { SubQueryType } from '@/utils/sparql/representation';
import ResultPlot from './results/Plot.vue';
import ResultGeoMap from './results/GeoMap.vue';
import type { NodeLinkRepository } from '@/utils/sparql/store';
import SelectorGroup from '../ui/SelectorGroup.vue';
import type { NodeLinkRepositoryDiff } from '@/utils/sparql/diff';
import ResultMinitatures from './results/MinitatureList.vue';
import { detectGeoColumns } from '@/utils/geo';
import { geoNodesOf } from '@/utils/result-plot/geo-map';
import { api } from '@/utils/api';
enum ResultMode {
    MINI = 'Miniatures',
    PROP = 'Properties',
    MAP = 'Map',
}
// rows sampled to decide whether the results have coordinates/geometries
const GEO_SAMPLE_ROWS = 50
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
    // bump to run the query again (e.g. while the data changes)
    refresh: {
        type: Number,
        default: 0
    }
})
const ui_state = reactive({
    result_mode: ResultMode.MINI,
    // the map view is offered only when the results have geo columns
    geo_available: false,
    geo_check_id: 0,
})
const mode_options = computed(() => Object.values(ResultMode)
    .filter(mode => mode != ResultMode.MAP || ui_state.geo_available)
    .map(mode => ({ value: mode, label: mode })))

// samples the results and looks for WKT/GeoJSON literals or latitude/longitude pairs
const checkGeo = async () => {
    const check_id = ++ui_state.geo_check_id
    let available = false
    try {
        const nodes = store ? geoNodesOf(store) : []
        if (nodes.some(n => n.props.length > 0)) {
            const response = await api.sparql.sparqlQuerySparqlPost({ query: store.generateQuery(GEO_SAMPLE_ROWS, null) })
            available = detectGeoColumns(nodes, response.data as Record<string, unknown>[]).length > 0
        }
    } catch (e) {
        console.warn('Geo column check failed', e)
    }
    if (check_id != ui_state.geo_check_id) {
        return
    }
    ui_state.geo_available = available
    if (!available && ui_state.result_mode == ResultMode.MAP) {
        ui_state.result_mode = ResultMode.MINI
    }
}
onMounted(() => checkGeo())
watch(() => refresh, () => checkGeo())
watch(() => query_string, () => {
    if (!store) {
        return
    }
    checkGeo()
    if (ui_state.result_mode == ResultMode.MAP) {
        // stay on the map while the query is refined (checkGeo leaves it if the coordinates disappear)
        return
    }
    let query_props = store.nodes.flatMap(n => n.subqueries.filter(sq => sq.constraint_type == SubQueryType.QUERY_PROP))
    if (query_props.length > 0) {
        ui_state.result_mode = ResultMode.PROP
    } else {
        ui_state.result_mode = ResultMode.MINI
    }
}, { deep: true })
</script>
