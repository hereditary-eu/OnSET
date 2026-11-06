<template>
    <!-- Query & results panel of the ontology builder: SPARQL over the (growing) KG and its result table. -->
    <section class="panel builder_results" :class="{ builder_results_collapsed: collapsed }">
        <header class="panel_header">
            <template v-if="!collapsed">
                <span class="panel_title">Query & results</span>
                <select class="text_input builder_results_class" value="" title="Query the instances of a class"
                    @change="pickClass">
                    <option value="" disabled>Instances of…</option>
                    <option v-for="c in classes" :key="c.id" :value="c.id">{{ c.label }}</option>
                </select>
                <span class="toolbar_spacer"></span>
                <SelectorGroup v-model="display" :options="[{ value: 'labels', label: 'Labels' }, { value: 'raw', label: 'IRIs' }]" />
            </template>
            <OnsetBtn size="small" :toggleable="false" :icon="collapsed ? 'mdi-chevron-left' : 'mdi-chevron-right'"
                :title="collapsed ? 'Show query and results' : 'Collapse'" @click="collapsed = !collapsed" />
        </header>
        <div v-if="collapsed" class="builder_results_rail" @click="collapsed = false" title="Show query and results">
            <OnsetIcon icon="mdi-table" /> {{ result?.rows.length ?? 0 }}
        </div>
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
import OnsetBtn from '@/components/ui/OnsetBtn.vue'
import OnsetIcon from '@/components/ui/OnsetIcon.vue'
import SelectorGroup from '@/components/ui/SelectorGroup.vue'
import { cellText, type OntoClass, type QueryResult } from '@/utils/builder/api'

const { query, result, classes } = defineProps<{
    query: string
    result: QueryResult | null
    classes: OntoClass[]
}>()
const emit = defineEmits<{ apply: [query: string], queryClass: [class_id: string] }>()
const collapsed = defineModel<boolean>('collapsed', { default: false })

const display = ref('labels')
// the edited query; follows the session's query whenever that changes
const draft = ref(query)
watch(() => query, (q) => draft.value = q)

const pickClass = (evt: Event) => {
    const select = evt.target as HTMLSelectElement
    emit('queryClass', select.value)
    select.value = ''
}
</script>
<style scoped>
.builder_results {
    flex: 0 0 26%;
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
