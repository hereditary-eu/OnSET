<template>

    <div>


        <h3>Select your Interests...</h3>
        <TopicSelector v-model="selected_topic_ids"></TopicSelector>

        <h3>...pick a relation to start with...</h3>
        <NodeLinkSelector :query="{ topic_ids: selected_topic_ids }" @select="selected_root"></NodeLinkSelector>
        <h3 v-if="selected_start">.. and start querying!</h3>
        <div class="query_build_view">
            <QueryBuilder :root="selected_start"></QueryBuilder>
            <ResultsView :query_string="query_string" :root_node="selected_start"></ResultsView>
        </div>
        <pre v-html="query_string_html" />
    </div>
</template>
<script setup lang="ts">
import Prism from 'prismjs';
import 'prismjs/themes/prism.css';
import { ref, watch, reactive, computed, onMounted } from 'vue'
import TopicSelector from '@/components/explore/TopicSelector.vue';
import NodeLinkSelector from '@/components/explore/NodeLinkSelector.vue';
import type { MixedResponse } from '@/utils/sparql/representation';
import QueryBuilder from '@/components/explore/QueryBuilder.vue';
import ResultsView from '@/components/explore/ResultsView.vue';

// window.Prism = window.Prism || {};
// window.Prism.manual = true;
// loadLanguages(['sparql']);
const selected_topic_ids = ref([] as number[])
const query_string_html = ref('')
const query_string = ref('')
const selected_start = ref(null as MixedResponse | null)

watch(() => selected_topic_ids, () => {
    console.log('selected_topic_ids changed!', selected_topic_ids.value)
}, { deep: true })
watch(() => selected_start, () => {
    if (!selected_start.value) {
        return
    }
    let new_query_string = selected_start.value.link.from_subject.generateQuery()
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
<style lang="scss">
.query_build_view {
    display: flex;
    justify-content: center;
    align-items: start;
    flex-direction: row;
    width: 100%;
    overflow: auto;

    pre {
        width: 25%;
        height: 70vh;
    }
}
</style>