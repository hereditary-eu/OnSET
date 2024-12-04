<template>
    <g>
        <path :d="`M ${link.from_subject.x + link.from_subject.width},${link.from_subject.y + link.from_subject.height / 2} 
                C ${link.to_subject.x},${link.from_subject.y + link.from_subject.height / 2} 
                ${link.from_subject.x + link.from_subject.width},${link.to_subject.y + link.to_subject.height / 2} 
                ${link.to_subject.x},${link.to_subject.y + link.to_subject.height / 2}`" fill="none" stroke="#666"
            class="link_path"></path>
        <text :x="`${(link.from_subject.x + link.from_subject.width + link.to_subject.x) / 2}px`"
            :y="`${-5 + (link.from_subject.y + link.from_subject.height / 2 + link.to_subject.y + link.to_subject.height / 2) / 2}px`"
            fill="#000" class="link_text">{{ link.label
            }}</text>
    </g>
</template>
<script setup lang="ts">
import type { Link } from '@/utils/sparql/representation';
import { ref, watch, reactive, computed, onMounted, defineProps } from 'vue'

const { link } = defineProps({
    link: {
        type: Object as () => Link,
        required: true
    },
})

watch(() => link, () => {
}, { deep: true })
onMounted(() => {
    // console.log('Link', link)
})
</script>
<style lang="scss">
.link_text {
    font: 10px sans-serif;
    text-anchor: middle;
    text-align: center;
}
.link_path {
    fill: none;
    stroke: #828282;
    stroke-width: 1px;
}
</style>