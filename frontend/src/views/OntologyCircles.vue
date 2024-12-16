<script setup lang="ts">
import { ref, watch, reactive, computed, onMounted } from 'vue'
import * as d3 from 'd3'
import { Api, type Subject, type Topic } from '@/api/client.ts/Api';
import { de, fa, he } from 'vuetify/locale';
import type { UnionType } from 'typescript';
import { type NodeType, type SubjectInGraph, GraphMan } from '@/utils/d3-man/GraphMan';
import { CircleMan, SubjectInCircle } from '@/utils/d3-man/CircleMan';
import { BACKEND_URL } from '@/utils/config';
import { CircleMan3D } from '@/utils/three-man/CircleMan3D';
const graph_data = ref([] as SubjectInCircle[])
const topics_root = ref(null as Topic | null)
const circleman = new CircleMan3D()
const api = new Api({
    baseURL: BACKEND_URL
})

watch(() => { graph_data.value, topics_root.value }, () => {
    console.log('node_links changed')
    circleman.nodes = graph_data.value
    circleman.topics_root = topics_root.value
    circleman.initPackedCircles()
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
        const resp_classes = await api.classes.getFullClassesClassesFullGet()
        const resp_topics = await api.topics.getTopicsRootTopicsRootGet()
        topics_root.value = resp_topics.data
        graph_data.value = resp_classes.data as SubjectInCircle[]
        console.log('graph_data', graph_data)
    })().catch(console.error)

    // .style('background-color', 'red')
})

</script>
<template>
    <main>
        <div class="graph_wrapper"></div>

    </main>
</template>
<style>
.graph_wrapper {
    display: flex;
    justify-content: center;
    align-items: center;
    height: 70vh;
    width: 100%;
    background-color: #ffffff;
}

.threed_graph {
    width: 100%;
    height: 100%;
}
</style>