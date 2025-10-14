<template>
    <Expandable v-model="expanded">
        <template v-slot:header>
            <div class="result_instance_overview_header">{{ store.nodes[0].instance_label }}</div>
        </template>
        <template v-slot:content>
            <svg class="result_interact_svg">
                <g :transform="`translate(${offset.x},${offset.y})`">
                    <GraphView :store="store" :display-mode="DisplayMode.RESULT_INTERACTIVE"
                        @prop-point-clicked="ui_state.prop_open_event = $event; ui_state.prop_open = true"></GraphView>
                    <Propview v-if="ui_state.prop_open_event" :selection_event="ui_state.prop_open_event"
                        v-model="ui_state.prop_open">
                    </Propview>
                    <use xlink:href="#outlink_selector"></use>
                </g>
            </svg>
        </template>
        <template v-slot:trigger>
            <svg class="result_instance_svg">
                <g :transform="`translate(${offset.x},${offset.y}) scale(${scale})`">
                    <GraphView :store="store" :display-mode="DisplayMode.RESULTS" :diff="diff"></GraphView>
                </g>
            </svg>
        </template>
    </Expandable>
</template>
<script setup lang="ts">
import { ref, reactive, defineProps } from 'vue'
import Propview from './elements/panels/Propview.vue';
import { PropertiesOpenEvent, type InstanceNodeLinkRepository } from '@/utils/sparql/querymapper';
import { type Vector2Like } from 'three';
import { DisplayMode } from '@/utils/sparql/helpers';
import Expandable from '../ui/Expandable.vue';
import GraphView from './elements/GraphView.vue';
import type { NodeLinkRepositoryDiff } from '@/utils/sparql/diff';

const { store, scale, offset } = defineProps({
    store: {
        type: Object as () => InstanceNodeLinkRepository,
        required: true
    },
    expanded: {
        type: Boolean,
        required: true
    },
    scale: {
        type: Number,
        required: true
    },
    offset: {
        type: Object as () => Vector2Like,
        required: true
    },
    diff: {
        type: Object as () => NodeLinkRepositoryDiff | null,
        required: false,
        default: null
    }
})
const expanded = ref(false)
const ui_state = reactive({
    prop_open: false,
    prop_open_event: null as PropertiesOpenEvent | null
})
</script>
<style lang="scss">
.results_view {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 70vh;
    width: 30%;
    border-left: 1px solid rgb(192, 213, 191);
}

.results_instance_container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    width: 100%;
    height: 100%;
    overflow: auto;
    padding: 5px;
}

.result_instance_element {
    width: 100%;
    height: 20%;
    display: flex;
    justify-content: center;
    align-items: center;
    margin: 4px;
}

.result_instance_svg {
    width: 100%;
    height: 100%;
}

.result_interact_svg {
    width: 100%;
    height: 100%;
}

.result_instance_header {
    font-size: 1.5rem;
    font-weight: bold;
    padding: 5px;
    border-bottom: 1px solid rgb(192, 213, 191);
    width: 100%;
}

.result_instance_overview_header {
    font-size: 2rem;
}
</style>
