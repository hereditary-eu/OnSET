<template>
    <Expandable v-model="expanded">
        <template v-slot:header>
            {{ store.nodes[0].instance_label }}
            <!-- in the ontology builder: the source documents of the result's instances -->
            <span v-if="inspect" class="miniature_sources">
                <OnsetBtn v-for="node in instanceNodes" :key="node.instance_id" size="small" :toggleable="false"
                    icon="mdi-file-document-outline" :title="`Source documents of ${node.instance_label}`"
                    @click="inspect(bareIri(node.instance_id))">{{ node.instance_label }}</OnsetBtn>
            </span>
        </template>
        <template v-slot:content>
            <!-- centred in the window on its own transform (the miniature's is scaled to the small trigger) -->
            <svg class="fill_svg" ref="expanded_svg">
                <g :transform="`translate(${expanded_view.offset.x},${expanded_view.offset.y}) scale(${expanded_view.scale})`">
                    <g ref="expanded_graph">
                        <GraphView :store="view_store" :display-mode="DisplayMode.RESULT_INTERACTIVE"
                            :viewport-state="expanded_view"
                            @prop-point-clicked="ui_state.prop_open_event = $event; ui_state.prop_open = true"></GraphView>
                    </g>
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
import { ref, reactive, computed, inject, nextTick, onBeforeUnmount, onMounted, watch, type Ref } from 'vue'
import OnsetBtn from '../../ui/OnsetBtn.vue';
import { INSPECT_INSTANCE } from '@/utils/builder/api';
import Propview from '../elements/panels/Propview.vue';
import { PropertiesOpenEvent, scalingFactors, type InstanceNodeLinkRepository } from '@/utils/sparql/querymapper';
import { type Vector2Like } from 'three';
import { DisplayMode } from '@/utils/sparql/helpers';
import Expandable from '../../ui/Expandable.vue';
import GraphView from '../elements/GraphView.vue';
import type { NodeLinkRepositoryDiff } from '@/utils/sparql/diff';
import { MiniatureType } from '@/utils/result-plot/plot-types';
import { centerTransform, nodesBox } from '@/utils/sparql/fit';
import { ViewPortState } from '@/utils/editing';
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
// provided by the ontology builder only
const inspect = inject(INSPECT_INSTANCE, null)
// result instance ids are SPARQL terms (<http://…>), the sources panel takes the plain IRI
const bareIri = (id: string) => id.replace(/^<(.*)>$/, '$1')
const instanceNodes = computed(() => {
    const seen = new Set<string>()
    return store.nodes.filter((n) => n.instance_id && !seen.has(n.instance_id) && seen.add(n.instance_id))
})
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
// --- the expanded result: centred in the visible window, shrunk if it does not fit; refitted when the
// window opens or resizes and when the result changes (e.g. re-run while the KG grows), not while dragging ---
const EXPANDED_PADDING = 24
const expanded_svg = ref<SVGSVGElement | null>(null)
const expanded_graph = ref<SVGGElement | null>(null)
const expanded_view = reactive(new ViewPortState(1, { x: 0, y: 0 }))

function centerExpanded() {
    const svg = expanded_svg.value
    if (!svg) {
        return
    }
    const rect = svg.getBoundingClientRect()
    // the rendered extent (labels, constraints) in graph coordinates, the nodes' boxes before it is rendered
    let box = null as { x: number, y: number, width: number, height: number } | null
    try {
        const b = expanded_graph.value?.getBBox()
        box = b && (b.width > 0 || b.height > 0) ? b : null
    } catch {
        box = null
    }
    const { offset, scale } = centerTransform(box ?? nodesBox(store.nodes), rect, EXPANDED_PADDING)
    expanded_view.offset = offset
    expanded_view.scale = scale
}
const refitExpanded = async () => {
    await nextTick()
    centerExpanded()
    // node sizes are measured once rendered
    requestAnimationFrame(centerExpanded)
}

// the window's size is only known once it is laid out, and changes with the browser window
const resize_observer = typeof ResizeObserver != 'undefined'
    ? new ResizeObserver((entries) => {
        for (const entry of entries) {
            if (entry.target == expanded_svg.value) {
                centerExpanded()
            } else {
                rescaleToFit()
            }
        }
    })
    : null
watch(expanded_svg, (el, old) => {
    if (old) {
        resize_observer?.unobserve(old)
    }
    if (el) {
        resize_observer?.observe(el)
        refitExpanded()
    }
})

watch(() => store, (new_entry) => {
    rescaleToFit()
    if (expanded.value) {
        refitExpanded()
    }
})
onMounted(() => {
    rescaleToFit()
    if (svg_ref.value) {
        resize_observer?.observe(svg_ref.value)
    }
})
onBeforeUnmount(() => resize_observer?.disconnect())

</script>
<style scoped>
.miniature_sources {
    display: inline-flex;
    flex-wrap: wrap;
    gap: var(--space-1);
    margin-left: var(--space-2);
    cursor: default;
}
</style>
