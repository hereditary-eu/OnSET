<template>
    <g id="propview" @mouseout.capture="edit_point_hover($event, false)"
        @mouseenter.capture="edit_point_hover($event, true)" @mouseover="edit_point_hover($event, true)">
        <g :transform="`translate(${attachment_pt.x},${attachment_pt.y})`" v-if="display">
            <foreignObject :height="(NODE_HEIGHT + 10) * 5" :width="NODE_WIDTH + LINK_WIDTH + 35">
                <div class="selection_div_container" :style="{ 'height': `${NODE_HEIGHT * 5 + 10}px` }">
                    <Loading v-if="editor_data.loading"></Loading>
                    
                </div>
            </foreignObject>

            <g v-show="editor_data.show_editpoints">
                <circle :cx="NODE_WIDTH + LINK_WIDTH + 35" :cy="0" :r="editor_data.editpoint_r"
                    class="edit_point edit_point_delete" @click="display = false"></circle>
            </g>
        </g>
    </g>
</template>
<script setup lang="ts">
import { ref, watch, reactive, computed, onMounted } from 'vue'
import { Constraint, MixedResponse } from '@/utils/sparql/representation';
import LinkComp from './Link.vue';
import NodeComp from './Node.vue';
import { BACKEND_URL } from '@/utils/config';
import { Api, RELATION_TYPE, RETURN_TYPE } from '@/api/client.ts/Api';
import { LINK_WIDTH, NODE_HEIGHT, NODE_WIDTH, NodeSide, OutlinkSelectorOpenEvent } from '@/utils/sparql/explorer';
import Loading from '@/components/ui/Loading.vue';

const emit = defineEmits<{
    select: [value: MixedResponse]
}>()
const api = new Api({
    baseURL: BACKEND_URL
})
const { selection_event } = defineProps({
    selection_event: {
        type: Object as () => OutlinkSelectorOpenEvent,
        required: true
    }
})

const editor_data = reactive({
    show_editpoints: false,
    editpoint_r: 7,
    loading: false,
})
const display = defineModel<boolean>()
const update_selection_options = async () => {
    if (display) {
        (async () => {
        })().catch((e) => {
            console.error('Error fetching selection options', e)
            editor_data.loading = false
        })
    } else {
    }
}
// watch(() => display, update_selection_options, { deep: false })
watch(() => selection_event, () => {
    update_selection_options()
}, { deep: false })
// watch(() => editor_data.q, update_selection_options, { deep: false })
const attachment_pt = computed(() => {
    if (!selection_event) {
        return { x: 0, y: 0 }
    }
    if(selection_event.side == NodeSide.TO) {
        return { x: selection_event.node.x, y: selection_event.node.y }
    }
})

const edit_point_hover = (event: MouseEvent, state: boolean) => {
    editor_data.show_editpoints = state
}
</script>

<style lang="css">

</style>