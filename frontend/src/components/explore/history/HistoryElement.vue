<template>
    <div class="history_instance_element" @mouseover.capture="ui_state.hover_actions = true"
        @mouseleave.capture="ui_state.hover_actions = false">
        <div class="toolbar history_edit_btns" v-show="ui_state.hover_actions">
            <OnsetBtn @click="emit('revert', entry)" size="small" :toggleable="false" icon="mdi-undo">Revert</OnsetBtn>
            <OnsetBtn @click="emit('compare', entry)" size="small" :toggleable="false" icon="mdi-compare">Compare
            </OnsetBtn>
        </div>
        <svg class="fill_svg" ref="svg_ref">
            <g :transform="`translate(${entry.offset.x},${entry.offset.y}) scale(${entry.scale})`">
                <GraphView :store="entry.query" :display-mode="DisplayMode.SELECT" :diff="entry.previous_diff">
                </GraphView>
            </g>
        </svg>
    </div>
</template>
<script setup lang="ts">
import { onMounted, ref, watch, type Ref } from 'vue'
import { DisplayMode } from '@/utils/sparql/helpers';
import GraphView from '../elements/GraphView.vue';
import type { HistoryEntry } from '@/utils/sparql/history';
import OnsetBtn from '@/components/ui/OnsetBtn.vue';
const svg_ref = ref('') as unknown as Ref<HTMLElement>

const { entry } = defineProps({
    entry: {
        type: Object as () => HistoryEntry,
        required: true
    },
})

const ui_state = ref({
    hover_actions: false,
})

const emit = defineEmits<{
    revert: [HistoryEntry],
    compare: [HistoryEntry]
}>()

function rescaleToFit() {
    if (!svg_ref.value) {
        return
    }
    let rect = svg_ref.value.getBoundingClientRect()
    // console.log("SVG ref", svg_ref, rect.width, rect.height, entry);
    if (svg_ref && rect.width > 0 && rect.height > 0) {
        entry.rescale({
            x: rect.width,
            y: rect.height
        })
    }
}
watch(() => entry, (new_entry) => {
    console.log("History entry changed", new_entry)
    rescaleToFit()
})
onMounted(() => {
    setTimeout(() => {
        rescaleToFit()
    }, 100)
})
</script>
<style scoped>
.history_instance_element {
    position: relative;
    flex: 0 0 auto;
    width: 100%;
    height: 6rem;
    padding: var(--space-1);
    border-bottom: 1px solid var(--c-border);
    cursor: pointer;
}

.history_edit_btns {
    position: absolute;
    top: var(--space-1);
    right: var(--space-1);
    z-index: 1;
}
</style>
