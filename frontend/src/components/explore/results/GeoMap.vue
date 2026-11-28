<template>
    <div class="geo_map_wrapper">
        <div class="geo_map_toolbar toolbar">
            <SelectorGroup v-model="ui_state.mode" :options="Object.values(GeoMapMode).map(m => ({ value: m, label: m }))">
            </SelectorGroup>
            <span class="geo_map_summary" v-if="!ui_state.loading">{{ summary }}</span>
        </div>
        <div class="geo_map_plot" ref="plot_el"></div>
        <div v-if="selected_details" class="geo_map_details">
            <div class="geo_map_details_header">
                <OnsetIcon icon="mdi-map-marker" />
                <a v-if="selected_details.href" :href="selected_details.href" target="_blank" rel="noopener"
                    class="geo_map_details_title">{{ selected_details.title }}</a>
                <span v-else class="geo_map_details_title">{{ selected_details.title }}</span>
                <span class="toolbar_spacer"></span>
                <OnsetBtn size="small" :toggleable="false" icon="mdi-close" title="Clear selection"
                    @click="ui_state.selected = null"></OnsetBtn>
            </div>
            <table class="geo_map_details_table">
                <tr v-for="entry of selected_details.entries" :key="entry.key">
                    <th>{{ entry.key }}</th>
                    <td>{{ entry.value }}</td>
                </tr>
            </table>
        </div>
        <div v-if="ui_state.message" class="message">{{ ui_state.message }}</div>
        <Loading v-if="ui_state.loading"></Loading>
    </div>
</template>
<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount, nextTick, shallowRef } from 'vue'
import * as PlotlyNS from 'plotly.js-dist'
import type { NodeLinkRepository } from '@/utils/sparql/store'
import { readableName } from '@/utils/sparql/querymapper'
import { api } from '@/utils/api'
import { detectGeoColumns, extractFeatures, fitView, geometryBounds, type GeoColumn, type GeoFeature, type GeoNodeInfo } from '@/utils/geo'
import { buildGeoTraces, geoNodesOf, GeoMapMode } from '@/utils/result-plot/geo-map'
import Loading from '../../ui/Loading.vue'
import OnsetBtn from '../../ui/OnsetBtn.vue'
import OnsetIcon from '../../ui/OnsetIcon.vue'
import SelectorGroup from '../../ui/SelectorGroup.vue'

// the bundle is CommonJS, so the module may arrive as its default export
const Plotly: any = (PlotlyNS as any).default ?? PlotlyNS
// rows fetched for the map (the result list pages through 50 at a time)
const MAX_ROWS = 5000

const { store, query_string, refresh } = defineProps({
    store: {
        type: Object as () => NodeLinkRepository,
        required: true
    },
    query_string: {
        type: String,
        required: true
    },
    refresh: {
        type: Number,
        default: 0
    }
})

const plot_el = ref<HTMLDivElement | null>(null)
const rows = shallowRef<Record<string, unknown>[]>([])
const nodes = shallowRef<GeoNodeInfo[]>([])
const columns = shallowRef<GeoColumn[]>([])
const features = shallowRef<GeoFeature[]>([])
const ui_state = reactive({
    mode: GeoMapMode.TILES as string,
    loading: false,
    message: null as string | null,
    selected: null as number | null,
    load_id: 0,
})

const summary = computed(() => {
    if (features.value.length == 0) {
        return ''
    }
    const instances = new Set(features.value.map(f => `${f.node_id}|${f.instance_id}`)).size
    const limited = rows.value.length >= MAX_ROWS ? ` (first ${MAX_ROWS} rows)` : ''
    return `${instances} instances with geometry · ${columns.value.map(c => c.label).join(', ')}${limited}`
})

// the selected instance and the values of its result row
const selected_details = computed(() => {
    const f = ui_state.selected !== null ? features.value[ui_state.selected] : null
    if (!f) {
        return null
    }
    const row = rows.value[f.row_index] || {}
    const bare = f.instance_id?.replace(/^<(.*)>$/, '$1') ?? null
    const entries: { key: string, value: string }[] = []
    for (const node of nodes.value) {
        const label = row[node.label_var ?? ''] ?? (row[node.instance_var] != null ? readableName(String(row[node.instance_var])) : null)
        if (node.id != f.node_id && label != null) {
            entries.push({ key: node.label, value: String(label) })
        }
        for (const p of node.props) {
            if (row[p.var] != null && row[p.var] !== '') {
                entries.push({ key: `${node.label} · ${p.label || readableName(p.property_id ?? p.var)}`, value: String(row[p.var]) })
            }
        }
    }
    const node = nodes.value.find(n => n.id == f.node_id)
    return {
        title: `${f.instance_label || readableName(f.instance_id ?? undefined)}${node ? ` (${node.label})` : ''}`,
        href: bare && /^https?:\/\//.test(bare) ? bare : null,
        entries,
    }
})

// map colours follow the app's surface colour (light unless a dark theme sets --c-surface)
const isDark = () => {
    const surface = getComputedStyle(document.documentElement).getPropertyValue('--c-surface').trim()
    const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(surface)
    if (!m) {
        return false
    }
    const [r, g, b] = m.slice(1).map(h => parseInt(h, 16))
    return 0.299 * r + 0.587 * g + 0.114 * b < 128
}

