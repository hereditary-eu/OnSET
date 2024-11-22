<template>

    <div>

        <TopicSelector v-model="selected_topic_ids"></TopicSelector>
    </div>


</template>
<script setup lang="ts">
import { ref, watch, reactive, computed, onMounted } from 'vue'
import * as d3 from 'd3'
import { Api, type Subject } from '@/api/client.ts/Api';
import TopicSelector from '@/components/TopicSelector.vue';
import { BACKEND_URL } from '@/utils/config';

const api = new Api({
    baseURL: BACKEND_URL
})
const selected_topic_ids = ref([] as number[])






</script>
<style lang="scss"></style>