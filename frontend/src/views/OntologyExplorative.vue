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
                        :title="`Save the query and its history in session ${session.id} now (they are also saved after every change)`">Save</OnsetBtn>
                    <OnsetBtn v-model="session.open" size="small" icon="mdi-identifier"
                        :title="`Query session ${session.id}: copy its id or open another session`">Session</OnsetBtn>
                    <OnsetBtn size="small" :toggleable="false" icon="mdi-plus-box-outline"
                        :title="`Start a new, empty query session (current: ${session.id})`" @click="newSession" />
                    <OnsetBtn @click="clearState()" size="small" :toggleable="false" icon="mdi-delete-outline"
                        title="Clear the query and history of this session">Clear</OnsetBtn>
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
                            @revert="revertToEntry" @show-tooltip="showTooltip" @show-in-chat="showInChat"></HistoryView>
                        <div v-if="ui_state.history_interactive.tooltip.visible" class="history_tooltip"
                            @mouseleave="ui_state.history_interactive.tooltip.visible = false"
                            :style="`top: ${ui_state.history_interactive.tooltip.position.y}px; left: ${ui_state.history_interactive.tooltip.position.x}px;`">
                            <HistoryElement :entry='(ui_state.history_interactive.tooltip.entry as HistoryEntry)'
                                @compare="compareToCurrent" @revert="revertToEntry" @show-in-chat="showInChat">
                            </HistoryElement>
                        </div>
                    </div>
                    <div v-if="session.open" class="explore_overlay explore_session">
                        <div class="toolbar"><b>Query session</b><span class="toolbar_spacer"></span>
                            <OnsetBtn size="small" :toggleable="false" icon="mdi-close" @click="session.open = false" />
                        </div>
                        <label>Current session (the query and its history are saved on the server)
                            <span class="toolbar">
                                <input :value="session.id" class="text_input explore_session_id" readonly
                                    @focus="($event.target as HTMLInputElement).select()" />
                                <OnsetBtn size="small" :toggleable="false" icon="mdi-content-copy" title="Copy the session id"
                                    @click="copySessionId" />
                            </span>
                        </label>
                        <label>Open a session by its id
                            <span class="toolbar">
                                <input v-model="session.input" class="text_input explore_session_id" placeholder="Paste a session id…"
                                    spellcheck="false" @keydown.enter="openInput" />
                                <OnsetBtn size="small" :toggleable="false" icon="mdi-folder-open-outline"
                                    :active="!!session.input.trim() && !session.busy" @click="openInput">Open</OnsetBtn>
                            </span>
                        </label>
                        <p v-if="session.message" class="message" :class="{ explore_error: session.failed }">{{ session.message }}</p>
                        <template v-if="session.list.length">
                            <b>Recent sessions</b>
                            <ul class="explore_session_list">
                                <li v-for="s in session.list" :key="s.session_id">
                                    <button class="explore_session_item" :class="{ explore_session_current: s.session_id == session.id }"
                                        :title="s.query" @click="openById(s.session_id)">
                                        <span class="explore_session_id">{{ s.session_id }}</span>
                                        <span>{{ new Date(s.updated_at).toLocaleString() }} · {{ s.history_entries }} history entries</span>
                                    </button>
                                </li>
                            </ul>
                        </template>
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

            <!-- (c) side panel: agent chat, progressive discovery and topics -->
            <SidePanel :tabs="side_tabs" v-model:active="ui_state.side_tab" v-model:collapsed="ui_state.side_collapsed">
                <template #chat>
                    <AgentChat :session="agent"></AgentChat>
                </template>
                <template #progressive>
                    <ProgressivePanel :store="store"
                        @apply="(change, details) => applyEditorChange(change, details, progressiveProvenance(change))"></ProgressivePanel>
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
import { ref, watch, reactive, computed, nextTick, onBeforeUnmount } from 'vue'
import TopicSelector from '@/components/explore/TopicSelector.vue';
import NodeLinkSelector from '@/components/explore/NodeLinkSelector.vue';
import QueryBuilder from '@/components/explore/QueryBuilder.vue';
import ResultsView from '@/components/explore/ResultsView.vue';
import OnsetBtn from '@/components/ui/OnsetBtn.vue';
import { NodeLinkRepository, RepositoryState, type MixedResponse } from '@/utils/sparql/store';
import SidePanel, { type SidePanelTab } from '@/components/explore/SidePanel.vue';
import ExampleQueries from '@/components/explore/ExampleQueries.vue';
import AgentChat from '@/components/explore/chat/AgentChat.vue';
import ProgressivePanel from '@/components/explore/progressive/ProgressivePanel.vue';
import { jsonClone, parseJSON, stringifyJSON } from '@/utils/parsing';
import { NodeLinkRepositoryDiff } from '@/utils/sparql/diff';
import HistoryView from '@/components/explore/history/HistoryView.vue';
import { HistoryEntry, QueryHistory } from '@/utils/sparql/history';
import type { HistoryTooltipEvent } from '@/utils/sparql/helpers';
import HistoryElement from '@/components/explore/history/HistoryElement.vue';
import { activeConfigId } from '@/utils/api'
import { HistorySync } from '@/utils/historySync'
import { newQuerySessionId, QUERY_SESSION_ID_PATTERN, querySessions, type QuerySessionSummary } from '@/utils/sparql/querySession'
import { useAgentSession } from '@/utils/agent/agentSession'
import { applyGraphChange, toAgentGraph } from '@/utils/agent/graph_sync'
import type { GraphChange, GraphDetails } from '@/utils/agent/protocol'
import { agentProvenance, flashChatEntries, progressiveProvenance, type EditProvenance } from '@/utils/sparql/provenance'


