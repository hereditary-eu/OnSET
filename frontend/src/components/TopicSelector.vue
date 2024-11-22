<template>
    <div>

        <div class="d-flex align-center data_container">
            <OnsetBtn v-for="topic of shown_components" :key="topic.topic_id" class="flex-grow-1 wrapper_clickable">
                {{ topic.topic }}
            </OnsetBtn>
        </div>
        <div class="show_more_wrapper">
            <OnsetBtn @click="expanded = !expanded" btn_height="3rem">Show {{ expanded ? 'less' : 'more' }} </OnsetBtn>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, watch, reactive, computed, onMounted } from 'vue'
import * as d3 from 'd3'
import { Api, type Subject, type Topic } from '@/api/client.ts/Api';
import { BACKEND_URL } from '@/utils/config';
import { de, tr } from 'vuetify/locale';
import OnsetBtn from './OnsetBtn.vue';
interface TopicSelection extends Topic {
    selected: boolean
    depth: number
}
const api = new Api({
    baseURL: BACKEND_URL
})
const expanded = ref(false)
const topics = ref([] as TopicSelection[])
const shown_components = computed(() => {
    if (expanded.value) {
        return topics.value
    } else {
        return topics.value.filter((t) => t.depth < 4)
    }
})
onMounted(() => {
    api.topics.getTopicsRootTopicsRootGet().then(resp => {
        console.log('resp', resp)
        let root = resp.data
        let ordered_topics: TopicSelection[] = []
        let topics_above: Topic[] = [root]
        let topics_one_below: Topic[] = []
        let depth = 0
        while (topics_above.length > 0) {
            ordered_topics.push(...topics_above.map((t) => { return { ...t, depth: depth, selected: false } }))
            for (let t of topics_above) {
                if (t) {
                    topics_one_below.push(...t.sub_topics)
                }
            }
            console.log('topics_one_below', topics_one_below)
            topics_above = topics_one_below
            topics_one_below = []
            depth++
        }
        topics.value = ordered_topics
    }).catch(console.error)
})
</script>
<style>
.clickable_container {
    cursor: pointer;
    width: 16rem;
    padding: 0.5rem;
    border: 1px solid #e0e0e0;
    height: 4rem;
    text-align: center;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0.5rem;
    justify-items: center;
}

.clickable_container:hover {
    border-color: #8fa88f;
}

.clickable_selected {
    background-color: #d5edde;
}

.wrapper_clickable {
    display: flex;
    justify-content: center;
    align-items: center;
}

.data_container {
    display: flex;
    justify-content: space-around;
    justify-items: center;
    align-items: center;
    padding: 0.5rem;
    border-bottom: 1px solid #e0e0e0;
    flex-wrap: wrap;
}

.show_more_wrapper {
    display: flex;
    justify-content: center;
    margin-top: 1rem;
}
</style>