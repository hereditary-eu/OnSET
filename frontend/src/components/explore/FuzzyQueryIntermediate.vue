<template>
    <div class="fuzzy_intermediate" ref="svg_wrapper">
        <svg width="100%" height="100%">
            <GraphView :store="store" :display-mode="DisplayMode.SELECT"></GraphView>
        </svg>
    </div>

</template>
<script setup lang="ts">
import type { Candidates, EnrichedEntitiesRelations, EntitiesRelations } from '@/api/client.ts/Api';
import { DisplayMode, NODE_HEIGHT, NODE_WIDTH, NodeSide } from '@/utils/sparql/helpers';
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

    let step = erl
    let store = new NodeLinkRepository()
    store.nodes = step.entities.map((entity) => {
        let mapped_node = new Node({
            subject_id: entity.type,
            label: entity.type,
            internal_id: entity.identifier
        })
        mapped_node.height = NODE_HEIGHT / 2
        return mapped_node
    })

    step.relations.forEach((relation, i) => {
        let from_subject = store.nodes.find((n) => n.internal_id == relation.entity)
        if (!from_subject) {
            from_subject = new Node({
                subject_id: relation.entity,
                label: relation.entity,
                internal_id: relation.entity
            })
            from_subject.height = NODE_HEIGHT / 2
        }
        let to_subject = store.nodes.find((n) => n.internal_id == relation.target)
        if (!to_subject) {
            to_subject = new Node({
                subject_id: relation.target,
                label: relation.target,
                internal_id: relation.target
            })
            to_subject.height = NODE_HEIGHT / 2
        }
        store.addOutlink(
            new Link({
                link_id: i,
                from_id: relation.entity,
                to_id: relation.target,
                label: relation.relation,
                from_internal_id: relation.entity,
                to_internal_id: relation.target,
                link_type: 'relation',
                to_proptype: null,
                property_id: null,
                instance_count: 1,
                from_subject,
                to_subject
            }), from_subject, to_subject, NodeSide.TO
        )
    })
    if ((step as Candidates).constraints) {
        (step as Candidates).constraints.forEach((candidate) => {
            let constrained_node = store.nodes.find((n) => n.subject_id == candidate.entity)
            if (constrained_node) {
                let constraint_link = new Link({
                    link_id: 0,
                    from_id: candidate.entity,
                    to_id: null,
                    label: candidate.property,
                    from_internal_id: candidate.entity,
                    to_internal_id: candidate.entity,
                    link_type: 'constraint',
                    to_proptype: candidate.type,
                    property_id: candidate.property,
                    instance_count: 1,
                    from_subject: constrained_node,
                    to_subject: null
                })
                constrained_node.property_constraints.push(Constraint.construct(constraint_link))
            }
        })
    }
    store.nodes = store.nodes.map(node => reactive(node))
    store.links = store.links.map(link => reactive(link))
    return store
})
watch(() => store.value, start_simulation, { deep: false })
</script>
<style scoped>
.fuzzy_intermediate {
    width: 100%;
    height: 20vh;
}
</style>