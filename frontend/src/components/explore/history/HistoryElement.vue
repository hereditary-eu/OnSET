<template>
    <div>
        <svg class="result_interact_svg" ref="svg_ref">
            <g :transform="`translate(${entry.offset.x},${entry.offset.y}) scale(${entry.scale})`">
                <GraphView :store="entry.query" :display-mode="DisplayMode.SELECT" :diff="entry.previous_diff">
                </GraphView>
            </g>
        </svg>
    </div>
</template>
<script setup lang="ts">
import { defineProps, onMounted, ref, type Reactive, type Ref } from 'vue'
import { type Vector2Like } from 'three';
import { DisplayMode } from '@/utils/sparql/helpers';
import GraphView from '../elements/GraphView.vue';
import type { NodeLinkRepositoryDiff } from '@/utils/sparql/diff';
import type { NodeLinkRepository } from '@/utils/sparql/store';
import type { HistoryEntry } from '@/utils/sparql/history';
const svg_ref = ref('') as unknown as Ref<HTMLElement>
const { entry } = defineProps({
    entry: {
        type: Object as () => HistoryEntry,
        required: true
    },
})

onMounted(() => {
    setTimeout(() => {
        console.log("Mounted history element", svg_ref)
        let rect = svg_ref.value.getBoundingClientRect()
        console.log("SVG ref", svg_ref, rect.width, rect.height, entry);
        if (svg_ref && rect.width > 0 && rect.height > 0) {
            entry.rescale({
                x: rect.width,
                y: rect.height
            })
        }
    }, 100)
})
</script>
<style lang="scss">
.history_instance_container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    width: 100%;
    height: 100%;
    overflow: auto;
    padding: 5px;
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
