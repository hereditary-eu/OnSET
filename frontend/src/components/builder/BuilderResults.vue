<template>
    <!-- Query & results panel of the ontology builder over the (growing) KG: the visual query editor with
         its results (the session is a configuration of the config-scoped API, see backend builder/kg.py),
         or a SPARQL query with its result table. -->
    <section class="panel builder_results" :class="{ builder_results_collapsed: collapsed }">
        <header class="panel_header">
            <template v-if="!collapsed">
                <span class="panel_title">Query & results</span>
                <SelectorGroup v-model="mode" :options="[{ value: 'visual', label: 'Visual' }, { value: 'sparql', label: 'SPARQL' }]" />
                <select class="text_input builder_results_class" value="" title="Query the instances of a class"
                    @change="pickClass">
                    <option value="" disabled>Instances of…</option>
                    <option v-for="c in classes" :key="c.id" :value="c.id">{{ c.label }}</option>
                </select>
                <span class="toolbar_spacer"></span>
                <SelectorGroup v-if="mode == 'sparql'" v-model="display" :options="[{ value: 'labels', label: 'Labels' }, { value: 'raw', label: 'IRIs' }]" />
            </template>
            <OnsetBtn size="small" :toggleable="false" :icon="collapsed ? 'mdi-chevron-left' : 'mdi-chevron-right'"
                :title="collapsed ? 'Show query and results' : 'Collapse'" @click="collapsed = !collapsed" />
        </header>
        <div v-if="collapsed" class="builder_results_rail" @click="collapsed = false" title="Show query and results">
            <OnsetIcon icon="mdi-table" /> {{ result?.rows.length ?? 0 }}
        </div>
        <template v-else-if="mode == 'visual'">
            <div class="panel_body builder_results_editor">
                <QueryBuilder :store="store" />
                <p v-if="!store.nodes.length" class="message builder_results_hint">
                    Pick a class (Instances of… or the table button on a class) to start a query, then add its
                    fields and links from the points around the class.
                </p>
            </div>
            <ResultsView v-if="store.nodes.length" class="builder_results_view" :store="store"
                :query_string="visual_query" :refresh="refresh" />
        </template>
        <template v-else>
            <div class="builder_results_query">
                <textarea v-model="draft" class="text_input" rows="6" spellcheck="false"
                    placeholder="SELECT ?s ?label WHERE { ?s a onto:Person ; rdfs:label ?label }"
                    @keydown.enter.ctrl.prevent="emit('apply', draft)" @keydown.enter.meta.prevent="emit('apply', draft)" />
                <div class="toolbar">
                    <span class="message">Prefixes onto:, rdfs:, rdf:, xsd:, prov: are predefined.</span>
                    <span class="toolbar_spacer"></span>
                    <OnsetBtn size="small" :toggleable="false" icon="mdi-play" title="Run the query (Ctrl+Enter)"
                        :active="draft != query" @click="emit('apply', draft)">Apply</OnsetBtn>
                </div>
            </div>
            <div class="panel_body">
                <p v-if="result?.error" class="message builder_results_error">{{ result.error }}</p>
                <p v-else-if="!query" class="message">Write a query or pick a class to see its instances.</p>
                <p v-else-if="result && result.rows.length == 0" class="message">
                    No results{{ result.status.running ? ' yet, the knowledge graph is being built…' : '.' }}
                </p>
                <table v-if="result && result.rows.length" class="builder_results_table">
                    <thead>
                        <tr><th v-for="c in result.columns" :key="c">{{ c }}</th></tr>
                    </thead>
                    <tbody>
                        <tr v-for="(row, i) in result.rows" :key="i">
                            <td v-for="(cell, j) in row" :key="j" :title="cell?.value">{{ cellText(cell, display == 'raw') }}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </template>
    </section>
</template>
<script setup lang="ts">
import { ref, watch } from 'vue'
import QueryBuilder from '@/components/explore/QueryBuilder.vue'
import ResultsView from '@/components/explore/ResultsView.vue'
import { api } from '@/utils/api'
import { NodeLinkRepository, RepositoryState } from '@/utils/sparql/store'
import { SubjectNode } from '@/utils/sparql/representation'
import { fitNode } from '@/utils/sparql/helpers'
import OnsetBtn from '@/components/ui/OnsetBtn.vue'
import OnsetIcon from '@/components/ui/OnsetIcon.vue'
import SelectorGroup from '@/components/ui/SelectorGroup.vue'
import { cellText, type OntoClass, type QueryResult } from '@/utils/builder/api'

