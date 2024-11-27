<template>

    <div>


        <h3>1. Select your Interests</h3>
        <TopicSelector v-model="selected_topic_ids"></TopicSelector>

        <h3>2. Pick a relation to start with</h3>
        <NodeLinkSelector :query="{ topic_ids: selected_topic_ids }"></NodeLinkSelector>

    </div>
</template>
<script setup lang="ts">
import { ref, watch, reactive, computed, onMounted } from 'vue'
import * as d3 from 'd3'
import { Api, type Subject } from '@/api/client.ts/Api';
import TopicSelector from '@/components/explore/TopicSelector.vue';
import { BACKEND_URL } from '@/utils/config';
import NodeLinkSelector from '@/components/explore/NodeLinkSelector.vue';

const api = new Api({
    baseURL: BACKEND_URL
})
const selected_topic_ids = ref([] as number[])


watch(() => selected_topic_ids, () => {
    console.log('selected_topic_ids changed!', selected_topic_ids.value)
}, { deep: true })



</script>
<style lang="scss"></style>