<template>

    <div>
        <div class="mode_selector input_step">
            <h3>Mode</h3>
            <SelectorGroup v-model="ui_state.query_mode" :options="Object.keys(QueryMode).map(qm => {
                return { value: QueryMode[qm], label: QueryMode[qm] }
            })"></SelectorGroup>
        </div>
        <div v-if="ui_state.query_mode == QueryMode.TOPICS">
            <div class="input_step">
                <h3>Select one or more topics...</h3>
                <TopicSelector v-model="selected_topic_ids"></TopicSelector>
            </div>

            <div class="input_step">
                <h3>...pick a relation to start with...</h3>
                <NodeLinkSelector :query="{ topic_ids: selected_topic_ids }" @select="selected_root"></NodeLinkSelector>
            </div>
        </div>
        <div v-else>
            <div class="input_step">
                <FuzzyQueryStarter @query_complete="selected_root"></FuzzyQueryStarter>
            </div>
        </div>
        <div class="input_step">
            <h3 v-if="store">.. and start querying!</h3>
            <div class="query_build_view">
                <div class="show_history_btn">
                    <OnsetBtn @click="ui_state.show_history = !ui_state.show_history">{{ !ui_state.show_history ?
                        "Show" : "Hide" }} History
                    </OnsetBtn>
                </div>
                <div class="history_view_container" v-show="ui_state.show_history">
                    <HistoryView v-show="ui_state.show_history" :history='(ui_state.history as QueryHistory)'
                        @compare="compareToCurrent" @revert="revertToEntry" @show-tooltip="showTooltip"></HistoryView>

                    <div ref="tooltip_div">
                        <div v-if="ui_state.history_interactive.tooltip.visible" class="history_tooltip"
                            @mouseleave="ui_state.history_interactive.tooltip.visible = false"
                            :style="`top: ${ui_state.history_interactive.tooltip.position.y}px; left: ${ui_state.history_interactive.tooltip.position.x}px;`">
                            <HistoryElement :entry='(ui_state.history_interactive.tooltip.entry as HistoryEntry)'
                                @compare="compareToCurrent" @revert="revertToEntry">

                            </HistoryElement>
                        </div>
                    </div>
                </div>
                <div ref="graph_view" class="query_builder_wrapper">
                    <QueryBuilder :store="store" :diff="ui_state.diff" :simulate="ui_state.simulate">
                    </QueryBuilder>
                </div>
                <ResultsView :query_string="query_string" :store="store" :diff="ui_state.diff"></ResultsView>
            </div>
            <div class="diff_controls">
                <OnsetBtn @click="saveState()" :height="'2.8rem'" :width="'3rem'" :toggleable="false">Save
                </OnsetBtn>
                <OnsetBtn @click="loadState()" :height="'2.8rem'" :width="'3rem'" :toggleable="false">Load
                </OnsetBtn>
                <OnsetBtn @click="clearState()" :height="'2.8rem'" :width="'3rem'" :toggleable="false">Clear
                </OnsetBtn>
                <div class="vertical_line">

                </div>
                <OnsetBtn :toggleable="false" @click="ui_state.diff_active = !ui_state.diff_active">{{
                    !ui_state.diff_active ? "Start Change Tracking" :
                        "Apply Changes" }} </OnsetBtn>
                <OnsetBtn @click="clearDiff()" v-if="ui_state.diff_active">Clear Changes</OnsetBtn>
                <div class="vertical_line">

                </div>
                <input type="text" v-model="assistant_state.query_string" placeholder="Tell me what to change ..."
                    class="query_input" />
                <Loading v-if="assistant_state.loading" :height="'2.8rem'" :width="'3rem'"></Loading>
                <OnsetBtn @click="submit_assistant()" :toggleable="false" btn_width="4rem">Start</OnsetBtn>
            </div>
        </div>
        <div>
            <OnsetBtn @click="ui_state.show_query = !ui_state.show_query">{{ !ui_state.show_query ? "Show" : "Hide" }}
                Query
            </OnsetBtn>
            <pre v-if="ui_state.show_query" v-html="query_string_html" />
        </div>
        <div class="diff_controls">

            <OnsetBtn @click="ui_state.colour_blind = !ui_state.colour_blind">
                <v-icon icon="mdi-eye-off" /> Red-Green Colourblindness Mode
            </OnsetBtn>
            <OnsetBtn @click="downloadState()" :toggleable="false">Download Query History
            </OnsetBtn>
            <OnsetBtn @click="loadStateFromFile" :toggleable="false">Load Query History
            </OnsetBtn>
            <input type="file" ref="state_file" />
        </div>
    </div>
