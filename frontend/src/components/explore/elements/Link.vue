<template>
    <g v-if="from && to" @mouseout.capture="editPointHover($event, false)"
        @mouseenter.capture="editPointHover($event, true)" @mouseover="editPointHover($event, true)">
        <!-- invisible hover area around the link and its label -->
        <rect :x="extent.x" :y="extent.y - LABEL_HOVER_PAD" :width="extent.width"
            :height="extent.height + LABEL_HOVER_PAD" fill="transparent" />
        <defs>
            <marker :id="marker_id" viewBox="0 0 10 10" refX="9" refY="5" :markerWidth="marker_size" :markerHeight="marker_size"
                markerUnits="userSpaceOnUse" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" class="link_arrow" :class="link_statestyle" />
            </marker>
        </defs>
        <path :d="geometry.d" class="link_path" :class="[link_statestyle, { link_empty: strength.empty }]"
            :style="{ strokeWidth: strength.width }" :marker-end="`url(#${marker_id})`">
            <title v-if="count_title">{{ count_title }}</title>
        </path>
        <g :transform="`translate(${text_attach_pt.x},${text_attach_pt.y})`">
            <text :y="-4" class="link_text" :class="{ link_text_empty: strength.empty }"
                :style="{ fontWeight: strength.weight > 0.66 ? 600 : undefined }">{{ label }}<title
                    v-if="count_title">{{ count_title }}</title></text>
            <g v-if="mode == DisplayMode.EDIT" v-show="editor_data.show_editpoints">
                <circle :cx="0" :cy="EDITPOINT_R + 2" :r="EDITPOINT_R" class="edit_point"
                    @click="emit('linkEditClicked', { side: OpenEventType.LINK, link: link, evt: $event })" />
                <text :x="EDITPOINT_R + 3" :y="EDITPOINT_R + 2" class="help_text_right">Edit</text>

                <circle :cx="0" :cy="-(EDITPOINT_R + 16)" :r="EDITPOINT_R" @mouseover="hoverDeletion(true)"
                    @mouseout="hoverDeletion(false)" class="edit_point edit_point_delete" @click="doDeletion()" />
                <text :x="EDITPOINT_R + 3" :y="-(EDITPOINT_R + 16)" class="help_text_right">Delete</text>
            </g>
        </g>
    </g>
</template>
<script setup lang="ts">
import type { NodeLinkRepositoryDiff } from '@/utils/sparql/diff';
import { DisplayMode, EDITPOINT_R, extentNodes, OpenEventType, type SelectorOpenEvent } from '@/utils/sparql/helpers';
import type { InstanceLink } from '@/utils/sparql/querymapper';
import { NodeState, type Link } from '@/utils/sparql/representation';
import type { NodeLinkRepository } from '@/utils/sparql/store';
import { LINK_COUNTS_KEY, linkStrength } from '@/utils/sparql/link-strength';
import { watch, reactive, computed, onMounted, useId, inject } from 'vue'

// extra hover area above the link for its label and edit handles
const LABEL_HOVER_PAD = 30

const emit = defineEmits<{
    (e: 'linkEditClicked', value: SelectorOpenEvent): void
}>();

const { link, store, diff, circular, mode } = defineProps({
    link: {
        type: Object as () => Link,
        required: true
    },
    store: {
        type: Object as () => NodeLinkRepository,
        required: true
    },
    diff: {
        type: Object as () => NodeLinkRepositoryDiff | null,
        default: null
    },
    circular: {
        type: Boolean,
        default: false
    },
    mode: {
        type: String as () => DisplayMode,
        default: DisplayMode.SELECT
    }
})

