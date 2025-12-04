<template>
    <g v-if="from && to" @mouseout.capture="editPointHover($event, false)"
        @mouseenter.capture="editPointHover($event, true)" @mouseover="editPointHover($event, true)">
        <rect :x="`${extent.x}px`" :y="`${extent.y - 30}px`" :width="`${extent.width}px`"
            :height="`${extent.height + 30}px`" fill="transparent">
        </rect>
        <g v-if="circular_detected">
            <path :d="`M ${from.x + from.width},${from.y + from.height / 2} 
                C ${to.x + to.width * 2},${to.y + to.height / 2} 
                ${to.x + to.width * 2},${to.y - to.height * 2} 
                ${to.x + to.width},${to.y - to.height * 2}
                L ${to.x},${to.y - to.height * 2}
                C ${from.x - from.width},${to.y - from.height * 2} 
                ${from.x - from.width},${to.y + from.height / 2} 
                ${from.x},${to.y + from.height / 2}`" fill="none" stroke="#f00" class="link_path"
                :class="link_statestyle"></path>
        </g>
        <g v-else>
            <path :d="`M ${from.x + from.width},${from.y + from.height / 2} 
                C ${to.x},${from.y + from.height / 2} 
                ${from.x + from.width},${to.y + to.height / 2} 
                ${to.x},${to.y + to.height / 2}`" fill="none" stroke="#666" class="link_path" :class="link_statestyle">
            </path>
        </g>
        <g :transform="`translate(${text_attach_pt.x},${text_attach_pt.y})`">
            <!-- <circle :cx="text_attach_pt.x" :cy="text_attach_pt.y" :r="link_width" class="link_text_circle"></circle> -->

            <text :x="`${- 5}px`" :y="`${- 5}px`" fill="#000" class="link_text">{{
                label
            }}</text>
            <g v-show="mode == DisplayMode.EDIT && editor_data.show_editpoints">
                <circle :cx="0" :cy="10" :r="editor_data.editpoint_r" class="edit_point"
                    @click="emit('linkEditClicked', { side: OpenEventType.LINK, link: link, evt: $event })">
                </circle>
                <text :x="`${20}px`" :y="`10px`" class="help_text_right">Edit</text>

                <circle :cx="0" :cy="-25" :r="editor_data.editpoint_r" @mouseover="hoverDeletion(true)"
                    @mouseout="hoverDeletion(false)" class="edit_point edit_point_delete" @click="doDeletion()">
                </circle>
                <text :x="`${20}px`" :y="`-25px`" class="help_text_right">Delete</text>
            </g>
        </g>
    </g>
</template>
<script setup lang="ts">
import type { NodeLinkRepositoryDiff } from '@/utils/sparql/diff';
import { DisplayMode, extentNodes, OpenEventType, type SelectorOpenEvent } from '@/utils/sparql/helpers';
import type { InstanceLink } from '@/utils/sparql/querymapper';
import { NodeState, type Link } from '@/utils/sparql/representation';
import type { NodeLinkRepository } from '@/utils/sparql/store';
import { ref, watch, reactive, computed, onMounted, defineProps } from 'vue'

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
    editpoint_r: 7,
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

watch(() => link, () => {
}, { deep: true })
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
<style lang="scss">
.link_text {
    font-size: 10px;
    text-anchor: middle;
    text-align: center;
}

.link_path {
    fill: none;
    stroke: #cccccc;
    stroke-width: v-bind("link_width");
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

@mixin help_text($anchor: middle, $baseline: 0.5em) {
    font-size: 10px;
    text-anchor: $anchor;
    dominant-baseline: central;
}

.help_text_right {
    @include help_text(start);
}

.help_text_bottom {
    @include help_text(middle, -0.5em);
}
</style>