<template>
    <div class="history_instance_element" @mouseover.capture="ui_state.hover_actions = true"
        @mouseleave.capture="ui_state.hover_actions = false">
        <div class="history_edit_btns" v-show="ui_state.hover_actions">
            <OnsetBtn @click="emit('revert', entry)" :btn_height="'1.3rem'" :btn_width="'8rem'" :toggleable="false">Revert
            </OnsetBtn>
            <OnsetBtn @click="emit('compare', entry)" v-show="ui_state.hover_actions" :btn_height="'1.3rem'"
                :btn_width="'8rem'" :toggleable="false">Compare
            </OnsetBtn>
        </div>
        <svg class="result_interact_svg" ref="svg_ref">
            <g :transform="`translate(${entry.offset.x},${entry.offset.y}) scale(${entry.scale})`">
                <GraphView :store="entry.query" :display-mode="DisplayMode.SELECT" :diff="entry.previous_diff">
                </GraphView>
            </g>
        </svg>
    </div>
</template>
<script setup lang="ts">
import { defineProps, onMounted, ref, watch, type Ref } from 'vue'
import { DisplayMode } from '@/utils/sparql/helpers';
import GraphView from '../elements/GraphView.vue';
import type { HistoryEntry, QueryHistory } from '@/utils/sparql/history';
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
<style lang="scss" scoped>
.history_edit_btns {
    position: absolute;
    top: 5px;
    right: 5px;
    display: flex;
    flex-direction: row;
    gap: 5px;
    z-index: 150;
}

.history_instance_element {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    width: 100%;
    height: 100%;
    overflow: auto;
    padding: 5px;
    border-bottom: 1px solid rgb(192, 213, 191);
    position: relative;
    cursor: pointer;
}

.result_instance_element {
    width: 100%;
    height: 20%;
    display: flex;
    justify-content: center;
    align-items: center;
    margin: 4px;
}

.result_instance_svg {
    width: 100%;
    height: 100%;
}

.result_interact_svg {
    width: 100%;
    height: 100%;
}

.result_instance_header {
    font-size: 1.5rem;
    font-weight: bold;
    padding: 5px;
    border-bottom: 1px solid rgb(192, 213, 191);
    width: 100%;
}

.result_instance_overview_header {
    font-size: 2rem;
}
</style>
