<template>
    <g v-if="from && to" @mouseout.capture="editPointHover($event, false)"
        @mouseenter.capture="editPointHover($event, true)" @mouseover="editPointHover($event, true)">
        <!-- invisible hover area around the link and its label -->
        <rect :x="extent.x" :y="extent.y - LABEL_HOVER_PAD" :width="extent.width"
            :height="extent.height + LABEL_HOVER_PAD" fill="transparent" />
        <path v-if="circular_detected" :d="`M ${from.x + from.width},${from.y + from.height / 2}
                C ${to.x + to.width * 2},${to.y + to.height / 2}
                ${to.x + to.width * 2},${to.y - to.height * 2}
                ${to.x + to.width},${to.y - to.height * 2}
                L ${to.x},${to.y - to.height * 2}
                C ${from.x - from.width},${to.y - from.height * 2}
                ${from.x - from.width},${to.y + from.height / 2}
                ${from.x},${to.y + from.height / 2}`" class="link_path" :class="link_statestyle"
            :style="{ strokeWidth: link_width }" />
        <path v-else :d="`M ${from.x + from.width},${from.y + from.height / 2}
                C ${to.x},${from.y + from.height / 2}
                ${from.x + from.width},${to.y + to.height / 2}
                ${to.x},${to.y + to.height / 2}`" class="link_path" :class="link_statestyle"
            :style="{ strokeWidth: link_width }" />
        <g :transform="`translate(${text_attach_pt.x},${text_attach_pt.y})`">
            <text :y="-4" class="link_text">{{ label }}</text>
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
import { watch, reactive, computed, onMounted } from 'vue'

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
        return {
            x: from.value.x - from.value.width,
            y: from.value.y - from.value.height * 2,
            width: from.value.width * 3,
            height: from.value.height * 2,
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
let text_attach_pt = computed(() => {
    return store.textAttachPoint(link, circular)
})

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
const link_width = computed(() => {
    return Math.log10(link.instance_count + 1) + 1
})

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
