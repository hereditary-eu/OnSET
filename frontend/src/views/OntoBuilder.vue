<template>
    <!-- Ontology builder: ontology editor, query & results over the KG being extracted, agent chat and text search -->
    <div class="builder">
        <div class="builder_main">
            <section class="panel builder_editor">
                <header class="panel_header">
                    <span class="panel_title">Ontology · {{ builder?.name ?? builderId }}</span>
                    <span v-if="status" class="builder_status" :title="status.last_error ?? ''">
                        <OnsetIcon v-if="status.running" icon="mdi-loading mdi-spin" />
                        <OnsetIcon v-else icon="mdi-check" />
                        {{ status.processed }}/{{ status.total }} docs · {{ status.triples }} triples
                        <span v-if="status.errors" class="builder_error">· {{ status.errors }} errors</span>
                        · {{ status.store }}
                    </span>
                    <OnsetBtn size="small" :toggleable="false" icon="mdi-refresh" title="Extract the knowledge graph again"
                        :active="!!state" @click="rebuild">Rebuild</OnsetBtn>
                    <span class="toolbar_spacer"></span>
                    <OnsetBtn v-model="io.open" size="small" icon="mdi-swap-vertical" title="Import or export Turtle"
                        :active="!!state" @click="io.prefix = state?.ontology.prefix ?? ''">Import / Export</OnsetBtn>
                    <OnsetBtn size="small" :toggleable="false" icon="mdi-plus-box-outline"
                        :title="`Start a new, empty session (current: ${sessionId})`" @click="newSession" />
                </header>
                <div class="panel_body builder_editor_body">
                    <p v-if="error" class="message builder_error builder_banner">{{ error }}</p>
                    <OntologyEditor v-if="state" v-model="state.ontology" @query="cardQuery" />
                    <p v-else-if="!error" class="message">Loading the session…</p>

                    <div v-if="io.open && state" class="builder_io">
                        <div class="toolbar"><b>Import / Export</b><span class="toolbar_spacer"></span>
                            <OnsetBtn size="small" :toggleable="false" icon="mdi-close" @click="io.open = false" />
                        </div>
                        <label>Prefix IRI<input v-model="io.prefix" class="text_input" /></label>
                        <SelectorGroup v-model="io.content" :options="[{ value: 'ontology', label: 'Ontology' },
                        { value: 'kg', label: 'KG' }, { value: 'all', label: 'Both' }]" />
                        <div class="toolbar">
                            <a class="onset_btn onset_btn_small" :href="api.exportUrl(io.content, io.prefix)" target="_blank"
                                rel="noopener"><OnsetIcon icon="mdi-download" /> Download</a>
                            <OnsetBtn size="small" :toggleable="false" icon="mdi-content-save" @click="save">Save on server</OnsetBtn>
                            <OnsetBtn size="small" :toggleable="false" icon="mdi-upload" title="Import an ontology and/or KG (.ttl); a changed prefix overrides the file's"
                                @click="import_file?.click()">Import…</OnsetBtn>
                            <input ref="import_file" type="file" accept=".ttl,text/turtle" hidden @change="importFile" />
                        </div>
                        <p v-if="io.message" class="message" :class="{ builder_error: io.failed }">{{ io.message }}</p>
                    </div>
                </div>
            </section>

            <BuilderResults v-if="state" ref="results_panel" :key="sessionId" :query="state.query" :result="result"
                :classes="state.ontology.classes" :refresh="results_refresh" v-model:collapsed="results_collapsed"
                @apply="applyQuery" @query-class="queryClass" />

            <SidePanel :tabs="side_tabs" v-model:active="side_tab" v-model:collapsed="side_collapsed">
                <template #chat>
                    <AgentChat :session="agent" hint="Ask the agent to build the ontology, e.g."
                        placeholder="Ask the agent to change the ontology…" :examples="[
                            'Search the texts and propose an ontology for them.',
                            'Add a field for the publication date and query it.',
                        ]" />
                </template>
                <template #search>
                    <TextSearch :builder-id="builderId" />
                </template>
            </SidePanel>
        </div>
    </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, provide, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import OnsetBtn from '@/components/ui/OnsetBtn.vue'
