<template>
    <!-- Example query graphs (from the LLM query generation examples) to start exploring from. -->
    <div class="example_queries">
        <Loading v-if="state.loading" height="1.5rem"></Loading>
        <span v-else-if="state.examples.length == 0" class="message">No examples available.</span>
        <span class="chip" v-for="example in state.examples" @click="select(example)">
            {{ example.message }}
        </span>
    </div>
</template>
<script setup lang="ts">
import { onMounted, reactive } from 'vue'
import type { EnrichedEntitiesRelations } from '@/api/client.ts/Api'
import Loading from '../ui/Loading.vue'
import { MixedResponse } from '@/utils/sparql/store'
import { mapERLToStore } from '@/utils/sparql/helpers'
import { api } from '@/utils/api'

const emit = defineEmits<{
    select: [value: MixedResponse]
}>()

const state = reactive({
    loading: false,
    examples: [] as EnrichedEntitiesRelations[],
})

onMounted(() => {
    state.loading = true
    api.classes.getLlmExamplesClassesSearchLlmExamplesGet()
        .then((response) => { state.examples = response.data })
        .catch(console.error)
        .finally(() => { state.loading = false })
})

const select = (example: EnrichedEntitiesRelations) => {
    const response = new MixedResponse()
    response.store = mapERLToStore(example)
    emit('select', response)
}
</script>
<style scoped>
.example_queries {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1);
    max-height: 12rem;
    overflow-y: auto;
}
</style>
