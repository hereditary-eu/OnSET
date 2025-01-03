<template>
    <g>
        <g :transform="`translate(${subject.x},${subject.y})`" @mouseout.capture="edit_point_hover($event, false)"
            @mouseenter.capture="edit_point_hover($event, true)" @mouseover="edit_point_hover($event, true)">
            <rect :x="`${-7}px`" :y="`${-7}px`"
                :width="`${subject.width + editor_data.editpoint_r * 2 + (constraint_list_mapped.length > 0 ? CONSTRAINT_WIDTH : 0)}px`"
                :height="`${constraints_height + subject.height + editor_data.editpoint_r * 2}px`" fill-opacity="0">

            </rect>
            <rect :width="`${subject.width}px`" :height="`${subject.height}px`"
                :class="`${subject.deletion_imminent ? 'node_deletion_imminent' : null}`" class="node"
                @mousedown="mouse_down_node" @mousemove="mouse_move_node" @mouseup="mouse_up_node"
                @mouseleave="mouse_up_node">
            </rect>
            <text :x="`${subject.width / 2}px`" :y="`${subject.height / 2}px`" class=node_text>
                {{ (mode == DisplayMode.RESULTS || mode == DisplayMode.RESULT_INTERACTIVE) ?
                    result_subject.instance_label :
                    subject.label }}
            </text>
            <g v-if="mode == DisplayMode.EDIT" v-for="constr_info in constraint_list_mapped"
                :transform="`translate(${subject.width / 2},${constr_info.y})`">
                <Constraint :constraint="constr_info.constraint" :extend_path="constr_info.extend_path"
                    :show_editpoints="editor_data.show_editpoints" :node="subject" @delete="deleteConstraint"
                    @instance-search-clicked="emit('instanceSearchClicked', $event)">

                </Constraint>
            </g>

            <g v-show="mode == DisplayMode.RESULT_INTERACTIVE && editor_data.show_editpoints">
                <circle :cx="subject.width / 2" :cy="subject.height" :r="editor_data.editpoint_r"
                    class="edit_point edit_point_prop"
                    @click="emit('propPointClicked', { node: subject as InstanceNode })"></circle>
            </g>
            <g v-show="mode == DisplayMode.EDIT && editor_data.show_editpoints">
                <circle :cx="0" :cy="subject.height / 2" :r="editor_data.editpoint_r" class="edit_point edit_point_link"
                    @click="emit('editPointClicked', { side: NodeSide.FROM, node: subject })"></circle>
                <circle :cx="subject.width / 2" :cy="constraints_height + subject.height" :r="editor_data.editpoint_r"
                    class="edit_point edit_point_prop"
                    @click="emit('editPointClicked', { side: NodeSide.PROP, node: subject })">
                </circle>
                <circle :cx="subject.width" :cy="subject.height / 2" :r="editor_data.editpoint_r"
                    @click="emit('editPointClicked', { side: NodeSide.TO, node: subject })"
                    class="edit_point edit_point_link">
                </circle>
                <circle :cx="subject.width" :cy="0" :r="editor_data.editpoint_r" @mouseover="hover_deletion(true)"
                    @mouseout="hover_deletion(false)" class="edit_point edit_point_delete" @click="do_deletion()">
                </circle>

            </g>
        </g>
    </g>
</template>
<script setup lang="ts">
import { ref, watch, reactive, computed, onMounted, defineProps, onBeforeUpdate, type Prop, onUpdated, onRenderTriggered } from 'vue'
import { type Subject } from '@/api/client.ts/Api';
import { Node as NodeRepr } from '@/utils/sparql/representation';
import LinkComp from './Link.vue';
import { CONSTRAINT_PADDING, CONSTRAINT_WIDTH, DisplayMode, InstanceSelectorOpenEvent, NodeSide, OutlinkSelectorOpenEvent } from '@/utils/sparql/helpers';
import Constraint from './Constraint.vue';
import type { InstanceNode, PropertiesOpenEvent } from '@/utils/sparql/querymapper';
import type { NodeLinkRepository } from '@/utils/sparql/store';
const emit = defineEmits<{
    editPointClicked: [value: OutlinkSelectorOpenEvent]
    propPointClicked: [value: PropertiesOpenEvent]
    instanceSearchClicked: [value: InstanceSelectorOpenEvent]
}>()

