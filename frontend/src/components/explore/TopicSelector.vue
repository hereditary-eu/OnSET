<template>
    <div class="topic_selector">
        <OnsetBtn v-for="topic of shown_components" :key="topic.topic_id" v-model="topic.selected" :toggleable="true"
            size="small" class="topic_btn" :title="topic.topic">
            {{ topic.topic }}
        </OnsetBtn>
        <Loading v-if="topics.length == 0"></Loading>
    </div>
</template>
<script setup lang="ts">
import { ref, watch, computed, onMounted } from 'vue'
import { type Topic } from '@/api/client.ts/Api';
import OnsetBtn from '@/components/ui/OnsetBtn.vue';
import Loading from '@/components/ui/Loading.vue';
import { api } from '@/utils/api'
interface TopicSelection extends Topic {
    selected: boolean
    depth: number
}
const topics = ref([] as TopicSelection[])

const model = defineModel<number[]>({ default: () => [] })


// selected topics first
const shown_components = computed(() => [
    ...topics.value.filter((t) => t.selected == true),
    ...topics.value.filter((t) => t.selected == false),
])
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
<style scoped>
.topic_selector {
    display: flex;
    flex-wrap: wrap;
    gap: 2px;
}

/* topic labels can be long: let them wrap inside the button */
.topic_btn {
    height: auto;
    min-height: var(--control-h-sm);
    max-width: 100%;
    padding: 2px var(--space-1);
    white-space: normal;
    text-align: left;
}
</style>