import OnsetIcon from '@/components/ui/OnsetIcon.vue'
import SelectorGroup from '@/components/ui/SelectorGroup.vue'
import SidePanel, { type SidePanelTab } from '@/components/explore/SidePanel.vue'
import AgentChat from '@/components/explore/chat/AgentChat.vue'
import OntologyEditor from '@/components/builder/OntologyEditor.vue'
import BuilderResults from '@/components/builder/BuilderResults.vue'
import TextSearch from '@/components/builder/TextSearch.vue'
import { AgentSession } from '@/utils/agent/agentSession'
import { setActiveConfig } from '@/utils/api'
import { OntoConfig } from '@/utils/sparql/ontoconfig'
import {
    builderSession, listBuilders,
    type BuilderSummary, type ExportContent, type Ontology, type QueryResult, type SessionState,
} from '@/utils/builder/api'

const POLL_MS = 1500
// the visual query's results re-run at most this often while the KG grows
const RESULTS_REFRESH_MS = 5000
const PUT_DEBOUNCE_MS = 300

const route = useRoute()
const builderId = route.params.builderId as string
const builder = ref<BuilderSummary>()
listBuilders().then((bs) => builder.value = bs.find((b) => b.id == builderId)).catch(() => { })

const side_tabs: SidePanelTab[] = [
    { id: 'chat', label: 'Agent', icon: 'mdi-robot-outline' },
    { id: 'search', label: 'Text search', icon: 'mdi-text-search' },
]
const side_tab = ref('chat')
const side_collapsed = ref(false)
const results_collapsed = ref(false)

// --- session: its id is kept per builder in the browser, the backend creates it on first access ---
const storage_key = `onset:builder:${builderId}:session`
const createSession = () => {
    const id = crypto.randomUUID()
    localStorage.setItem(storage_key, id)
    return id
}
const sessionId = ref(localStorage.getItem(storage_key) ?? createSession())
const api = computed(() => builderSession(builderId, sessionId.value))
// the visual query editor talks to the session as the configuration builder:<builder>:<session>
watch(sessionId, (sid) => {
    setActiveConfig(`builder:${builderId}:${sid}`)
    OntoConfig.ensureConfig().catch((e) => console.error('Loading the session config failed', e))
}, { immediate: true })

const state = ref<SessionState | null>(null)
const result = ref<QueryResult | null>(null)
const error = ref('')
const status = computed(() => result.value?.status ?? state.value?.status)

