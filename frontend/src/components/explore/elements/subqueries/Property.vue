<template>
    <div class="query">
        <span> <v-icon icon="mdi-tag"></v-icon>
        </span>
        <span class="query_label">{{ query.link.label }}</span>
    </div>
</template>
<script setup lang="ts">
import { QueryProp } from '@/utils/sparql/representation';
import { defineProps, defineModel, computed } from 'vue'

const { query } = defineProps({
    query: {
        type: Object as () => QueryProp,
        required: true
    }
})
</script>
<style lang="scss" scoped>
.query_label {
    margin-right: 5px;
}

.query_select {
    margin-right: 5px;
    border: rgb(105, 132, 99) 1px solid;
    border-radius: 0px;

}
</style>
