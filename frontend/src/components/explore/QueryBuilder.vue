<template>
    <div class="query_builder">
        <svg class="query_build_wrapper">

            <GraphView :store="store" :display-mode="DisplayMode.EDIT" @edit-point-clicked="clicked_outlink($event)"
                @instance-search-clicked="clicked_instance($event)"></GraphView>
            <OutLinkSelector :selection_event="ui_state.outlink_event" v-model="ui_state.outlink_display"
                :store="store">
            </OutLinkSelector>
            <InstanceSelector :selection_event="ui_state.instance_event" v-model="ui_state.instance_display">
            </InstanceSelector>
            <use xlink:href="#outlink_selector"></use>
            <use xlink:href="#instance_selector"></use>
        </svg>
    </div>
</template>
<script setup lang="ts">
import { ref, watch, reactive, computed, onMounted, defineProps, onBeforeMount } from 'vue'
import { SubjectNode, Link } from '@/utils/sparql/representation';
import NodeComp from './elements/Node.vue';
import OutLinkSelector from './elements/OutLinkSelector.vue';
import { DisplayMode, InstanceSelectorOpenEvent, type NodeSide, type OutlinkSelectorOpenEvent } from '@/utils/sparql/helpers';
import InstanceSelector from './elements/InstanceSelector.vue';
import type { NodeLinkRepository } from '@/utils/sparql/store';
import GraphView from './elements/GraphView.vue';

const { store } = defineProps({
    store: {
        type: Object as () => NodeLinkRepository,
        required: true
    }
})
const ui_state = reactive({
    outlink_display: false,
    outlink_event: null as OutlinkSelectorOpenEvent,
    instance_display: false,
    instance_event: null as InstanceSelectorOpenEvent,
    loading: false
})
const clicked_outlink = (evt: OutlinkSelectorOpenEvent) => {
    ui_state.outlink_display = true
    ui_state.outlink_event = evt
}
const clicked_instance = (evt: InstanceSelectorOpenEvent) => {
    ui_state.instance_display = true
    ui_state.instance_event = evt
}
const root_subject = ref(null as SubjectNode | null)
watch(() => store, () => {
    console.log('Store changed!', store)
    if (!store) {
        return
    }
}, { deep: false })

</script>
<style lang="scss" scoped>
.query_builder {
    width: 80%;
    height: 98%;
}

.query_build_wrapper {
    width: 100%;
    height: 100%;
}

.node {
    cursor: pointer;
    fill: #ccc;
    stroke: #000;
    stroke-width: 1.5px;

}

.node_text {
    font-size: 10px;
    text-anchor: middle;
}
</style>