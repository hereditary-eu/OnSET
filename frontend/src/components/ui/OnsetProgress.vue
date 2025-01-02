<template>
    <div class="progress_bar" ref="svg_wrapper">
        <svg width="100%" height="100%">
            <rect :width="`${state.bbox.width}`" :height="`${state.bbox.height}`" class="background_rect"></rect>
            <rect :width="`${state.bbox.width * progress / max}`" :height="`${state.bbox.height}`"
                class="progress_rect"></rect>
        </svg>
    </div>
</template>
<script setup lang="ts">
import { onMounted, onUpdated, reactive, useTemplateRef } from 'vue';
const svgwrapperRef = useTemplateRef('svg_wrapper')

const { progress } = defineProps({
    progress: {
        type: Number,
        required: true
    },
    max: {
        type: Number,
        required: false,
        default: 100
    },
    height: {
        type: String,
        required: false,
        default: '1rem'
    },
})
const state = reactive({
    bbox: {
        x: 0,
        y: 0,
        width: 0,
        height: 0
    }
})
onMounted(() => {
    console.log('bbox', svgwrapperRef)
    state.bbox = svgwrapperRef.value.getBoundingClientRect()
    console.log('bbox', state.bbox)
})
</script>
<style lang="css">
.background_rect {
    fill: #efefef;
    transition: width 0.5s;
}

.progress_rect {
    fill: #99c993;
    transition: width 0.5s;
}

.progress_bar {
    width: 100%;
    height: v-bind("height");
    overflow: hidden;
}
</style>