let editor_data = reactive({
    show_editpoints: false,
    hover_deletion: false,
    state: NodeState.NORMAL,
})
let extent = computed(() => {
    if (circular_detected.value) {
        // the loop on the right side of the node
        const k = store.parallelIndex(link)
        return {
            x: from.value.x + from.value.width,
            y: from.value.y - 30,
            width: 70 + k * 28,
            height: from.value.height + 60,
        }
    }
    return extentNodes([from.value, to.value])
})
let from = computed(() => {
    let from_node = store.from(link)
    if (!from_node) {
        return diff?.diff_nodes.removed.find(n => n.left.internal_id == link.from_internal_id)?.left
    }
    return from_node
})
let to = computed(() => {
    let to_node = store.to(link)
    if (!to_node) {
        return diff?.diff_nodes.removed.find(n => n.left.internal_id == link.to_internal_id)?.left
    }
    return to_node
})
let label = computed(() => {
    if (mode == DisplayMode.RESULTS || mode == DisplayMode.RESULT_INTERACTIVE) {
        return (link as InstanceLink).instance_label || (link as InstanceLink).instance_id || ''
    }
    let quantifier = link.quantifier ? link.quantifier.toString() : ''
    let text = link.label || ''
    if (link.allow_arbitrary) {
        text = `(any)`
    }
    return text + quantifier
})
let same_links = computed(() => {
    let all_links = store.sameLinks(link)
    let my_id = all_links.findIndex(l => l.id == link.id)
    return {
        links: all_links,
        my_id: my_id,
        count: all_links.length,
    }
})
let circular_detected = computed(() => {
    return from.value.internal_id == to.value.internal_id || circular
})
// directed bezier from the subject to the object node, ending on the object's border at the arrow
// (the nodes may come from the diff, so they are passed explicitly)
let geometry = computed(() => store.linkGeometry(link, circular, from.value, to.value)!)
let text_attach_pt = computed(() => geometry.value.label)
// one arrow marker per link, so it takes the link's state colour (ids must be unique in the page)
const marker_id = `link_arrow_${useId()}`

const editPointHover = (event: MouseEvent, state: boolean) => {
    editor_data.show_editpoints = state
}
const hoverDeletion = (state: boolean) => {
    editor_data.hover_deletion = state
}
const doDeletion = () => {
    store.removeLink(link)
}

watch(() => diff, () => {
    updateLinkState()
}, { deep: true })
onMounted(() => {
    // console.log('Link', link)
    updateLinkState()
})
// live triple counts of the view (the ontology builder's KG), else the link's stored instance count
const link_counts = inject(LINK_COUNTS_KEY, null)
const live_count = computed(() => {
    if (!link_counts?.value || link.allow_arbitrary || mode == DisplayMode.RESULTS || mode == DisplayMode.RESULT_INTERACTIVE) {
        return undefined
    }
    return link_counts.value.count(from.value?.subject_id ?? link.from_id, link.property_id, to.value?.subject_id ?? link.to_id)
})
const strength = computed(() => live_count.value !== undefined
    ? linkStrength(live_count.value, link_counts!.value!.max)
    : linkStrength(link.instance_count))
const count_title = computed(() => live_count.value !== undefined
    ? `${live_count.value} triple${live_count.value == 1 ? '' : 's'} in the knowledge graph` : '')
// the arrowhead grows with the stroke (userSpaceOnUse: 8 at the thinnest)
const marker_size = computed(() => 6.5 + 1.5 * strength.value.width)

const updateLinkState = () => {
    if (diff) {
        let diff_link_added = diff.diff_links.added.find(l => l.right?.identifier() == link.identifier())
        let diff_link_removed = diff.diff_links.removed.find(l => l.left?.identifier() == link.identifier())
        if (diff_link_added) {
            editor_data.state = NodeState.ADDED
            return
        } else if (diff_link_removed) {
            editor_data.state = NodeState.REMOVED
            return
        }

    }
    editor_data.state = NodeState.NORMAL
}
const link_statestyle = computed(() => {
    // console.log('subject.state', subject.state)
    let state = editor_data.state.toLowerCase()
    if (!state) {
        return ''
    }
    return `link_${state.toLowerCase()}`
})
</script>