</template>
<script setup lang="ts">
import Prism from 'prismjs';
import 'prismjs/themes/prism.css';
import { ref, watch, reactive, computed, onMounted, onBeforeMount, h } from 'vue'
import TopicSelector from '@/components/explore/TopicSelector.vue';
import NodeLinkSelector from '@/components/explore/NodeLinkSelector.vue';
import QueryBuilder from '@/components/explore/QueryBuilder.vue';
import ResultsView from '@/components/explore/ResultsView.vue';
import Loading from '@/components/ui/Loading.vue';
import { OverviewCircles } from '@/utils/three-man/OverviewCircles';
import { Api, OperationType, type AssistantLink, type AssistantSubjectInput } from '@/api/client.ts/Api';
import { BACKEND_URL } from '@/utils/config';
import type { SubjectInCircle } from '@/utils/d3-man/CircleMan';
import OnsetBtn from '@/components/ui/OnsetBtn.vue';
import { NodeLinkRepository, RepositoryState, type MixedResponse } from '@/utils/sparql/store';
import SelectorGroup from '@/components/ui/SelectorGroup.vue';
import FuzzyQueryStarter from '@/components/explore/FuzzyQueryStarter.vue';
import { jsonClone, parseJSON, stringifyJSON } from '@/utils/parsing';
import { NodeLinkRepositoryDiff } from '@/utils/sparql/diff';
import { Link, SubjectNode } from '@/utils/sparql/representation';
import HistoryView from '@/components/explore/history/HistoryView.vue';
import { HistoryEntry, QueryHistory } from '@/utils/sparql/history';
import type { Vector2 } from 'three';
import type { HistoryTooltipEvent } from '@/utils/sparql/helpers';
import HistoryElement from '@/components/explore/history/HistoryElement.vue';


const api = new Api({
    baseURL: BACKEND_URL
})

// window.Prism = window.Prism || {};
// window.Prism.manual = true;
// loadLanguages(['sparql']);

const graph_view = ref<HTMLElement | null>(null)
const state_file = ref<HTMLInputElement | null>(null)

const selected_topic_ids = ref([] as number[])
const query_string_html = ref('')
const query_string = ref('')
const selected_start = ref(null as MixedResponse | null)
enum QueryMode {
    FUZZY = 'Fuzzy',
    TOPICS = 'Topics',
}
const assistant_state = reactive({
    query_string: '',
    loading: false,
})
const ui_state = reactive({
    loading: false,
    show_query: false,
    query_mode: QueryMode.FUZZY,
    diff: null as NodeLinkRepositoryDiff | null,
    diff_active: false,
    colour_blind: false,
    show_history: false,
    history: new QueryHistory(),
    simulate: false,
    history_interactive: {
        tooltip: {
            visible: false,
            position: { x: 0, y: 0 },
            entry: null as HistoryEntry | null,
        }
    }
})
const store = ref(null as NodeLinkRepository | null)
const old_store = ref(null as NodeLinkRepository | null)

