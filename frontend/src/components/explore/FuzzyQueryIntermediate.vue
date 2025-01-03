<template>
    <div class="fuzzy_intermediate" ref="svg_wrapper">
        <svg width="100%" height="100%">
            <GraphView :store="store" :display-mode="DisplayMode.SELECT"></GraphView>
        </svg>
    </div>

</template>
<script setup lang="ts">
import type { Candidates, EnrichedEntitiesRelations, EntitiesRelations } from '@/api/client.ts/Api';
import { DisplayMode, mapERLToStore, NODE_HEIGHT, NODE_WIDTH, NodeSide } from '@/utils/sparql/helpers';
import { Constraint, Link, Node } from '@/utils/sparql/representation';
import { NodeLinkRepository } from '@/utils/sparql/store';
import { compute } from 'three/webgpu';
import { computed, defineProps, onMounted, reactive, useTemplateRef, watch } from 'vue';
import GraphView from './elements/GraphView.vue';
import * as d3 from 'd3'


const svgwrapperRef = useTemplateRef('svg_wrapper')
const start_simulation = () => {
    if (!store || !store.value) return
    let mapped_links = store.value.links.map((link) => {
        return {
            source: link.from_internal_id,
            target: link.to_internal_id,
            ...link
        }
    })
    const simulation = d3.forceSimulation(store.value.nodes)
        .force('charge', d3.forceManyBody())
        .force('center', d3.forceCenter(state.bbox.width / 2, state.bbox.height / 2).strength(0.1))
        .force('link', d3.forceLink<Node, typeof mapped_links[0]>(mapped_links)
            .id((d) => d.internal_id)
            .strength(0.5)
        )
        .force('collide', d3.forceCollide<Node>(d => d.width / 2).strength(0.05))
    simulation.on('tick', () => {
        store.value.nodes.forEach((node) => {
            node.x = Math.max(0, Math.min(state.bbox.width - node.width, node.x))
            node.y = Math.max(0, Math.min(state.bbox.height - node.height, node.y))
        })
    })
    console.log("Started simulation for", store.value.nodes)
}
const { erl } = defineProps({
    erl: {
        type: Object as () => EntitiesRelations | Candidates | EnrichedEntitiesRelations,
        required: true
    }
})
const state = reactive({
    bbox: {
        x: 0,
        y: 0,
        width: 0,
        height: 0
    }
})
onMounted(() => {
    console.log('bbox', svgwrapperRef)
    state.bbox = svgwrapperRef.value.getBoundingClientRect()
    start_simulation()
})
const store = computed(() => {
    return mapERLToStore(erl)
})
watch(() => store.value, start_simulation, { deep: false })
</script>
<style scoped>
.fuzzy_intermediate {
    width: 100%;
    height: 20vh;
}
</style>