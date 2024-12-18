<template>
    <Expandable v-model="expanded">
        <template v-slot:header>
            <div class="result_instance_overview_header">{{ subject.instance_label }}</div>
        </template>
        <template v-slot:content>
            <svg class="result_interact_svg">
                <g :transform="`translate(${offset.x},${offset.y})`">
                    <NodeComp :subject="subject.interactive_clone" :mode="DisplayMode.RESULT_INTERACTIVE"
                        @prop-point-clicked="ui_state.prop_open_event = $event; ui_state.prop_open = true">
                    </NodeComp>
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
                    <NodeComp :subject="subject" :mode="DisplayMode.RESULTS"></NodeComp>
                </g>
            </svg>
        </template>
    </Expandable>
</template>
<script setup lang="ts">
import { ref, watch, reactive, computed, onMounted, defineProps } from 'vue'
import { MixedResponse, Node, Link } from '@/utils/sparql/representation';
import NodeComp from './elements/Node.vue';
import Propview from './elements/Propview.vue';
import { InstanceNode, PropertiesOpenEvent, QueryMapper } from '@/utils/sparql/querymapper';
import { Vector2, type Vector2Like } from 'three';
import { DisplayMode } from '@/utils/sparql/explorer';
import Loading from '../ui/Loading.vue';
import Expandable from '../ui/Expandable.vue';

const { subject, scale, offset } = defineProps({
    subject: {
        type: Object as () => InstanceNode,
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