const { query, result, classes, refresh = 0 } = defineProps<{
    query: string
    result: QueryResult | null
    classes: OntoClass[]
    // bumped while the KG grows, re-runs the visual query's results
    refresh?: number
}>()
const emit = defineEmits<{ apply: [query: string], queryClass: [class_id: string] }>()
const collapsed = defineModel<boolean>('collapsed', { default: false })

const display = ref('labels')
// the edited query; follows the session's query whenever that changes
const draft = ref(query)
watch(() => query, (q) => draft.value = q)

// --- visual mode: the editor's query is the session's query (so the agent sees it) ---
const store = ref(new NodeLinkRepository())
const visual_query = ref('')
// queries the editor generated: any other session query (e.g. the agent's) is shown as SPARQL
const generated = new Set<string>()
const mode = ref<'visual' | 'sparql'>(query ? 'sparql' : 'visual')

let put_timer: ReturnType<typeof setTimeout> | null = null
const applyVisual = () => {
    if (put_timer) {
        clearTimeout(put_timer)
    }
    put_timer = setTimeout(() => {
        if (mode.value == 'visual' && visual_query.value && visual_query.value != query) {
            emit('apply', visual_query.value)
        }
    }, 500)
}
watch(store, () => {
    if (store.value.state != RepositoryState.STABLE) {
        return
    }
    const q = store.value.nodes.length ? store.value.generateQuery().trim() : ''
    if (q != visual_query.value) {
        visual_query.value = q
        generated.add(q)
        applyVisual()
    }
}, { deep: true })
watch(mode, applyVisual)
watch(() => query, (q) => {
    if (q && !generated.has(q)) {
        mode.value = 'sparql'
    }
})

// classes removed from the ontology leave the query, renamed ones take their new label
// (nodes being created in the editor have no class yet)
watch(() => classes.map((c) => `${c.id}:${c.label}`).join(), () => {
    const labels = new Map(classes.map((c) => [`onto:${c.id}`, c.label || c.id]))
    for (const node of [...store.value.nodes]) {
        if (!node.subject_id?.startsWith('onto:')) {
            continue
        } else if (!labels.has(node.subject_id)) {
            store.value.removeNode(node)
        } else if (node.label != labels.get(node.subject_id)) {
            node.label = labels.get(node.subject_id)!
        }
    }
})

/** Instances of a class: a visual query of the class alone, or its SPARQL query (by the parent). */
const queryClass = async (class_id: string) => {
    if (mode.value == 'sparql') {
        emit('queryClass', class_id)
        return
    }
    const subject = (await api.classes.getSubjectClassesSubjectsGet({ subject_id: `onto:${class_id}` })).data
    if (!subject) {
        return
    }
    const node = fitNode(new SubjectNode(subject))!
    node.x = 40
    node.y = 60
    const fresh = new NodeLinkRepository()
    fresh.nodes.push(node)
    store.value = fresh
}
defineExpose({ queryClass })

const pickClass = (evt: Event) => {
    const select = evt.target as HTMLSelectElement
    queryClass(select.value)
    select.value = ''
}
</script>
<style scoped>
.builder_results {
    flex: 0 0 38%;
}

.builder_results_editor {
    flex: 0 0 45%;
    overflow: hidden;
    border-bottom: 1px solid var(--c-border);
}

.builder_results_hint {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    pointer-events: none;
}

.builder_results_view {
    flex: 1 1 auto;
    border: none;
    border-radius: 0;
}

.builder_results_collapsed {
    flex: 0 0 auto;
}

.builder_results_class {
    width: 9rem;
}

.builder_results_rail {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-1);
    padding: var(--space-1);
    font-size: var(--fs-xs);
    cursor: pointer;
}

.builder_results_query {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    padding: var(--space-1);
    border-bottom: 1px solid var(--c-border);
}

.builder_results_query textarea {
    height: auto;
    padding: var(--space-1) var(--space-2);
    font-size: var(--fs-xs);
    resize: vertical;
}

.builder_results_error {
    color: #b3261e;
    white-space: pre-wrap;
}

.builder_results_table {
    border-collapse: collapse;
    font-size: var(--fs-xs);
    width: 100%;
}

.builder_results_table th {
    position: sticky;
    top: 0;
    background: var(--c-surface);
    text-align: left;
    border-bottom: 1px solid var(--c-border);
}

.builder_results_table th,
.builder_results_table td {
    padding: 2px var(--space-1);
    max-width: 16rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.builder_results_table tr:nth-child(even) td {
    background: var(--c-hover);
}
</style>
