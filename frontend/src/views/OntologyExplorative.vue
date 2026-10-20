<template>
    <div class="explore" :style="colour_vars">
        <div class="explore_main">
            <!-- (a) query graph editor -->
            <section class="panel explore_editor">
                <header class="panel_header">
                    <span class="panel_title">Query</span>
                    <OnsetBtn v-model="ui_state.show_examples" size="small" icon="mdi-lightbulb-outline"
                        title="Start from an example query">Examples</OnsetBtn>
                    <OnsetBtn v-model="ui_state.show_history" size="small" icon="mdi-history">History</OnsetBtn>
                    <OnsetBtn v-model="ui_state.show_query" size="small" icon="mdi-code-braces">SPARQL</OnsetBtn>
                    <span class="vsep"></span>
                    <!-- change tracking: highlights changes (incl. the agent's) against the state it started from -->
                    <OnsetBtn size="small" :toggleable="false" icon="mdi-source-branch"
                        :class="{ onset_btn_selected: ui_state.diff_active }"
                        :title="ui_state.diff_active ? 'Accept the tracked changes' : 'Highlight changes from now on'"
                        @click="ui_state.diff_active = !ui_state.diff_active">
                        {{ ui_state.diff_active ? "Apply Changes" : "Track Changes" }}
                    </OnsetBtn>
                    <OnsetBtn v-if="ui_state.diff_active" size="small" :toggleable="false" icon="mdi-close"
                        title="Revert to the state the tracking started from" @click="clearDiff()">Discard</OnsetBtn>
                    <span class="toolbar_spacer"></span>
                    <OnsetBtn @click="saveState()" size="small" :toggleable="false" icon="mdi-content-save"
                        title="Save query and history in the browser">Save</OnsetBtn>
                    <OnsetBtn @click="loadState()" size="small" :toggleable="false" icon="mdi-folder-open"
                        title="Load the saved query and history">Load</OnsetBtn>
                    <OnsetBtn @click="clearState()" size="small" :toggleable="false" icon="mdi-delete-outline"
                        title="Clear the query and history">Clear</OnsetBtn>
                    <span class="vsep"></span>
                    <OnsetBtn @click="downloadState()" size="small" :toggleable="false" icon="mdi-download"
                        title="Download the query history as JSON" />
                    <OnsetBtn @click="state_file?.click()" size="small" :toggleable="false" icon="mdi-upload"
                        title="Load a query history JSON file" />
                    <input type="file" ref="state_file" accept="application/json,.json" hidden
                        @change="loadStateFromFile" />
                    <OnsetBtn v-model="ui_state.colour_blind" size="small" icon="mdi-eye-off"
                        title="Red-green colour-blindness mode" />
                </header>
                <div ref="graph_view" class="panel_body explore_editor_body">
                    <QueryBuilder :store="store" :diff="ui_state.diff" :simulate="ui_state.simulate">
                    </QueryBuilder>
                    <div class="explore_overlay explore_history" v-show="ui_state.show_history">
                        <HistoryView :history='(ui_state.history as QueryHistory)' @compare="compareToCurrent"
                            @revert="revertToEntry" @show-tooltip="showTooltip"></HistoryView>
                        <div v-if="ui_state.history_interactive.tooltip.visible" class="history_tooltip"
                            @mouseleave="ui_state.history_interactive.tooltip.visible = false"
                            :style="`top: ${ui_state.history_interactive.tooltip.position.y}px; left: ${ui_state.history_interactive.tooltip.position.x}px;`">
                            <HistoryElement :entry='(ui_state.history_interactive.tooltip.entry as HistoryEntry)'
                                @compare="compareToCurrent" @revert="revertToEntry">
                            </HistoryElement>
                        </div>
                    </div>
                    <pre v-if="ui_state.show_query" class="explore_overlay explore_sparql"
                        v-html="query_string_html" />
                    <ExampleQueries v-if="ui_state.show_examples" class="explore_overlay explore_examples"
                        @select="selected_example"></ExampleQueries>
                </div>
            </section>

            <!-- (b) results -->
            <ResultsView class="explore_results" :query_string="query_string" :store="store" :diff="ui_state.diff">
            </ResultsView>

            <!-- (c) side panel: agent chat and topics -->
            <SidePanel :tabs="side_tabs" v-model:active="ui_state.side_tab" v-model:collapsed="ui_state.side_collapsed">
                <template #chat>
                    <AgentChat :session="agent"></AgentChat>
                </template>
                <template #topics>
                    <div class="explore_topics">
                        <h3>Topics</h3>
                        <TopicSelector v-model="selected_topic_ids"></TopicSelector>
                        <h3>Start from a relation</h3>
                        <NodeLinkSelector :query="{ topic_ids: selected_topic_ids }" @select="selected_root">
                        </NodeLinkSelector>
                    </div>
                </template>
            </SidePanel>
        </div>

    </div>
</template>
<script setup lang="ts">
import Prism from 'prismjs';
import 'prismjs/themes/prism.css';
import { ref, watch, reactive, computed, onMounted } from 'vue'
import TopicSelector from '@/components/explore/TopicSelector.vue';
import NodeLinkSelector from '@/components/explore/NodeLinkSelector.vue';
import QueryBuilder from '@/components/explore/QueryBuilder.vue';
import ResultsView from '@/components/explore/ResultsView.vue';
import OnsetBtn from '@/components/ui/OnsetBtn.vue';
import { NodeLinkRepository, RepositoryState, type MixedResponse } from '@/utils/sparql/store';
import SidePanel, { type SidePanelTab } from '@/components/explore/SidePanel.vue';
import ExampleQueries from '@/components/explore/ExampleQueries.vue';
import AgentChat from '@/components/explore/chat/AgentChat.vue';
import { jsonClone, parseJSON, stringifyJSON } from '@/utils/parsing';
import { NodeLinkRepositoryDiff } from '@/utils/sparql/diff';
import HistoryView from '@/components/explore/history/HistoryView.vue';
import { HistoryEntry, QueryHistory } from '@/utils/sparql/history';
import type { HistoryTooltipEvent } from '@/utils/sparql/helpers';
import HistoryElement from '@/components/explore/history/HistoryElement.vue';
import { activeConfigId, configStorageKey } from '@/utils/api'
import { useAgentSession } from '@/utils/agent/agentSession'
import { applyGraphChange, toAgentGraph } from '@/utils/agent/graph_sync'
import type { GraphChange, GraphDetails } from '@/utils/agent/protocol'


const graph_view = ref<HTMLElement | null>(null)
const state_file = ref<HTMLInputElement | null>(null)

const selected_topic_ids = ref([] as number[])
const query_string_html = ref('')
const query_string = ref('')
const selected_start = ref(null as MixedResponse | null)
// tabs of the side panel, each rendered from the slot with its id
const side_tabs: SidePanelTab[] = [
    { id: 'chat', label: 'Agent', icon: 'mdi-robot-outline' },
    { id: 'topics', label: 'Topics', icon: 'mdi-shape-outline' },
]
const ui_state = reactive({
    loading: false,
    show_query: false,
    show_examples: false,
    side_tab: 'chat',
    side_collapsed: false,
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

const selected_example = (example: MixedResponse) => {
    ui_state.show_examples = false
    selected_root(example)
}

// agent chat: the agent edits the editor graph like any other edit, i.e. the change
// shows up in the change tracking diff and as a history entry (store watcher above)
const applyAgentChange = (change: GraphChange, _graph: unknown, details: GraphDetails) => {
    if (!store.value) {
        store.value = new NodeLinkRepository()
    }
    if (!ui_state.diff_active) {
        ui_state.diff_active = true
        startDiff()
    }
    applyGraphChange(store.value, change, details)
}
const agent = useAgentSession(activeConfigId, {
    read: () => toAgentGraph(store.value),
    apply: applyAgentChange,
}, () => store.value)

const saveState = () => {
    if (!store.value) {
        return
    }
    const store_json = stringifyJSON(store.value)
    localStorage.setItem(configStorageKey('store'), store_json)
    localStorage.setItem(configStorageKey('history'), stringifyJSON(ui_state.history))
    console.log('Saved store and history to localStorage', store_json, ui_state.history)
}
const loadState = () => {
    const store_json = localStorage.getItem(configStorageKey('store'))
    const history_json = localStorage.getItem(configStorageKey('history'))
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
    localStorage.removeItem(configStorageKey('store'))
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
    // allow loading the same file again
    input.value = ''
}

// state colours of the query graph, consumed by assets/graph.css and assets/onset.css
const colour_vars = computed(() => {
    if (!ui_state.colour_blind) {
        return {}
    }
    return {
        '--c-node-added': 'rgb(51,114,237)',
        '--c-node-removed': 'rgb(248,212,150)',
        '--c-node-changed': 'rgb(232,224,253)',
        '--c-node-added-light': 'rgba(51,114,237,0.506)',
        '--c-node-removed-light': 'rgba(248,212,150,0.506)',
        '--c-link-added': 'rgb(51,114,237)',
        '--c-link-removed': 'rgb(248,212,150)',
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
<style scoped>
.explore {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    /* fill the viewport below the app header (2rem) and the page padding */
    height: calc(100vh - 2rem - 2 * var(--space-2));
    min-height: 28rem;
    /* the side panel hosts the agent chat */
    --side-panel-width: 22rem;
}

.explore_main {
    display: flex;
    flex-direction: row;
    gap: var(--space-1);
    flex: 1 1 auto;
    min-height: 0;
}

.explore_editor {
    flex: 1 1 auto;
}

.explore_editor_body {
    overflow: hidden;
}

.explore_results {
    flex: 0 0 26%;
}

.explore_overlay {
    position: absolute;
    z-index: 50;
    background: var(--c-surface);
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
}

.explore_history {
    top: var(--space-1);
    left: var(--space-1);
    bottom: var(--space-1);
    width: min(32rem, 70%);
}

.explore_sparql {
    right: var(--space-1);
    bottom: var(--space-1);
    max-width: 60%;
    max-height: 60%;
    margin: 0;
    padding: var(--space-2);
    overflow: auto;
    font-size: var(--fs-xs);
    border: 1px solid var(--c-border);
}

.explore_examples {
    top: var(--space-1);
    left: var(--space-1);
    max-width: min(40rem, 80%);
    padding: var(--space-2);
    border: 1px solid var(--c-border);
}

.explore_topics {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
}

</style>
