<template>
    <div class="constraint">
        <OnsetIcon icon="mdi-tag" />
        <span class="constraint_label">{{ query.link.label }}</span>
    </div>
</template>
<script setup lang="ts">
import { QueryProp } from '@/utils/sparql/representation';
import OnsetIcon from '@/components/ui/OnsetIcon.vue';

const { query } = defineProps({
    query: {
        type: Object as () => QueryProp,
        required: true
    }
})
</script>
