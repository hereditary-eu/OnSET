<template>
    <g ref="node_ref" :transform="`translate(${subject.x},${subject.y})`" @mouseout="editPointHover($event, false)"
        @mouseover="editPointHover($event, true)">
        <!-- invisible hover area covering the node, its handles, its aggregate popover and its subqueries -->
        <rect :x="-EDITPOINT_R" :y="hover_extent.y" :width="hover_extent.width" :height="hover_extent.height"
            fill-opacity="0" />
        <rect :width="subject.width" :height="subject.height" class="node" :class="node_statestyle"
            @pointerdown="dragStart" />
        <text :x="subject.width / 2" :y="subject.height / 2" class="node_text">{{ display_label }}</text>
        <!-- group by/aggregate of the node's variable: a popover centred above the node (and its "Specify" handle) -->
        <foreignObject v-if="show_aggregation" :x="subject.width / 2 - AGGREGATE_BOX_WIDTH / 2"
            :y="AGGREGATE_BOX_Y" :width="AGGREGATE_BOX_WIDTH" :height="AGGREGATE_BOX_HEIGHT">
            <div class="node_aggregate">
                <AggregateControls :target="subject" :kind="AggregateKind.NODE" :readonly="!aggregation_editable"
                    :expanded="editor_data.show_editpoints" collapsible />
            </div>
        </foreignObject>

        <g v-for="constr_info in constraint_list_mapped" :transform="`translate(${subject.width / 2},${constr_info.y})`">
            <Sublink :subquery="constr_info.subquery" :extend_path="constr_info.extend_path" :diff="diff_node"
                :show_editpoints="editor_data.show_editpoints" :node="subject" @delete="deleteConstraint"
                :mode="mode" @instance-search-clicked="emit('instanceSearchClicked', $event)" />
        </g>

        <circle v-if="mode == DisplayMode.RESULT_INTERACTIVE" v-show="editor_data.show_editpoints"
            :cx="subject.width / 2" :cy="subject.height" :r="EDITPOINT_R" class="edit_point edit_point_prop"
            @click="emit('propPointClicked', { node: subject as InstanceNode })" />
        <g v-if="mode == DisplayMode.EDIT" v-show="editor_data.show_editpoints">
            <circle :cx="0" :cy="subject.height / 2" :r="EDITPOINT_R" class="edit_point edit_point_link"
                @click="emit('linkPointClicked', { side: OpenEventType.FROM, node: subject, evt: $event })" />
            <text :x="-EDITPOINT_R - 2" :y="subject.height / 2" class="help_text_left">From</text>

            <circle :cx="subject.width / 2" :cy="constraints_height + subject.height" :r="EDITPOINT_R"
                class="edit_point edit_point_prop"
                @click="emit('linkPointClicked', { side: OpenEventType.PROP, node: subject, evt: $event })" />
            <text :x="subject.width / 2 + EDITPOINT_R + 2" :y="constraints_height + subject.height"
                class="help_text_right">Constraint/Property</text>

            <circle :cx="subject.width" :cy="subject.height / 2" :r="EDITPOINT_R"
                @click="emit('linkPointClicked', { side: OpenEventType.TO, node: subject, evt: $event })"
                class="edit_point edit_point_link" />
            <text :x="subject.width + EDITPOINT_R + 2" :y="subject.height / 2" class="help_text_right">To</text>

            <circle :cx="subject.width / 2" :cy="0" :r="EDITPOINT_R"
                @click="emit('typePointClicked', { side: OpenEventType.TO, node: subject, evt: $event })"
                class="edit_point edit_point_type" />
            <text :x="subject.width / 2" :y="-EDITPOINT_R * 2" class="help_text_top">Specify</text>

            <circle :cx="subject.width" :cy="0" :r="EDITPOINT_R" @mouseover="hoverDeletion(true)"
                @mouseout="hoverDeletion(false)" class="edit_point edit_point_delete" @click="doDeletion()" />
        </g>
    </g>