const graph_view = ref<HTMLElement | null>(null)
const state_file = ref<HTMLInputElement | null>(null)

const selected_topic_ids = ref([] as number[])
const query_string_html = ref('')
const query_string = ref('')
const selected_start = ref(null as MixedResponse | null)
// tabs of the side panel, each rendered from the slot with its id
const side_tabs: SidePanelTab[] = [
    { id: 'chat', label: 'Agent', icon: 'mdi-robot-outline' },
    { id: 'progressive', label: 'Progressive', icon: 'mdi-chart-histogram' },
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

// provenance of the next store change (agent, progressive panel, revert), consumed by the
// first store watcher run after it, i.e. the one caused by that change; others are the user's
const PROVENANCE_MAX_AGE_MS = 2000
let pending_provenance: { provenance: EditProvenance, at: number } | null = null
const setPendingProvenance = (provenance: EditProvenance) => {
    pending_provenance = { provenance, at: Date.now() }
}
const takePendingProvenance = (): EditProvenance | null => {
    const pending = pending_provenance
    pending_provenance = null
    return pending && Date.now() - pending.at < PROVENANCE_MAX_AGE_MS ? pending.provenance : null
}

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
    const provenance = takePendingProvenance()
    let new_query_string = store.value.generateQuery()
    // every change (also of the layout) is saved in the session, a session's own store is not a change
    if (!loading_session) {
        scheduleQuerySave()
    }
    if (query_string.value != new_query_string) {
        if (ui_state.history && store.value && !loading_session) {
            console.log('Adding history entry', ui_state.history, store.value)
            ui_state.history.tryAddEntry(store.value, provenance)
            history_sync?.schedule()
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
    // track changes from the entry, so the diff_active watcher keeps this baseline
    old_store.value = jsonClone(entry.query)
    ui_state.diff_active = true
    updateDiff()
}
const revertToEntry = (entry: HistoryEntry) => {
    if (!entry.query || !store.value) {
        return
    }
    ui_state.diff_active = false
    ui_state.simulate = false
    setPendingProvenance({
        source: 'revert', ops: [], reverted_to: entry.timestamp,
        reverted_from: entry.provenance ? jsonClone(entry.provenance) : undefined,
    })
    store.value = jsonClone(entry.query)
    old_store.value = null
    ui_state.diff = null
    ui_state.simulate = true
}

const selected_example = (example: MixedResponse) => {
    ui_state.show_examples = false
    selected_root(example)
}

// agent chat and progressive panel: they edit the editor graph like any other edit, i.e. the
// change shows up in the change tracking diff and as a history entry (store watcher above)
const applyEditorChange = (change: GraphChange, details: GraphDetails, provenance: EditProvenance) => {
    setPendingProvenance(provenance)
    if (!store.value) {
        store.value = new NodeLinkRepository()
    }
    if (!ui_state.diff_active) {
        ui_state.diff_active = true
        startDiff()
    }
    applyGraphChange(store.value, change, details)
    // the store watcher only refreshes the diff when the query string changes
    updateDiff()
}
const agent = useAgentSession(activeConfigId, {
    read: () => toAgentGraph(store.value),
    apply: (change, _graph, details, calls) => applyEditorChange(change, details, agentProvenance(change, calls)),
}, () => store.value)

// --- query session (backend query_session.py): the query and its history are saved on the server
// after every change, so the session can be reopened by its id (also in another browser); the last
// session id is kept per configuration in the browser. The history entries get the server's timestamps.
const QUERY_SAVE_DEBOUNCE_MS = 1000
const session = reactive({
    id: '', config: '', open: false, input: '', message: '', failed: false, busy: false,
    list: [] as QuerySessionSummary[],
})
const sessionKey = (config: string) => `onset:${config}:query-session`
// where the browser kept the query and history before the sessions (moved into a new session)
const legacyKey = (config: string, key: 'store' | 'history') => `onset:${config}:${key}`
let history_sync: HistorySync | null = null
let query_timer: ReturnType<typeof setTimeout> | null = null
// while a session's state is put into the editor (no change to record or save)
let loading_session = false

const scheduleQuerySave = () => {
    if (query_timer) {
        clearTimeout(query_timer)
    }
    query_timer = setTimeout(() => saveQueryNow().catch(() => { }), QUERY_SAVE_DEBOUNCE_MS)
}
/** PUTs the editor's query to the current session (and cancels a scheduled save). */
const saveQueryNow = async () => {
    if (query_timer) {
        clearTimeout(query_timer)
        query_timer = null
    }
    // read now: the session may change while the request runs
    const { id, config } = session
    if (!id || !config) {
        return
    }
    const visual_query = store.value ? stringifyJSON(store.value) : null
    const query = store.value ? store.value.generateQuery() : ''
    try {
        await querySessions(config).setQuery(id, query, visual_query)
    } catch (e) {
        console.warn('Saving the query in the session failed', e)
        throw e
    }
}
/** Saves everything of the current session that is not saved yet. */
const flushSession = () => Promise.all([saveQueryNow(), history_sync?.flush()])

const describe = (e: unknown) => (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail?.toString() ?? `${e}`
const statusCode = (e: unknown) => (e as { response?: { status?: number } }).response?.status

/**
 * Opens the session ``sid`` of ``config`` (``create``: also an unknown one) in the editor, after
 * saving the current one; keeps the current session if that fails. ``migrate``: an empty session
 * takes over the query and history the browser kept before the sessions.
 */
const openSession = async (config: string, sid: string, { create = true, migrate = false } = {}): Promise<boolean> => {
    const sessions = querySessions(config)
    let state, stored
    try {
        state = await sessions.state(sid, create)
        stored = await sessions.history(sid)
    } catch (e) {
        const message = statusCode(e) == 404 ? `No session '${sid}' found.` : `Opening the session '${sid}' failed: ${describe(e)}`
        Object.assign(session, { message, failed: true })
        return false
    }
    try {
        await flushSession()
    } catch {
        // the query of the left session stays unsaved, as it would on a backend error anyway
    }
    let history = QueryHistory.fromStored(stored)
    let restored = state.visual_query ? parseJSON<NodeLinkRepository>(state.visual_query) : null
    const legacy_store = localStorage.getItem(legacyKey(config, 'store'))
    const legacy_history = localStorage.getItem(legacyKey(config, 'history'))
    const migrated = migrate && !restored && !history.length && !!(legacy_store || legacy_history)
    if (migrated) {
        history = legacy_history ? parseJSON<QueryHistory>(legacy_history) : history
        restored = legacy_store ? parseJSON<NodeLinkRepository>(legacy_store) : null
    }
    if (!restored && history.length) {
        restored = jsonClone(history.entries[history.entries.length - 1].query)
    }

    loading_session = true
    Object.assign(session, { id: sid, config, input: '' })
    localStorage.setItem(sessionKey(config), sid)
    history_sync = new HistorySync(
        // only while it is the editor's session (a late sync of a left session does nothing)
        () => session.id == sid && session.config == config ? ui_state.history.toStored() : null,
        (update) => sessions.patchHistory(sid, update),
    )
    history_sync.reset(stored)
    ui_state.diff_active = false
    ui_state.diff = null
    old_store.value = null
    ui_state.history = history
    store.value = restored
    if (!restored) {
        query_string.value = ''
        query_string_html.value = ''
    }
    // the store watcher runs before the next tick
    await nextTick()
    loading_session = false
    if (migrated) {
        try {
            await flushSession()
            if (!history_sync.failed) {
                localStorage.removeItem(legacyKey(config, 'store'))
                localStorage.removeItem(legacyKey(config, 'history'))
            }
        } catch {
            // kept in the browser, moved on the next try
        }
    }
    return true
}
/** Reopens the last session of ``config``, or starts a new one if the backend no longer has it. */
const initSession = async (config: string) => {
    const stored = localStorage.getItem(sessionKey(config))
    if (stored && QUERY_SESSION_ID_PATTERN.test(stored)) {
        if (await openSession(config, stored, { create: false })) {
            return
        }
        Object.assign(session, { message: `Session ${stored} could not be opened, started a new one.`, failed: true })
    }
    await openSession(config, newQuerySessionId(), { migrate: true })
}
const newSession = async () => {
    if (await openSession(session.config, newQuerySessionId())) {
        Object.assign(session, { message: 'Started a new session.', failed: false })
    }
}
const openById = async (sid: string) => {
    if (!QUERY_SESSION_ID_PATTERN.test(sid)) {
        Object.assign(session, { message: `'${sid}' is no session id (letters, digits, - and _).`, failed: true })
        return
    }
    if (sid == session.id) {
        return
    }
    session.busy = true
    try {
        if (await openSession(session.config, sid, { create: false })) {
            Object.assign(session, { message: `Opened session ${sid}.`, failed: false })
        }
    } finally {
        session.busy = false
    }
}
const openInput = () => {
    const sid = session.input.trim()
    if (sid && !session.busy) {
        openById(sid)
    }
}
const copySessionId = async () => {
    try {
        await navigator.clipboard.writeText(session.id)
        Object.assign(session, { message: 'Copied the session id.', failed: false })
    } catch {
        Object.assign(session, { message: 'Copying failed: select the id and copy it.', failed: true })
    }
}
const loadSessionList = async () => {
    if (!session.config) {
        return
    }
    try {
        session.list = await querySessions(session.config).list()
    } catch (e) {
        Object.assign(session, { message: `Listing the sessions failed: ${describe(e)}`, failed: true })
    }
}
watch(() => session.open, (open) => open && loadSessionList())
// a session per configuration: switching it saves the current one and opens the configuration's last
watch(activeConfigId, (config) => {
    if (config && config != session.config) {
        initSession(config)
    }
}, { immediate: true })
onBeforeUnmount(() => {
    flushSession().catch(() => { })
})

const saveState = async () => {
    try {
        await flushSession()
        Object.assign(session, {
            message: history_sync?.failed ? 'Saving the history failed.' : `Saved session ${session.id}.`,
            failed: !!history_sync?.failed,
        })
    } catch (e) {
        Object.assign(session, { message: `Saving failed: ${describe(e)}`, failed: true })
    }
}
const clearState = () => {
    store.value = null
    old_store.value = null
    ui_state.diff = null
    ui_state.diff_active = false
    ui_state.history = new QueryHistory()
    query_string.value = ''
    query_string_html.value = ''
    // the store watcher does not run for an empty store
    scheduleQuerySave()
    history_sync?.schedule()
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
            history_sync?.schedule()
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

// history entry -> the agent's tool calls in the chat (entry ids are only valid in this session)
function showInChat(chat_entry_ids: string[]) {
    ui_state.side_tab = 'chat'
    ui_state.side_collapsed = false
    nextTick(() => flashChatEntries(chat_entry_ids))
}

function showTooltip(evt: HistoryTooltipEvent) {
    console.log("Showing History tooltip", evt)
    ui_state.history_interactive.tooltip.visible = true
    ui_state.history_interactive.tooltip.position.x = evt.position.x
    ui_state.history_interactive.tooltip.position.y = evt.position.y
    ui_state.history_interactive.tooltip.entry = evt.entry
}

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

.explore_session {
    top: var(--space-1);
    right: var(--space-1);
    width: min(26rem, 80%);
    max-height: calc(100% - 2 * var(--space-1));
    overflow: auto;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding: var(--space-2);
    font-size: var(--fs-xs);
    border: 1px solid var(--c-border);
}

.explore_session label {
    display: flex;
    flex-direction: column;
    gap: 2px;
}

.explore_session_id {
    flex: 1 1 auto;
    min-width: 0;
    font-family: monospace;
}

.explore_session_list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
}

.explore_session_item {
    width: 100%;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 1px;
    padding: var(--space-1);
    font: inherit;
    text-align: left;
    background: none;
    border: 1px solid transparent;
    cursor: pointer;
}

.explore_session_item:hover {
    border-color: var(--c-border);
}

.explore_session_current {
    border-color: var(--c-accent);
}

.explore_error {
    color: #b3261e;
}

.explore_topics {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
}

</style>
