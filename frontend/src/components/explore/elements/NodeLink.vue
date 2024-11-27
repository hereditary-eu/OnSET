<template>
    <g>
        <Node :subject="link.from_subject"></Node>
        <LinkComp :link="link"></LinkComp>
        <Node v-if="link.to_subject && !link.to_subject.unknown" :subject="link.to_subject"></Node>
    </g>
</template>
<script setup lang="ts">
import type { Link } from '@/utils/sparql/representation';
import { ref, watch, reactive, computed, onMounted } from 'vue'
import Node from './Node.vue';
import LinkComp from './Link.vue';
const { link } = defineProps({
    link: {
        type: Object as () => Link,
        required: true
    }
})


</script>
<style lang="scss"></style>