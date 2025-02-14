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
                <QueryBuilder :store="store"></QueryBuilder>
                <ResultsView :query_string="query_string" :store="store"></ResultsView>
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
import { Api } from '@/api/client.ts/Api';
import { BACKEND_URL } from '@/utils/config';
import type { SubjectInCircle } from '@/utils/d3-man/CircleMan';
import OnsetBtn from '@/components/ui/OnsetBtn.vue';
import type { MixedResponse, NodeLinkRepository } from '@/utils/sparql/store';
import SelectorGroup from '@/components/ui/SelectorGroup.vue';
import FuzzyQueryStarter from '@/components/explore/FuzzyQueryStarter.vue';


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
const ui_state = reactive({
    loading: false,
    show_query: false,
    query_mode: QueryMode.FUZZY
})
const store = ref(null as NodeLinkRepository | null)
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
</style>