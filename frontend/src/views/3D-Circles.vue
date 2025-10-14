<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { Api, type Topic } from '@/api/client.ts/Api';
import { SubjectInCircle } from '@/utils/d3-man/CircleMan';
import { BACKEND_URL } from '@/utils/config';
import { HierarchicalCircleMan3D } from '@/utils/three-man/HierarchicalCircleMan3D';
import Loading from '@/components/ui/Loading.vue';
import { SunburstEdgeBundling } from '@/utils/d3-man/SunburstEdgeBundling';
import SelectorGroup from '@/components/ui/SelectorGroup.vue';


enum TopicMode {
    THREE_D = 'Three Dimensional',
    EDGE_BUNDLE = 'Edge Bundle',
}

const graph_data = ref([] as SubjectInCircle[])
const ui_state = ref({
    query_mode: TopicMode.EDGE_BUNDLE,
})
const topics_root = ref(null as Topic | null)
const circleman = new HierarchicalCircleMan3D('.graph_wrapper')
const bundleman = new SunburstEdgeBundling('.edge_wrapper')
const api = new Api({
    baseURL: BACKEND_URL
})
const loading = ref(false)
watch(() => { graph_data.value, topics_root.value, ui_state.value.query_mode }, () => {
    console.log('node_links changed')
    switch (ui_state.value.query_mode) {
        case TopicMode.THREE_D:
            circleman.nodes = graph_data.value as any
            circleman.topics_root = topics_root.value as any
            circleman.initPackedCircles()
            break;
        case TopicMode.EDGE_BUNDLE:
            bundleman.nodes = graph_data.value as any
            bundleman.topics_root = topics_root.value as any
            bundleman.init()
            break;
    }

}, { deep: true })
onMounted(() => {
    // circleman.clicked_node = (node: NodeType) => {
    //     console.log('clicked_node', node)
    //     api.classes.getLinksClassesLinksGet({
    //         subject_id: node.subject_id
    //     }).then(resp => {
    //         console.log('resp', resp)
    //         circleman.removeLinks()
    //         const links = resp.data
    //         for (const out of links.targets) {
    //             circleman.addLink(links.source.subject_id, out.target.subject_id, out.count)
    //         }
    //     }).catch(console.error)
    // }
    (async () => {
        loading.value = true
        const resp_classes = await api.classes.getFullClassesClassesFullGet({
            
        })
        const resp_topics = await api.topics.getTopicsRootTopicsRootGet()
        loading.value = false
        topics_root.value = resp_topics.data
        graph_data.value = resp_classes.data as SubjectInCircle[]
        console.log('graph_data', graph_data)
    })().catch((e) => {
        console.error(e)
        loading.value = true
    })

    // .style('background-color', 'red')
})

</script>
<template>
    <main>
        <!-- <ColourRing>
        </ColourRing> -->
        <Loading v-if="loading"></Loading>
        <div v-else class="graph_container">
            <SelectorGroup v-model="ui_state.query_mode" :options="Object.keys(TopicMode).map(qm => {
                return { value: TopicMode[qm], label: TopicMode[qm] }
            })"></SelectorGroup>
        </div>
        <div v-show="ui_state.query_mode == TopicMode.THREE_D" class="graph_wrapper"></div>
        <div v-show="ui_state.query_mode == TopicMode.EDGE_BUNDLE" class="edge_wrapper"></div>
    </main>
</template>
<style>
.graph_wrapper {
    display: flex;
    justify-content: center;
    align-items: center;
    height: 100vh;
    width: 100%;
    background-color: #ffffff;
}

.edge_wrapper {
    display: flex;
    justify-content: center;
    align-items: center;
    height: 100vh;
    width: 100%;
    background-color: #ffffff;
}

.threed_graph {
    width: 100%;
    height: 100%;
}

.graph_container {
    display: flex;
    align-items: center;
    justify-items: center;
    align-self: center;
    justify-self: center;
    /* width: 100%; */
    /* height: 100%; */
}
</style>