watch(() => selected_topic_ids, () => {
    console.log('selected_topic_ids changed!', selected_topic_ids.value)
}, { deep: true })
watch(() => selected_start, () => {
    if (!selected_start.value) {
        return
    } else {

        // console.log('selected_root', root)
        const target_size = graph_view.value ? {
            x: graph_view.value.clientWidth,
            y: graph_view.value.clientHeight
        } : { x: 1000, y: 500 }
        console.log('target_size', target_size, graph_view.value)
        // circular placement using indices
        for (let i = 0; i < selected_start.value.store.nodes.length; i++) {
            const angle = (i / selected_start.value.store.nodes.length) * Math.PI * 2
            selected_start.value.store.nodes[i].x = target_size.x / 2 + Math.cos(angle) * (target_size.x / 4)
            selected_start.value.store.nodes[i].y = target_size.y / 2 + Math.sin(angle) * (target_size.y / 4)
        }

        store.value = jsonClone(selected_start.value.store)
    }
}, { deep: true })
watch(() => store, () => {
    if (!store.value || store.value.state != RepositoryState.STABLE) {
        return
    }
    let new_query_string = store.value.generateQuery()
    if (query_string.value != new_query_string) {
        if (ui_state.history && store.value) {
            console.log('Adding history entry', ui_state.history, store.value)
            ui_state.history.tryAddEntry(store.value)
        }
        updateDiff()
        query_string.value = new_query_string
        query_string_html.value = Prism.highlight(
            query_string.value,
            Prism.languages.sparql, 'sparql');
        // query_string.value = selected_start.value.link.from_subject.generateQuery()
    }
}, { deep: true })

const selected_root = (root: MixedResponse) => {
    selected_start.value = root
}
watch(() => ui_state.diff_active, (new_val) => {
    if (ui_state.diff_active) {
        if (!old_store.value) {
            console.log('Starting diff based on watcher')
            startDiff()
        }
    } else {
        console.log('Applying diff')
        ui_state.diff_active = false
        old_store.value = null
        ui_state.diff = null
    }
}, { deep: false })
const startDiff = () => {
    console.log('Starting diff')
    old_store.value = jsonClone(store.value)
    updateDiff()
}
const updateDiff = () => {
    if (ui_state.diff_active && old_store.value) {
        console.log('Updating diff')
        ui_state.diff = new NodeLinkRepositoryDiff(old_store.value, store.value)
    }
}
const clearDiff = () => {
    ui_state.diff_active = false
    store.value = old_store.value
    old_store.value = null
    ui_state.diff = null
}

const compareToCurrent = (entry: HistoryEntry) => {
    if (!entry.query || !store.value) {
        return
    }
    ui_state.diff_active = true
    ui_state.diff = new NodeLinkRepositoryDiff(entry.query, store.value)
}
const revertToEntry = (entry: HistoryEntry) => {
    if (!entry.query || !store.value) {
        return
    }
    ui_state.diff_active = false
    ui_state.simulate = false
    store.value = jsonClone(entry.query)
    old_store.value = null
    ui_state.diff = null
    ui_state.simulate = true
}

