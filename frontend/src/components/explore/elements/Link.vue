<template>
    <g>
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
import type { Link } from '@/utils/sparql/representation';
import type { NodeLinkRepository } from '@/utils/sparql/store';
import { ref, watch, reactive, computed, onMounted, defineProps } from 'vue'

const { link, store } = defineProps({
    link: {
        type: Object as () => Link,
        required: true
    },
    store: {
        type: Object as () => NodeLinkRepository,
        required: true
    }
})
let from = computed(() => store.from(link))
let to = computed(() => store.to(link))
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