const describe = (e: unknown) => (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail?.toString() ?? `${e}`

// --- ontology sync: local edits are PUT (debounced); server states are adopted unless there are unsent edits ---
const ontoKey = (o: Ontology) => JSON.stringify(o)
let sent_key = ''
let put_timer: ReturnType<typeof setTimeout> | null = null
let pending = 0

const adopt = (s: SessionState) => {
    if (!state.value || ontoKey(state.value.ontology) == sent_key) {
        state.value = s
        sent_key = ontoKey(s.ontology)
    } else {
        Object.assign(state.value, { version: s.version, query: s.query, status: s.status })
    }
}

const putOntology = async () => {
    if (put_timer) {
        clearTimeout(put_timer)
        put_timer = null
    }
    if (!state.value) {
        return
    }
    sent_key = ontoKey(state.value.ontology)
    pending++
    try {
        adopt(await api.value.setOntology(state.value.ontology))
        error.value = ''
    } catch (e) {
        error.value = `Saving the ontology failed: ${describe(e)}`
    } finally {
        pending--
    }
}
watch(() => state.value && ontoKey(state.value.ontology), (key) => {
    if (key && key != sent_key) {
        if (put_timer) {
            clearTimeout(put_timer)
        }
        put_timer = setTimeout(putOntology, PUT_DEBOUNCE_MS)
    }
})

// --- polling: the state (agent changes, build status) and, while the KG changes, the results ---
const loadResults = async () => {
    result.value = state.value?.query ? await api.value.results() : null
}
let polling = false
let was_running = false
const results_refresh = ref(0)
let refreshed = { triples: -1, at: 0 }
const poll = async () => {
    if (polling) {
        return
    }
    polling = true
    try {
        const s = await api.value.state()
        const changed = !state.value || s.version != state.value.version
        if (put_timer || pending) {
            state.value!.status = s.status
        } else {
            adopt(s)
        }
        if (changed || s.status.running || was_running) {
            await loadResults()
        }
        was_running = s.status.running
        if (s.status.triples != refreshed.triples && (!s.status.running || Date.now() - refreshed.at > RESULTS_REFRESH_MS)) {
            refreshed = { triples: s.status.triples, at: Date.now() }
            results_refresh.value++
        }
        error.value = ''
    } catch (e) {
        error.value = `The builder backend is not reachable: ${describe(e)}`
    } finally {
        polling = false
    }
}
poll()
const poll_timer = setInterval(poll, POLL_MS)

const run = async (action: () => Promise<unknown>) => {
    try {
        await action()
    } catch (e) {
        error.value = describe(e)
    }
}
const applyQuery = (query: string) => run(async () => {
    adopt(await api.value.setQuery(query))
    await loadResults()
})
const queryClass = (class_id: string) => run(async () => {
    await putOntology()
    results_collapsed.value = false
    await applyQuery((await api.value.classQuery(class_id)).query)
})
// the query button of a class card: its instances, in the panel's current mode
const results_panel = ref<InstanceType<typeof BuilderResults> | null>(null)
const cardQuery = (class_id: string) => run(async () => {
    await putOntology()
    results_collapsed.value = false
    await results_panel.value?.queryClass(class_id)
})
const rebuild = () => run(async () => adopt(await api.value.rebuild()))

const newSession = () => {
    sessionId.value = createSession()
    state.value = null
    result.value = null
    sent_key = ''
    poll()
}

// --- import / export ---
const io = reactive({ open: false, prefix: '', content: 'all' as ExportContent, message: '', failed: false })
const import_file = ref<HTMLInputElement | null>(null)
const ioRun = async (action: () => Promise<string>) => {
    try {
        io.message = await action()
        io.failed = false
    } catch (e) {
        io.message = describe(e)
        io.failed = true
    }
}
const save = () => ioRun(async () => `Saved to ${(await api.value.save(io.content, io.prefix)).path}`)
const importFile = () => {
    const file = import_file.value?.files?.[0]
    if (!file || !state.value) {
        return
    }
    const prefix = io.prefix != state.value.ontology.prefix ? io.prefix : undefined
    import_file.value!.value = ''
    ioRun(async () => {
        await putOntology()
        sent_key = '' // adopt the imported ontology
        state.value = null
        adopt(await api.value.import(file, prefix))
        io.prefix = state.value!.ontology.prefix
        await loadResults()
        return `Imported ${file.name}.`
    })
}

// --- agent chat over the builder session; its changes arrive as builder_state ---
const agent = new AgentSession({
    url: () => api.value.wsUrl(),
    session_id: (sid) => sid,
    onMessage: (m) => {
        if (m.type == 'builder_state') {
            adopt(m.state)
            loadResults()
        } else if (m.type == 'tool_call' && m.status == 'success') {
            poll()
        }
    },
})
watch(sessionId, (sid) => agent.connect(sid), { immediate: true })
provide('builderExportUrl', (content: ExportContent, prefix: string) => api.value.exportUrl(content, prefix))

onBeforeUnmount(() => {
    clearInterval(poll_timer)
    agent.disconnect()
    setActiveConfig(null)
})
</script>
<style scoped>
.builder {
    display: flex;
    flex-direction: column;
    /* fill the viewport below the app header (2rem) and the page padding, as the explore view */
    height: calc(100vh - 2rem - 2 * var(--space-2));
    min-height: 28rem;
    --side-panel-width: 22rem;
}

.builder_main {
    display: flex;
    flex-direction: row;
    gap: var(--space-1);
    flex: 1 1 auto;
    min-height: 0;
}

.builder_editor {
    flex: 1 1 auto;
}

.builder_editor_body {
    overflow: hidden;
}

.builder_status {
    display: inline-flex;
    min-width: 0;
    overflow: hidden;
    align-items: center;
    gap: var(--space-1);
    font-size: var(--fs-xs);
    white-space: nowrap;
    opacity: 0.85;
}

.builder_error {
    color: #b3261e;
}

.builder_banner {
    position: absolute;
    bottom: 0;
    left: 0;
    z-index: 10;
    background: var(--c-surface);
}

.builder_io {
    position: absolute;
    z-index: 20;
    top: var(--space-1);
    right: var(--space-1);
    width: 24rem;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding: var(--space-2);
    font-size: var(--fs-xs);
    background: var(--c-surface);
    border: 1px solid var(--c-border);
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
}

.builder_io label {
    display: flex;
    flex-direction: column;
    gap: 2px;
}

.builder_io a.onset_btn {
    text-decoration: none;
}
</style>