const submit_assistant = () => {
    if (assistant_state.query_string.length == 0) {
        return
    }
    console.log('Assistant query', assistant_state.query_string);

    (async () => {
        assistant_state.loading = true
        const graph = store.value.toQueryGraph()
        const response = await api.classes.getAssistantResultsClassesSearchAssistantPost(graph, {
            q: assistant_state.query_string,
        })
        assistant_state.loading = false
        if (!ui_state.diff_active) {
            ui_state.diff_active = true
            startDiff()
        }
        for (const step of response.data.operations) {
            if (step.operation == OperationType.Add) {
                switch (step.data.type) {
                    case 'subject':
                        const op_subject = step.data as AssistantSubjectInput
                        const full_subject = await api.classes.getSubjectClassesSubjectsGet({
                            subject_id: op_subject.subject_id
                        })
                        const subject = full_subject.data
                        const new_subject = new SubjectNode(subject)
                        new_subject.internal_id = op_subject.internal_id
                        console.log('new_subject', new_subject)
                        store.value.nodes.push(new_subject)
                        break
                }
            } else if (step.operation == OperationType.Remove) {
                switch (step.data.type) {
                    case 'subject':
                        const op_subject = step.data as AssistantSubjectInput
                        const subject = store.value.nodes.find((s) => s.id == op_subject.subject_id)
                        store.value.nodes.splice(store.value.nodes.indexOf(subject), 1)
                        break
                    case 'link':
                        const op_link = step.data as AssistantLink
                        const link = store.value.links.find((l) => l.id == op_link.link_id)
                        store.value.links.splice(store.value.links.indexOf(link), 1)
                        break
                }
            }
        }
        for (const step of response.data.operations) {
            if (step.operation == OperationType.Add) {
                switch (step.data.type) {
                    case 'link':
                        const op_link = step.data as AssistantLink
                        const full_link = await api.classes.getLinkClassesLinksGet({
                            link_id: op_link.link_id
                        })
                        const link = full_link.data
                        const new_link = new Link(link)
                        new_link.from_internal_id = op_link.from_internal_id
                        new_link.to_internal_id = op_link.to_internal_id
                        store.value.links.push(new_link)
                        store.value.to(new_link).x = store.value.from(new_link).x + store.value.from(new_link).width + 100
                        store.value.to(new_link).y = store.value.from(new_link).y
                        break
                }
            }
        }
        console.log('store after changes', store.value)
    })().catch(console.error)
}

const saveState = () => {
    if (!store.value) {
        return
    }
    const store_json = stringifyJSON(store.value)
    localStorage.setItem('store', store_json)
    localStorage.setItem('history', stringifyJSON(ui_state.history))
    console.log('Saved store and history to localStorage', store_json, ui_state.history)
}
const loadState = () => {
    const store_json = localStorage.getItem('store')
    const history_json = localStorage.getItem('history')
    if (history_json) {
        const history_obj = parseJSON<QueryHistory>(history_json)
        console.log('Loaded history', history_obj)
        ui_state.history = history_obj
    }
    if (store_json) {
        const store_obj = parseJSON<NodeLinkRepository>(store_json)
        store.value = store_obj
        console.log('Loaded store', store.value)
    } else if (ui_state.history?.entries.length > 0) {
        console.log('No store found in localStorage, but history exists.')
        store.value = jsonClone(ui_state.history.entries[ui_state.history.entries.length - 1].query)
    }
}
const clearState = () => {
    localStorage.removeItem('store')
    store.value = null
    old_store.value = null
    ui_state.diff = null
    ui_state.diff_active = false
    ui_state.history = new QueryHistory()

    console.log('Cleared store')
}

