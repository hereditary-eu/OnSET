<template>

    <div>


        <h3>Select your Interests...</h3>
        <TopicSelector v-model="selected_topic_ids"></TopicSelector>

        <h3>...pick a relation to start with...</h3>
        <NodeLinkSelector :query="{ topic_ids: selected_topic_ids }" @select="selected_root"></NodeLinkSelector>
        <h3 v-if="selected_start">.. and start querying!</h3>
        <div class="query_build_view">
            <QueryBuilder :root="selected_start"></QueryBuilder>
        </div>
        <pre v-html="query_string" />
    </div>
</template>
<script setup lang="ts">
import Prism from 'prismjs';
import loadLanguages from 'prismjs/components/';
import 'prismjs/themes/prism.css';
import { ref, watch, reactive, computed, onMounted } from 'vue'
import * as d3 from 'd3'
import { Api, type Subject } from '@/api/client.ts/Api';
import TopicSelector from '@/components/explore/TopicSelector.vue';
import { BACKEND_URL } from '@/utils/config';
import NodeLinkSelector from '@/components/explore/NodeLinkSelector.vue';
import type { MixedResponse } from '@/utils/sparql/representation';
import QueryBuilder from '@/components/explore/QueryBuilder.vue';

// window.Prism = window.Prism || {};
// window.Prism.manual = true;
// loadLanguages(['sparql']);
const api = new Api({
    baseURL: BACKEND_URL
})
const selected_topic_ids = ref([] as number[])
const query_string = ref('')
const selected_start = ref(null as MixedResponse | null)

watch(() => selected_topic_ids, () => {
    console.log('selected_topic_ids changed!', selected_topic_ids.value)
}, { deep: true })
watch(() => selected_start, () => {
    if (!selected_start.value) {
        return
    }
    query_string.value = Prism.highlight(
        selected_start.value.link.from_subject.generateQuery(),
        Prism.languages.sparql, 'sparql');
    // query_string.value = selected_start.value.link.from_subject.generateQuery()
}, { deep: true })
const selected_root = (root: MixedResponse) => {
    // console.log('selected_root', root)
    selected_start.value = root
}

</script>
<style lang="scss">
.query_build_view{
    display: flex;
    justify-content: center;
    align-items: start;
    flex-direction: row;
    width: 100%;
    height: 100%;
    overflow: auto;
    pre{
        width: 25%;
        height: 70vh;
    }
}

</style>