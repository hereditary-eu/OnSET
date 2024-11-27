<template>
    <g :transform="`translate(${subject.x},${subject.y})`">
        <rect :width="`${subject.width}px`" :height="`${subject.height}px`" class="node">
        </rect>
        <text :x="`${subject.width/2}px`" :y="`${subject.height/2}px`" class=node_text>
            {{ subject.label }}
        </text>
    </g>
</template>
<script setup lang="ts">
import { ref, watch, reactive, computed, onMounted, defineProps } from 'vue'
import { type Subject } from '@/api/client.ts/Api';
import type { Node } from '@/utils/sparql/representation';
const { subject } = defineProps({
    subject: {
        type: Object as () => Node,
        required: true
    },
})
</script>
<style lang="scss">
.node {
    cursor: pointer;
    fill: #ccc;
    stroke: #000;
    stroke-width: 1.5px;

}
.node_text {
    font: 10px sans-serif;
    text-anchor: middle;
}
</style>