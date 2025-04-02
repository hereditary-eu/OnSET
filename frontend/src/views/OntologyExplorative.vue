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
                <QueryBuilder :store="store" :diff="ui_state.diff"></QueryBuilder>
                <ResultsView :query_string="query_string" :store="store" :diff="ui_state.diff"></ResultsView>
            </div>
            <div class="diff_controls">
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
    </div>
</template>
<script setup lang="ts">
import Prism from 'prismjs';
import 'prismjs/themes/prism.css';
import { ref, watch, reactive, computed, onMounted, onBeforeMount } from 'vue'
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
import { type MixedResponse, type NodeLinkRepository } from '@/utils/sparql/store';
import SelectorGroup from '@/components/ui/SelectorGroup.vue';
import FuzzyQueryStarter from '@/components/explore/FuzzyQueryStarter.vue';
import { jsonClone } from '@/utils/parsing';
import { NodeLinkRepositoryDiff } from '@/utils/sparql/diff';
import { Link, SubjectNode } from '@/utils/sparql/representation';


const api = new Api({
    baseURL: BACKEND_URL
})

// window.Prism = window.Prism || {};
// window.Prism.manual = true;
// loadLanguages(['sparql']);
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
})
const store = ref(null as NodeLinkRepository | null)
const old_store = ref(null as NodeLinkRepository | null)

watch(() => selected_start, () => {
}, { deep: false })
watch(() => selected_topic_ids, () => {
    console.log('selected_topic_ids changed!', selected_topic_ids.value)
}, { deep: true })
watch(() => selected_start, () => {
    if (!selected_start.value) {
        return
    } else {
        store.value = selected_start.value.store
    }
    let new_query_string = store.value.generateQuery()
    if (query_string.value != new_query_string) {
        updateDiff()
        query_string.value = new_query_string
        query_string_html.value = Prism.highlight(
            query_string.value,
            Prism.languages.sparql, 'sparql');
        // query_string.value = selected_start.value.link.from_subject.generateQuery()
    }
}, { deep: true })
const selected_root = (root: MixedResponse) => {
    // console.log('selected_root', root)
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
                        break
                }
            }
        }
        console.log('store after changes', store.value)
    })().catch(console.error)
}

</script>
<style lang="scss" scoped>
.query_build_view {
    display: flex;
    justify-content: center;
    align-items: start;
    flex-direction: row;
    width: 100%;
    overflow: auto;
    height: 70vh;

    pre {
        width: 25%;
        height: 100%;
    }
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
</style>