</template>
<script setup lang="ts">
import { watch, reactive, computed, onMounted, useTemplateRef } from 'vue'
import { InstanceNode, SubjectNode as NodeRepr, NodeState, SubQuery } from '@/utils/sparql/representation';
import { CONSTRAINT_PADDING, DisplayMode, EDITPOINT_R, fitNode, InstanceSelectorOpenEvent, NODE_PADDING_X, OpenEventType, SelectorOpenEvent } from '@/utils/sparql/helpers';
import { truncateText } from '@/utils/sparql/measure';
import Sublink from './Subquery.vue';
import AggregateControls from './subqueries/AggregateControls.vue';
import { AggregateKind, isAggregated } from '@/utils/sparql/representation';
import { pointerDrag } from '@/utils/graph-layout';
import type { PropertiesOpenEvent } from '@/utils/sparql/querymapper';
import type { NodeLinkRepository } from '@/utils/sparql/store';
import type { NodeLinkRepositoryDiff } from '@/utils/sparql/diff';

const emit = defineEmits<{
    linkPointClicked: [value: SelectorOpenEvent]
    propPointClicked: [value: PropertiesOpenEvent]
    typePointClicked: [value: SelectorOpenEvent]
    instanceSearchClicked: [value: InstanceSelectorOpenEvent]
}>()

const { subject, mode, store, diff, scale } = defineProps({
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
    },
    diff: {
        type: Object as () => NodeLinkRepositoryDiff | null,
        default: null
    },
    scale: {
        type: Number,
        default: 1
    }
})
const editor_data = reactive({
    show_editpoints: false,
    hover_deletion: false,
    state: NodeState.NORMAL
})
// drag the node like the builder's cards: pointer capture, position relative to the drag start,
// screen pixels divided by the zoom of the view; the position is stored in the node
const dragStart = (evt: PointerEvent) => {
    if (mode != DisplayMode.EDIT && mode != DisplayMode.RESULT_INTERACTIVE && mode != DisplayMode.EDIT_NO_ADD) {
        return
    }
    pointerDrag(evt, { x: subject.x, y: subject.y }, (x, y) => {
        subject.x = x
        subject.y = y
    }, scale)
}
class SubQueryDisplay {
    subquery: SubQuery | null = null
    y: number = 0
    extend_path: number = 0
    constructor(subquery: SubQuery, state: NodeState = NodeState.NORMAL) {
        this.subquery = subquery
    }
}
const calculate_heights = (constraints: SubQueryDisplay[]): SubQueryDisplay[] => {
    let y_pos = subject.height + CONSTRAINT_PADDING
    let last_height = 0
    for (let constr of constraints) {
        constr.y = y_pos
        y_pos += constr.subquery.height + CONSTRAINT_PADDING
        if (last_height == 0) {
            constr.extend_path = CONSTRAINT_PADDING
        } else {
            constr.extend_path = last_height / 2 + CONSTRAINT_PADDING
        }
        last_height = constr.subquery.height
    }
    return constraints
}
const constraint_list_mapped = computed(() => {
    if (!subject.subqueries) {
        return []
    }

    let constraints = subject.subqueries.filter(constr => constr != null).map((subquery) => new SubQueryDisplay(subquery))
    if (diff_node.value) {
        constraints = constraints.concat(diff_node.value.diff_subqueries.removed.map((subquery) => new SubQueryDisplay(subquery.left, NodeState.REMOVED)))
    }
    if (mode == DisplayMode.RESULTS || mode == DisplayMode.RESULT_INTERACTIVE) {
        if (!(subject as InstanceNode).instance_query_props) {
            return []
        }
        constraints = (subject as InstanceNode).instance_query_props.map((subquery) => new SubQueryDisplay(subquery))
    }
    return calculate_heights(constraints)
})
const constraints_height = computed(() => {
    return constraint_list_mapped.value.reduce((acc, constr) => acc + constr.extend_path + constr.subquery.height / 2, 0)
})
watch(() => diff, () => {
    updateNodeState()
}, {
    deep: true
})
watch(() => subject.state, () => {
    updateNodeState()
}, { deep: true })
watch(() => editor_data.hover_deletion, () => {
    if (!store) {
        return
    }
    let target_state = editor_data.hover_deletion ? NodeState.DELETION_IMMINENT : NodeState.NORMAL
    subject.state = target_state
}, { deep: true })

