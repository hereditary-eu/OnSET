<template>
    <div class="fuzzy_intermediate" :class="{ non_last_step: !last_one }">
        <h3>{{ erl.message }}</h3>
        <div style="width: 100%; height: 100%;" ref="svg_g_ref">
            <svg width="100%" height="100%">
                <GraphView :store="store" :display-mode="DisplayMode.SELECT" :simulate="state.simulate"
                    :rect="state.bbox" @trigger-interface="state.trigger_sim = $event.trigger"></GraphView>
            </svg>
        </div>
    </div>

</template>
<script setup lang="ts">
import type { Candidates, EnrichedEntitiesRelations, EntitiesRelations } from '@/api/client.ts/Api';
import { DisplayMode, mapERLToStore, NODE_HEIGHT, NODE_WIDTH, OpenEventType } from '@/utils/sparql/helpers';
import { SubQuery, Link, SubjectNode } from '@/utils/sparql/representation';
import { NodeLinkRepository } from '@/utils/sparql/store';
import { compute } from 'three/webgpu';
import { computed, defineProps, onMounted, reactive, useTemplateRef, watch } from 'vue';
import GraphView from './elements/GraphView.vue';
import * as d3 from 'd3'


const svg_g_ref = useTemplateRef('svg_g_ref')
const { erl } = defineProps({
    erl: {
        type: Object as () => EntitiesRelations | Candidates | EnrichedEntitiesRelations,
        required: true
    },
    last_one: {
        type: Boolean,
        default: false
    }
})
const state = reactive({
    bbox: {
        x: 0,
        y: 0,
        width: 0,
        height: 0
    },
    simulate: false,
    trigger_sim: null as (() => void) | null
})
onMounted(() => {
    state.bbox = svg_g_ref.value.getBoundingClientRect()
    state.simulate = true
    if (state.trigger_sim) {
        state.trigger_sim()
    }
})
const store = computed(() => {
    return mapERLToStore(erl)
})
watch(() => store.value, () => {
    state.simulate = true
    if (state.trigger_sim) {
        state.trigger_sim()
    }
}, { deep: false, flush: 'post' })
</script>
<style scoped>
.fuzzy_intermediate {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    width: 40vw;
    height: 20vh;
    padding: 2rem;
}

.non_last_step {
    border-right: 1px solid #8fa88f;
}
</style>