<template>
    <div>
        <div class="d-flex align-center data_container">
            <OnsetBtn v-for="topic of shown_components" :key="topic.topic_id" v-model="topic.selected"
                class="flex-grow-1 wrapper_clickable">
                {{ topic.topic }}
            </OnsetBtn>
        </div>
        <Loading v-if="topics.length == 0"></Loading>
    </div>
</template>

<script setup lang="ts">
import { ref, watch, reactive, computed, onMounted } from 'vue'
import * as d3 from 'd3'
import { Api, type Subject, type Topic } from '@/api/client.ts/Api';
import { BACKEND_URL } from '@/utils/config';
import { de, tr } from 'vuetify/locale';
import OnsetBtn from '@/components/ui/OnsetBtn.vue';
import Loading from '@/components/ui/Loading.vue';
interface TopicSelection extends Topic {
    selected: boolean
    depth: number
}
const api = new Api({
    baseURL: BACKEND_URL
})
const expanded = ref(true)
const topics = ref([] as TopicSelection[])

const model = defineModel({ default: [] as number[] })


const shown_components = computed(() => {
    //TODO: make reactivity work
    const topics_reordered = [...topics.value.filter((t) => t.selected == true),
    ...topics.value.filter((t) => t.selected == false),]
    if (expanded.value) {
        return topics_reordered
    } else {
        return topics_reordered
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
        topics.value = ordered_topics.reverse()
    }).catch(console.error)
})


watch(shown_components, (new_val) => {
    model.value = new_val.filter((t) => t.selected).map((t) => t.topic_id)
}, { deep: true })
watch(model, (new_val) => {
    for (let t of topics.value) {
        t.selected = new_val.includes(t.topic_id)
    }
}, { deep: true })

</script>
<style>
.data_container {
    display: flex;
    justify-content: space-around;
    justify-items: center;
    align-items: center;
    padding: 0.5rem;
    border-bottom: 1px solid #e0e0e0;
    flex-wrap: wrap;
    overflow-x: auto;
    max-height: 14rem;
}

.show_more_wrapper {
    display: flex;
    justify-content: center;
    margin-top: 1rem;
}
</style>