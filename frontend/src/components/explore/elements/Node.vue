<template>
    <g>
        <g :transform="`translate(${subject.x},${subject.y})`">
            <rect :width="`${subject.width}px`" :height="`${subject.height}px`" class="node"
                @mousedown="mouse_down_node" @mousemove="mouse_move_node" @mouseup="mouse_up_node"
                @mouseleave="mouse_up_node">
            </rect>
            <text :x="`${subject.width / 2}px`" :y="`${subject.height / 2}px`" class=node_text>
                {{ subject.label }}
            </text>
            <g v-for="constr_info in constraint_list_mapped"
                :transform="`translate(${subject.width / 2},${constr_info.y})`">
                <Constraint :constraint="constr_info.constraint" :extend_path="constr_info.extend_path">
                </Constraint>
            </g>
            <circle v-if="editable" :cx="0" :cy="subject.height / 2" r="7" class="edit_point edit_point_link"
                @click="emit('editPointClicked', { side: NodeSide.FROM, node: subject })"></circle>
            <circle v-if="editable" :cx="subject.width / 2" :cy="constraints_height + subject.height" r="7"
                class="edit_point edit_point_prop"
                @click="emit('editPointClicked', { side: NodeSide.PROP, node: subject })">
            </circle>
            <circle v-if="editable" :cx="subject.width" :cy="subject.height / 2" r="7"
                @click="emit('editPointClicked', { side: NodeSide.TO, node: subject })"
                class="edit_point edit_point_link">
            </circle>

        </g>
        <g v-for="to_link of subject.to_links ">
            <Node :subject="to_link.to_subject" :editable="editable"
                @edit-point-clicked="emit('editPointClicked', $event)">
            </Node>
            <LinkComp :link="to_link"></LinkComp>
        </g>
        <g v-for="from_link of subject.from_links ">
            <Node :subject="from_link.from_subject" :editable="editable"
                @edit-point-clicked="emit('editPointClicked', $event)">
            </Node>
            <LinkComp :link="from_link"></LinkComp>
        </g>
    </g>
</template>
<script setup lang="ts">
import { ref, watch, reactive, computed, onMounted, defineProps, onBeforeUpdate } from 'vue'
import { type Subject } from '@/api/client.ts/Api';
import { Node as NodeRepr } from '@/utils/sparql/representation';
import LinkComp from './Link.vue';
import { NodeSide, OutlinkSelectorOpenEvent } from '@/utils/sparql/explorer';
import Constraint from './Constraint.vue';
const emit = defineEmits<{
    editPointClicked: [value: OutlinkSelectorOpenEvent]

}>()
const { subject, editable } = defineProps({
    subject: {
        type: Object as () => NodeRepr,
        required: true
    },
    editable: {
        type: Boolean,
        default: false
    }
})
const editor_data = reactive({
    mouse_down: false,
    mouse_x: 0,
    mouse_y: 0,
    constraint_padding: 5
})
const mouse_down_node = (event: MouseEvent) => {
    if (editable) {
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
    let y_pos = subject.height + editor_data.constraint_padding
    let last_height = 0
    for (let constr of constraints) {
        constr.y = y_pos
        y_pos += constr.constraint.height + editor_data.constraint_padding
        if (last_height == 0) {
            constr.extend_path = editor_data.constraint_padding
        } else {
            constr.extend_path = last_height / 2 + editor_data.constraint_padding
        }
        last_height = constr.constraint.height
    }
    return constraints
})
const constraints_height = computed(() => {
    return constraint_list_mapped.value.reduce((acc, constr) => acc + constr.extend_path + constr.constraint.height/2, 0)
})
</script>
<style lang="scss">
.node {
    cursor: auto;
    fill: #ccc;
    stroke: #000;
    stroke-width: 1.5px;

}

.node_text {
    font: 10px sans-serif;
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

.edit_point_prop {
    fill: #a0c2a9;

}

.edit_point_link {
    fill: #c2bca0;
}
</style>