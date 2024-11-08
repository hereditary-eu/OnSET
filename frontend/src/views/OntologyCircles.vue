<script setup lang="ts">
import { ref, watch, reactive, computed, onMounted } from 'vue'
import * as d3 from 'd3'
import { Api, type Subject } from '@/api/client.ts/Api';
import { de, fa, he } from 'vuetify/locale';
import type { UnionType } from 'typescript';
import { type NodeType, type SubjectInGraph, GraphMan } from '@/utils/GraphMan';
import { CircleMan, SubjectInCircle } from '@/utils/CircleMan';
const graph_data = ref([] as SubjectInCircle[])

const circleman = new CircleMan()
const api = new Api({
    baseURL: 'http://localhost:8000'
})

watch(() => { graph_data.value }, () => {
    console.log('node_links changed')
    circleman.nodes = graph_data.value
    circleman.initPackedCircles()
}, { deep: true })
onMounted(() => {
    circleman.clicked_node = (node: NodeType) => {
        console.log('clicked_node', node)
        // expandGraph(node as SubjectInGraph)
    }
    (async () => {
        const resp = await api.classes.getFullClassesClassesFullGet()
        graph_data.value = resp.data as SubjectInCircle[]

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
<style scoped>
.graph_wrapper {
    display: flex;
    justify-content: center;
    align-items: center;
    height: 70vh;
    width: 80;
    background-color: #f0f0f0;
}
</style>