const downloadState = () => {
    if (!store.value) {
        return
    }
    const store_json = stringifyJSON(ui_state.history)
    const blob = new Blob([store_json], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'query_history.json'
    a.click()
    URL.revokeObjectURL(url)
    console.log('Downloaded store as JSON', store_json)
}
const loadStateFromFile = () => {
    const input = state_file.value
    if (!input || !input.files || input.files.length == 0) {
        return
    }
    const file = input.files[0]
    const reader = new FileReader()
    reader.onload = (e) => {
        const content = e.target?.result
        if (typeof content === 'string') {
            const hist_obj = parseJSON<QueryHistory>(content)
            ui_state.history = hist_obj
            store.value = jsonClone(ui_state.history.entries[ui_state.history.entries.length - 1].query)
            console.log('Loaded history from file', ui_state.history)
        }
    }
    reader.readAsText(file)
}

const colour_config = computed(() => {
    if (ui_state.colour_blind) {
        return {
            node_normal: '#ccc',
            node_added: 'rgb(51,114,237)',
            node_removed: 'rgb(248,212,150)',
            node_changed: 'rgb(232,224,253)',
            node_added_light: 'rgba(51,114,237,0.506)',
            node_removed_light: 'rgba(248,212,150,0.506)',

            link_normal: '#999',
            link_added: 'rgb(51,114,237)',
            link_removed: 'rgb(248,212,150)',
        }
    } else {
        return {
            node_normal: '#ccc',
            node_added: 'var(--vt-c-green-strong)',
            node_removed: '#f26c6c',
            node_changed: '#bbd8ff',
            node_added_light: 'rgba(228, 119, 119, 0.506)',
            node_removed_light: 'rgba(109, 209, 109, 0.506)',

            link_normal: '#999',
            link_added: 'var(--vt-c-green-strong)',
            link_removed: '#f26c6c',
        }
    }
})

function showTooltip(evt: HistoryTooltipEvent) {
    console.log("Showing History tooltip", evt)
    ui_state.history_interactive.tooltip.visible = true
    ui_state.history_interactive.tooltip.position.x = evt.position.x
    ui_state.history_interactive.tooltip.position.y = evt.position.y
    ui_state.history_interactive.tooltip.entry = evt.entry
}

onMounted(() => {
    loadState()
})
</script>
<style lang="scss" scoped>
.query_build_view {
    display: flex;
    position: relative;
    justify-content: center;
    align-items: start;
    flex-direction: row;
    width: 100%;
    //overflow: auto;
    height: 60vh;

    pre {
        width: 25%;
        height: 100%;
    }
}

.query_builder_wrapper {
    width: 80%;
    height: 95%;
}

.diff_controls {
    display: flex;
    justify-items: start;
    justify-items: start;
    align-items: center;
    flex-direction: row;
    margin: 20px;
}

.input_step {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    border-bottom: 1px solid #e0e0e0;
    margin: 0.5rem;
    padding: 0.5rem;
}

.mode_selector {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    border-bottom: 1px solid #e0e0e0;
}

.query_input {
    width: 20vw;
    height: 2.8rem;
    font-size: 1rem;
    padding: 0.5rem;
    margin: 0.5rem;
    border: 1px solid #8fa88f;
}

.vertical_line {
    width: 1px;
    height: 2.8rem;
    background-color: #8fa88f;
    margin: 0 10px;
}

.show_history_btn {
    position: absolute;
    display: inline-block;
    top: 10px;
    left: 10px;
    z-index: 50;
    display: flex;
    flex-direction: column;
    align-items: start;
    justify-content: start;
}

.history_view_container {
    position: absolute;
    display: inline-block;
    top: 4rem;
    left: 10px;
    z-index: 50;
    height: 100%;
    width: 80%;
    display: flex;
    flex-direction: column;
    align-items: start;
    justify-content: start;
}

:deep(.node_normal) {
    fill: v-bind('colour_config.node_normal');
}

:deep(.node_added) {
    fill: v-bind('colour_config.node_added');
    stroke-dasharray: 10, 2, 10, 2;
}

:deep(.node_removed) {
    fill: v-bind('colour_config.node_removed');
    stroke-dasharray: 10, 4, 10, 4;
}

:deep(.node_changed) {
    fill: v-bind('colour_config.node_changed');
    stroke-dasharray: 10, 1, 10, 1;
}

:deep(.node_attaching) {
    fill: v-bind('colour_config.node_normal');
    stroke-width: 3px;
    stroke-dasharray: 1, 1, 1, 1;
}

:deep(.result_instance_right) {
    background-color: v-bind('colour_config.node_added_light');
}

:deep(.result_instance_left) {
    background-color: v-bind('colour_config.node_removed_light');
}


:deep(.link_normal) {
    stroke: v-bind('colour_config.link_normal');
}

:deep(.link_added) {
    stroke: v-bind('colour_config.link_added');
    stroke-dasharray: 10, 2, 10, 2;
}

:deep(.link_removed) {
    stroke: v-bind('colour_config.link_removed');
    stroke-dasharray: 10, 4, 10, 4;
}
</style>