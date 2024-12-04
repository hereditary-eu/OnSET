<template>
    <svg class="query_build_wrapper">
        <NodeComp v-if="root_subject" :subject="root_subject" :editable="true" @edit-point-clicked="clicked_outlink">
        </NodeComp>
        <OutLinkSelector :selection_event="open_outlink_selector.event" v-model="open_outlink_selector.display">
        </OutLinkSelector>
        <use xlink:href="#outlink_selector"></use>
    </svg>
</template>
<script setup lang="ts">
import { ref, watch, reactive, computed, onMounted, defineProps } from 'vue'
import { MixedResponse, Node, Link } from '@/utils/sparql/representation';
import NodeComp from './elements/Node.vue';
import OutLinkSelector from './elements/OutLinkSelector.vue';
import type { NodeSide, OutlinkSelectorOpenEvent } from '@/utils/sparql/explorer';
const { root } = defineProps({
    root: {
        type: Object as () => MixedResponse,
        required: true
    },
})
const root_subject = ref(null as Node | null)
const open_outlink_selector = reactive({
    display: false,
    event: null as OutlinkSelectorOpenEvent
})
const clicked_outlink = (evt: OutlinkSelectorOpenEvent) => {
    console.log('Clicked outlink!', evt)
    open_outlink_selector.display = true
    open_outlink_selector.event = evt
}
watch(() => root, () => {
    console.log('Root changed!', root)
    if (!root) {
        return
    }
    if (root.subject) {
        root_subject.value = root.subject
    } else if (root.link) {
        const root_subject_holder = root.link.from_subject
        root_subject_holder.to_links = [root.link]

        root_subject.value = root_subject_holder
    }

}, { deep: false })
</script>
<style lang="scss">
.query_build_wrapper {
    width: 100%;
    height: 70rem;
}

.node {
    cursor: pointer;
    fill: #ccc;
    stroke: #000;
    stroke-width: 1.5px;

}

.node_text {
    font: 10px sans-serif;
    text-anchor: middle;
}
</style>