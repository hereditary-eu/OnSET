<template>
    <Expandable v-model="expanded">
        <template v-slot:header>
            {{ store.nodes[0].instance_label }}
        </template>
        <template v-slot:content>
            <svg class="fill_svg">
                <g :transform="`translate(${ui_state.offset.x},${ui_state.offset.y})`">
                    <GraphView :store="view_store" :display-mode="DisplayMode.RESULT_INTERACTIVE"
                        @prop-point-clicked="ui_state.prop_open_event = $event; ui_state.prop_open = true"></GraphView>
                    <Propview v-if="ui_state.prop_open_event" :selection_event="ui_state.prop_open_event"
                        v-model="ui_state.prop_open">
                    </Propview>
                    <use xlink:href="#outlink_selector"></use>
                </g>
            </svg>
        </template>
        <template v-slot:trigger>
            <svg class="fill_svg" :class="miniatureClass" ref="svg_ref">
                <g :transform="`translate(${ui_state.offset.x},${ui_state.offset.y}) scale(${ui_state.scale})`">
                    <GraphView :store="view_store" :display-mode="DisplayMode.RESULTS" :diff="diff"></GraphView>
                </g>
            </svg>
        </template>
    </Expandable>
</template>
<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch, type Ref } from 'vue'
import Propview from '../elements/panels/Propview.vue';
import { PropertiesOpenEvent, scalingFactors, type InstanceNodeLinkRepository } from '@/utils/sparql/querymapper';
import { type Vector2Like } from 'three';
import { DisplayMode } from '@/utils/sparql/helpers';
import Expandable from '../../ui/Expandable.vue';
import GraphView from '../elements/GraphView.vue';
import type { NodeLinkRepositoryDiff } from '@/utils/sparql/diff';
import { MiniatureType } from '@/utils/result-plot/plot-types';
const svg_ref = ref('') as unknown as Ref<HTMLElement>

const { store, diff, miniatureType } = defineProps({
    store: {
        type: Object as () => InstanceNodeLinkRepository,
        required: true
    },
    expanded: {
        type: Boolean,
        required: true
    },
    diff: {
        type: Object as () => NodeLinkRepositoryDiff | null,
        required: false,
        default: null
    },
    miniatureType: {
        type: String as () => MiniatureType,
        required: false,
        default: MiniatureType.BOTH
    }
})
const expanded = ref(false)
const ui_state = reactive({
    prop_open: false,
    prop_open_event: null as PropertiesOpenEvent | null,
    scale: 1 as number,
    offset: { x: 0, y: 0 } as Vector2Like,
})
// the store is a fresh clone; make it reactive so measured subquery sizes re-layout the miniature
const view_store = computed(() => reactive(store) as InstanceNodeLinkRepository)
const miniatureClass = computed(() => {
    switch (miniatureType) {
        case MiniatureType.LEFT:
            return 'result_instance_left'
        case MiniatureType.RIGHT:
            return 'result_instance_right'
        default:
            return ''
    }
})

function rescaleToFit() {
    if (!svg_ref.value) {
        return
    }
    let rect = svg_ref.value.getBoundingClientRect()
    if (svg_ref.value && rect.width > 0 && rect.height > 0) {
        let target_size = {
            x: rect.width,
            y: rect.height
        }
        let { offset, scale, size } = scalingFactors(diff || store, target_size)
        if (isNaN(scale)) {
            scale = 1.0
            offset = { x: 0, y: 0 }
            size = { x: 0, y: 0 }
        }
        ui_state.offset = offset
        ui_state.scale = scale
        // ui_state.size = size
    }
}
watch(() => store, (new_entry) => {
    rescaleToFit()
})
onMounted(() => {
    rescaleToFit()
})

</script>
