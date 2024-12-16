<template>
    <div class="results_view">
        <div class="results_instance_container">
            <div class="result_instance_element" ref="view_container" v-show="mapped_root_nodes.length == 0"></div>
            <div class="result_instance_element" v-for="subject of mapped_root_nodes">
                <svg class="result_instance_svg">
                    <g :transform="`translate(${offset.x},${offset.y}) scale(${scale})`">
                        <NodeComp :subject="subject" :mode="DisplayMode.RESULTS"></NodeComp>
                    </g>
                </svg>
            </div>
        </div>
    </div>
</template>
<script setup lang="ts">
import { ref, watch, reactive, computed, onMounted, defineProps } from 'vue'
import { MixedResponse, Node, Link } from '@/utils/sparql/representation';
import NodeComp from './elements/Node.vue';
import { QueryMapper } from '@/utils/sparql/querymapper';
import { Vector2, type Vector2Like } from 'three';
import { DisplayMode } from '@/utils/sparql/explorer';

const { root_node, query_string } = defineProps({
    root_node: {
        type: Object as () => MixedResponse,
        required: true
    },
    query_string: {
        type: String,
        required: true
    }
})
const mapper = ref(null as QueryMapper | null)
const mapped_root_nodes = ref([] as Node[])
const scale = ref(1)
const offset = reactive({ x: 0, y: 0 })
const view_container = ref(null as SVGSVGElement | null)
const root_subject = ref(null as Node | null)
const last_query_id = ref(0)
const initial_size = reactive(new Vector2(0, 0))
watch(() => root_node, () => {
    if (!root_node) {
        return
    }
    if (root_node.link) {
        root_subject.value = root_node.link.from_subject
    } else if (root_node.subject) {
        root_subject.value = root_node.subject
    }
}, { deep: false })
watch(() => query_string, () => {
    console.log('Query string changed!', query_string, root_subject.value)
    if(mapped_root_nodes.value.length == 0) {
        initial_size.x = view_container.value?.clientWidth || 0
        initial_size.y = view_container.value?.clientHeight || 0
    }
    mapper.value = new QueryMapper(root_subject.value, initial_size)
    let query_id = last_query_id.value + 1
    last_query_id.value = query_id
    mapper.value.runAndMap(query_string).then((results) => {
        if (query_id == last_query_id.value) {
            mapped_root_nodes.value = results.mapped_nodes
            scale.value = results.scale
            offset.x = results.offset.x
            offset.y = results.offset.y
        }
    }).catch((err) => {
        console.error('Error while mapping query!', err)
    })
}, { deep: true })
</script>
<style lang="scss">
.results_view {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 70vh;
    width: 30%;
}

.results_instance_container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    width: 100%;
    height: 100%;
    overflow: auto;
}

.result_instance_element {
    width: 100%;
    height: 20%;
    display: flex;
    justify-content: center;
    align-items: center;
}
.result_instance_svg {
    width: 100%;
    height: 100%;
}
</style>
