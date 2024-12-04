<template>

    <div>


        <h3>Select your Interests...</h3>
        <TopicSelector v-model="selected_topic_ids"></TopicSelector>

        <h3>...pick a relation to start with...</h3>
        <NodeLinkSelector :query="{ topic_ids: selected_topic_ids }" @select="selected_root"></NodeLinkSelector>
        <h3 v-if="selected_start">.. and start querying!</h3>
        <QueryBuilder :root="selected_start"></QueryBuilder>
    </div>
</template>
<script setup lang="ts">
import { ref, watch, reactive, computed, onMounted } from 'vue'
import * as d3 from 'd3'
import { Api, type Subject } from '@/api/client.ts/Api';
import TopicSelector from '@/components/explore/TopicSelector.vue';
import { BACKEND_URL } from '@/utils/config';
import NodeLinkSelector from '@/components/explore/NodeLinkSelector.vue';
import type { MixedResponse } from '@/utils/sparql/representation';
import QueryBuilder from '@/components/explore/QueryBuilder.vue';

const api = new Api({
    baseURL: BACKEND_URL
})
const selected_topic_ids = ref([] as number[])

const selected_start = ref(null as MixedResponse | null)

watch(() => selected_topic_ids, () => {
    console.log('selected_topic_ids changed!', selected_topic_ids.value)
}, { deep: true })

const selected_root = (root: MixedResponse) => {
    console.log('selected_root', root)
    selected_start.value = root
}

</script>
<style lang="scss"></style>