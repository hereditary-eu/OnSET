<template>
    <div class="constraint">
        <span class="constraint_label">{{ constraint.link.label }}</span>
        <input type="checkbox" v-model="constraint.value">
    </div>
</template>
<script setup lang="ts">
import { BooleanConstraint } from '@/utils/sparql/representation';

const { constraint } = defineProps({
    constraint: {
        type: Object as () => BooleanConstraint,
        required: true
    }
})
</script>
