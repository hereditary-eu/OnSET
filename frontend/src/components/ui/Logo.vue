<template>
    <Loading :height="height" :fixed="true" />
</template>
<script setup lang="ts">

import { ref } from 'vue'
import Loading from './Loading.vue';

// height of the animation; the width follows from the aspect ratio
const { height } = defineProps({
    height: {
        type: String,
        default: "1rem"
    }
})
</script>
<style lang="scss" scoped></style>