const node_statestyle = computed(() => {
    // console.log('subject.state', subject.state)
    let state = editor_data.state.toLowerCase()
    if (!state) {
        return ''
    }
    return `node_${state.toLowerCase()}`
})
const diff_node = computed(() => {
    if (diff) {
        let diff_node_added = diff.diff_nodes.added.find((node) => node.right.internal_id == subject.internal_id)
        if (diff_node_added) {
            return diff_node_added
        }
        let diff_node_removed = diff.diff_nodes.removed.find((node) => node.left.internal_id == subject.internal_id)
        if (diff_node_removed) {
            return diff_node_removed
        }
        let diff_node_changed = diff.diff_nodes.changed.find((node) => node.left.internal_id == subject.internal_id)
        if (diff_node_changed) {
            return diff_node_changed
        }

    }
    return null
})

const updateNodeState = () => {
    if (subject.state == NodeState.DELETION_IMMINENT) {
        editor_data.state = NodeState.DELETION_IMMINENT
        return
    }
    if (diff) {
        let diff_node = diff.diff_nodes.added.find((node) => node.right.internal_id == subject.internal_id)
        if (diff_node) {
            editor_data.state = NodeState.ADDED
            return
        }
        let diff_node_del = diff.diff_nodes.removed.find((node) => node.left.internal_id == subject.internal_id)
        if (diff_node_del) {
            editor_data.state = NodeState.REMOVED
            return
        }
    }
    editor_data.state = NodeState.NORMAL
}

const hoverDeletion = (state: boolean) => {
    editor_data.hover_deletion = state
}
const doDeletion = () => {
    store.removeNode(subject)
}
// mouseover/mouseout bubble from every child (also the HTML inside the foreignObjects), so only
// leaving the whole node hides the handles; otherwise they flicker while moving across children
const node_ref = useTemplateRef<SVGGElement>('node_ref')
const editPointHover = (event: MouseEvent, state: boolean) => {
    if (!state && node_ref.value?.contains(event.relatedTarget as Node | null)) {
        return
    }
    editor_data.show_editpoints = state
}
const deleteConstraint = (constraint) => {
    subject.subqueries = subject.subqueries.filter((constr) => constr != constraint)
}
const is_result_mode = computed(() => mode == DisplayMode.RESULTS || mode == DisplayMode.RESULT_INTERACTIVE)
const AGGREGATE_BOX_WIDTH = 140
const AGGREGATE_BOX_HEIGHT = 22
const AGGREGATE_BOX_Y = -EDITPOINT_R * 3 - 2 - AGGREGATE_BOX_HEIGHT
// group by/aggregate of the node: editable while hovered in the editor (or once set), shown in previews if set
const aggregation_editable = computed(() => mode == DisplayMode.EDIT || mode == DisplayMode.EDIT_NO_ADD)
const show_aggregation = computed(() => !is_result_mode.value && (aggregation_editable.value || isAggregated(subject)))
// Query nodes are sized to their class label. Result nodes keep the layout of the query
// (positions are computed from it), so their instance label is shortened to fit instead.
const display_label = computed(() => {
    if (is_result_mode.value) {
        return truncateText((subject as InstanceNode).instance_label, subject.width - NODE_PADDING_X)
    }
    return subject.label
})
watch(() => subject.label, () => {
    if (!is_result_mode.value) {
        fitNode(subject)
    }
}, { immediate: true })
const hover_extent = computed(() => {
    const subquery_width = constraint_list_mapped.value.reduce((acc, c) => Math.max(acc, c.subquery.width), 0)
    // while hovered, reach up to the aggregate popover, so moving to it keeps the node hovered
    const y = editor_data.show_editpoints && show_aggregation.value && aggregation_editable.value ? AGGREGATE_BOX_Y : -EDITPOINT_R
    return {
        y,
        width: Math.max(subject.width, subject.width / 2 + subquery_width) + EDITPOINT_R * 2,
        height: constraints_height.value + subject.height + EDITPOINT_R - y,
    }
})

onMounted(() => {
    // console.log('subject', subject)
    updateNodeState()
})
</script>
<style>
.node_aggregate {
    display: flex;
    justify-content: center;
    align-items: flex-end;
    height: 100%;
    font-size: var(--fs-xs);
}

.node_aggregate .aggregate_controls {
    padding: 1px 2px;
    background: var(--c-surface);
    border: 1px solid rgb(105, 132, 99);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}
</style>
