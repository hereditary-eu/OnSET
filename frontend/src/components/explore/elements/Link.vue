<template>
    <g v-if="from && to">
        <path :d="`M ${from.x + from.width},${from.y + from.height / 2} 
                C ${to.x},${from.y + from.height / 2} 
                ${from.x + from.width},${to.y + to.height / 2} 
                ${to.x},${to.y + to.height / 2}`" fill="none" stroke="#666" class="link_path"></path>
        <text :x="`${(from.x + from.width + to.x) / 2}px`"
            :y="`${-5 + (from.y + from.height / 2 + to.y + to.height / 2) / 2}px`" fill="#000" class="link_text">{{
                link.label
            }}</text>
    </g>
</template>
<script setup lang="ts">
import type { NodeLinkRepositoryDiff } from '@/utils/sparql/diff';
import type { Link } from '@/utils/sparql/representation';
import type { NodeLinkRepository } from '@/utils/sparql/store';
import { ref, watch, reactive, computed, onMounted, defineProps } from 'vue'

const { link, store, diff } = defineProps({
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
    }
})
let from = computed(() => {
    let from_node = store.from(link)
    if (!from_node) {
        return diff?.diff_nodes.removed.find(n => n.internal_id == link.from_internal_id)
    }
    return from_node
})
let to = computed(() => {
    let to_node = store.to(link)
    if (!to_node) {
        return diff?.diff_nodes.removed.find(n => n.internal_id == link.to_internal_id)
    }
    return to_node
})
watch(() => link, () => {
}, { deep: true })
onMounted(() => {
    // console.log('Link', link)
})
const link_width = computed(() => {
    return Math.log10(link.instance_count + 1) + 1
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
</style>