const { subject, mode, store } = defineProps({
    subject: {
        type: Object as () => NodeRepr,
        required: true
    },
    store: {
        type: Object as () => NodeLinkRepository,
        required: true
    },
    mode: {
        type: String as () => DisplayMode,
        default: DisplayMode.SELECT
    }
})
const editor_data = reactive({
    mouse_down: false,
    mouse_x: 0,
    mouse_y: 0,
    constraint_padding: 5,
    show_editpoints: false,
    editpoint_r: 7
})
const mouse_down_node = (event: MouseEvent) => {
    if (mode == DisplayMode.EDIT || mode == DisplayMode.RESULT_INTERACTIVE) {
        editor_data.mouse_down = true
        editor_data.mouse_x = event.clientX
        editor_data.mouse_y = event.clientY
    }
}
const mouse_up_node = (event: MouseEvent) => {
    editor_data.mouse_down = false
}
const mouse_move_node = (event: MouseEvent) => {
    if (editor_data.mouse_down) {
        subject.x += event.clientX - editor_data.mouse_x
        subject.y += event.clientY - editor_data.mouse_y
        editor_data.mouse_x = event.clientX
        editor_data.mouse_y = event.clientY
    }
}
const constraint_list_mapped = computed(() => {
    if (!subject.property_constraints) {
        return []
    }
    let constraints = subject.property_constraints.filter(constr => constr != null).map((constraint) => {
        return {
            constraint: constraint,
            y: 0,
            extend_path: 0
        }
    })
    // if (constraints.length > 0) {
    //     constraints[0].first_prop = true
    // }
    let y_pos = subject.height + CONSTRAINT_PADDING
    let last_height = 0
    for (let constr of constraints) {
        constr.y = y_pos
        y_pos += constr.constraint.height + CONSTRAINT_PADDING
        if (last_height == 0) {
            constr.extend_path = CONSTRAINT_PADDING
        } else {
            constr.extend_path = last_height / 2 + CONSTRAINT_PADDING
        }
        last_height = constr.constraint.height
    }
    return constraints
})
const constraints_height = computed(() => {
    return constraint_list_mapped.value.reduce((acc, constr) => acc + constr.extend_path + constr.constraint.height / 2, 0)
})
watch(() => subject.deletion_imminent, () => {
    if(!store){
        return
    }
    let subElements = store.subElements(subject)
    for (let node of subElements.nodes) {
        node.deletion_imminent = subject.deletion_imminent
    }
}, { deep: true })
const hover_deletion = (state: boolean) => {
    subject.deletion_imminent = state
}
const do_deletion = () => {
    store.deleteWithSubnodes(subject)
}
const edit_point_hover = (event: MouseEvent, state: boolean) => {
    editor_data.show_editpoints = state
}
const deleteConstraint = (constraint) => {
    subject.property_constraints = subject.property_constraints.filter((constr) => constr != constraint)
}
const result_subject = computed(() => subject as InstanceNode)
onMounted(() => {
    console.log('subject', subject)
})
</script>
<style lang="scss">
.node {
    cursor: auto;
    fill: #ccc;
    stroke: #000;
    stroke-width: 1.5px;

}

.node_deletion_imminent {
    fill: #f2b56c;
    stroke-dasharray: 5, 5;
}

.node_text {
    font-size: 10px;
    text-anchor: middle;
}

.edit_point {
    fill: #a0c2a9;
    cursor: pointer;
    fill-opacity: 0.4;
}

.edit_point:hover {
    stroke: #888888;
    display: block;
    fill-opacity: 1;
}

.edit_point_delete {
    fill: #ea694f;
}

.edit_point_prop {
    fill: #a0c2a9;

}

.edit_point_link {
    fill: #c2bca0;
}
</style>