const render = async () => {
    await nextTick()
    const el = plot_el.value
    if (!el) {
        return
    }
    const dark = isDark()
    const rect = el.getBoundingClientRect()
    const view = fitView(geometryBounds(features.value), rect.width || 600, rect.height || 400)
    const text_color = getComputedStyle(document.documentElement).getPropertyValue('--color-text').trim() || '#2c3e50'
    const layout: Record<string, any> = {
        margin: { l: 0, r: 0, t: 0, b: 0 },
        paper_bgcolor: 'rgba(0,0,0,0)',
        font: { color: text_color },
        showlegend: true,
        legend: { x: 0.01, y: 0.99, bgcolor: dark ? 'rgba(30,30,30,0.8)' : 'rgba(255,255,255,0.8)' },
        hovermode: 'closest',
        // keep the user's pan/zoom while the selection changes; reset it for a new query
        uirevision: `${query_string}|${ui_state.mode}`,
    }
    if (ui_state.mode == GeoMapMode.TILES) {
        layout.map = {
            style: dark ? 'carto-darkmatter' : 'carto-positron',
            center: view.center,
            zoom: view.zoom,
        }
    } else {
        layout.geo = {
            projection: { type: 'natural earth' },
            showland: true,
            landcolor: dark ? '#2a2a2a' : '#eef0ec',
            showcountries: true,
            countrycolor: dark ? '#555' : '#c8c8c8',
            showocean: true,
            oceancolor: dark ? '#1a1d22' : '#f5f8fb',
            bgcolor: 'rgba(0,0,0,0)',
            fitbounds: features.value.length > 0 ? 'locations' : false,
        }
    }
    const traces = buildGeoTraces(features.value, nodes.value, ui_state.mode as GeoMapMode, ui_state.selected)
    await Plotly.react(el, traces, layout, { displayModeBar: false, responsive: true, scrollZoom: true })
    if (!(el as any).__geo_click_bound) {
        (el as any).__geo_click_bound = true;
        (el as any).on('plotly_click', (event: any) => {
            const point = event?.points?.[0]
            const index = point?.customdata?.[0]
            ui_state.selected = typeof index == 'number' ? index : null
        })
    }
}

const loadData = async () => {
    if (!store) {
        return
    }
    const load_id = ++ui_state.load_id
    ui_state.loading = true
    ui_state.message = null
    ui_state.selected = null
    try {
        const response = await api.sparql.sparqlQuerySparqlPost({ query: store.generateQuery(MAX_ROWS, null) })
        if (load_id != ui_state.load_id) {
            return
        }
        const query_nodes = geoNodesOf(store)
        const data = response.data as Record<string, unknown>[]
        const detected = detectGeoColumns(query_nodes, data)
        nodes.value = query_nodes
        rows.value = data
        columns.value = detected
        features.value = extractFeatures(query_nodes, detected, data)
        if (features.value.length == 0) {
            ui_state.message = 'No coordinates or geometries in the results.'
        }
        await render()
    } catch (e: any) {
        console.error('Error loading the map data', e)
        ui_state.message = 'Error loading data: ' + (e?.message ?? e)
    } finally {
        if (load_id == ui_state.load_id) {
            ui_state.loading = false
        }
    }
}

let resize_observer: ResizeObserver | null = null
onMounted(() => {
    loadData()
    if (plot_el.value && typeof ResizeObserver != 'undefined') {
        resize_observer = new ResizeObserver(() => {
            if (plot_el.value && (plot_el.value as any)._fullLayout) {
                Plotly.Plots.resize(plot_el.value)
            }
        })
        resize_observer.observe(plot_el.value)
    }
})
onBeforeUnmount(() => {
    resize_observer?.disconnect()
    if (plot_el.value) {
        Plotly.purge(plot_el.value)
    }
})
watch(() => [query_string, refresh], () => loadData())
watch(() => [ui_state.mode, ui_state.selected], () => render())
</script>
<style scoped>
.geo_map_wrapper {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    height: 100%;
    width: 100%;
    min-height: 20rem;
}

.geo_map_toolbar {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    flex: 0 0 auto;
}

.geo_map_summary {
    font-size: 0.8rem;
    opacity: 0.75;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.geo_map_plot {
    flex: 1 1 auto;
    min-height: 16rem;
    width: 100%;
    border: 1px solid var(--c-border);
    border-radius: 4px;
    overflow: hidden;
}

.geo_map_details {
    flex: 0 0 auto;
    max-height: 30%;
    overflow: auto;
    border: 1px solid var(--c-border);
    border-radius: 4px;
    background: var(--c-surface);
    padding: var(--space-1);
    font-size: 0.8rem;
}

.geo_map_details_header {
    display: flex;
    align-items: center;
    gap: var(--space-1);
}

.geo_map_details_title {
    font-weight: 600;
}

.geo_map_details_table th {
    text-align: left;
    padding-right: var(--space-2);
    font-weight: 500;
    opacity: 0.75;
    white-space: nowrap;
    vertical-align: top;
}

.geo_map_details_table td {
    word-break: break-all;
}

.geo_map_wrapper > .loading_wrapper,
.geo_map_wrapper > .message {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
}
</style>
