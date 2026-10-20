<template>
    <g>
        <path :d="`M 0,-${extend_path} V ${subquery.height / 2} H ${SUBQUERY_INDENT}`" class="subquery_connection" />
        <rect :x="SUBQUERY_INDENT" :y="0" :width="content_width" :height="subquery.height" class="subquery_box"
            :class="query_statestyle" />
        <circle v-if="mode == DisplayMode.EDIT" v-show="show_editpoints" :cx="subquery.width" :cy="0"
            :r="EDITPOINT_R" class="edit_point edit_point_delete" @click="emit('delete', subquery)" />
        <foreignObject :x="SUBQUERY_INDENT" :y="0" :width="content_width" :height="subquery.height">
            <div class="subquery" ref="content_ref">
                <NumberConstraintEditor v-if="(subquery.constraint_type == SubQueryType.NUMBER)"
                    :constraint="(subquery as NumberConstraint)" />
                <StringConstraintEditor v-else-if="(subquery.constraint_type == SubQueryType.STRING)"
                    :constraint="(subquery as StringConstraint)" />
                <DateConstraintEditor v-else-if="(subquery.constraint_type == SubQueryType.DATE)"
                    :constraint="(subquery as DateConstraint)" />
                <SubjectConstraintEditor v-else-if="(subquery.constraint_type == SubQueryType.SUBJECT)"
                    :constraint="(subquery as SubjectConstraint)" :node="node"
                    @open_search="emit('instanceSearchClicked', $event)" />
                <BooleanConstraintEditor v-else-if="(subquery.constraint_type == SubQueryType.BOOLEAN)"
                    :constraint="(subquery as BooleanConstraint)" />
                <Property v-else-if="(subquery.constraint_type == SubQueryType.QUERY_PROP)"
                    :query="(subquery as QueryProp)" />
                <InstanceProperty v-else-if="(subquery.constraint_type == SubQueryType.INSTANCE_PROP)"
                    :query="(subquery as InstanceQueryProp)" />
                <VectorSubquery v-else-if="(subquery.constraint_type == SubQueryType.VECTOR_SORT)"
                    :constraint="(subquery as VectorSort)" />
            </div>
        </foreignObject>
    </g>
</template>
<script setup lang="ts">
import { SubQuery, SubQueryType, DateConstraint, SubjectNode, NumberConstraint, StringConstraint, SubjectConstraint, BooleanConstraint, QueryProp, NodeState, VectorSort, InstanceQueryProp } from '@/utils/sparql/representation';
import { computed, onBeforeUnmount, onMounted, reactive, useTemplateRef, watch } from 'vue'
import NumberConstraintEditor from './subqueries/NumberConstraintEditor.vue';
import StringConstraintEditor from './subqueries/StringConstraintEditor.vue';
import DateConstraintEditor from './subqueries/DateConstraintEditor.vue';
import SubjectConstraintEditor from './subqueries/SubjectConstraintEditor.vue';
import { DisplayMode, EDITPOINT_R, SUBQUERY_INDENT, type InstanceSelectorOpenEvent } from '@/utils/sparql/helpers';
import BooleanConstraintEditor from './subqueries/BooleanConstraintEditor.vue';
import VectorSubquery from './subqueries/VectorSubquery.vue';
import Property from './subqueries/Property.vue';
import type { NodeDiff } from '@/utils/sparql/diff';
import InstanceProperty from './subqueries/InstanceProperty.vue';
const emit = defineEmits<{
    delete: [value: SubQuery]
    instanceSearchClicked: [value: InstanceSelectorOpenEvent]
}>()
const { extend_path, subquery: subquery, diff } = defineProps({
    extend_path: {
        type: Number,
        required: true
    },
    subquery: {
        type: Object as () => SubQuery,
        required: true
    },
    node: {
        type: Object as () => SubjectNode,
        required: true
    },
    show_editpoints: {
        type: Boolean,
        required: true
    },
    diff: {
        type: Object as () => NodeDiff | null,
        default: null
    },
    mode: {
        type: String as () => DisplayMode,
        default: DisplayMode.SELECT
    },
})
const editor_data = reactive({
    state: null as NodeState | null
})
const updateNodeState = () => {
    if (diff) {
        let diff_node_added = diff.diff_subqueries.added.find((sq) => sq.right.id == subquery.id)
        if (diff_node_added) {
            editor_data.state = NodeState.ADDED
            return
        }
        let diff_node_del = diff.diff_subqueries.removed.find((sq) => sq.left.id == subquery.id)
        if (diff_node_del) {
            editor_data.state = NodeState.REMOVED
            return
        }
        if (diff.diff_subqueries.changed.find((sq) => sq.left.id == subquery.id)) {
            editor_data.state = NodeState.CHANGED
            return
        }
    }
    editor_data.state = NodeState.NORMAL
}
watch(() => diff, () => {
    updateNodeState()
}, { immediate: true, deep: true })
// The content is laid out at its intrinsic size (see .subquery in assets/graph.css) and
// measured, so the box and the node layout (Node.vue) fit around it.
const content_ref = useTemplateRef<HTMLDivElement>('content_ref')
const content_width = computed(() => Math.max(0, subquery.width - SUBQUERY_INDENT))
let observer: ResizeObserver | null = null
const measure = () => {
    const el = content_ref.value
    if (!el || el.offsetWidth == 0 || el.offsetHeight == 0) {
        return
    }
    const width = el.offsetWidth + SUBQUERY_INDENT
    const height = el.offsetHeight
    if (subquery._fit_width != width || subquery._fit_height != height) {
        subquery._fit_width = width
        subquery._fit_height = height
    }
}
onMounted(() => {
    measure()
    if (typeof ResizeObserver !== 'undefined' && content_ref.value) {
        observer = new ResizeObserver(measure)
        observer.observe(content_ref.value)
    }
})
onBeforeUnmount(() => observer?.disconnect())

const query_statestyle = computed(() => {
    // console.log('subject.state', subject.state)
    let state = editor_data.state.toLowerCase()
    if (!state) {
        return ''
    }
    return `node_${state.toLowerCase()}`
})

</script>
