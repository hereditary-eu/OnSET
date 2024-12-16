<template>
    <div class="query_results">
        <h3>Results</h3>
        <div v-if="query_results">
            <div v-for="result in query_results">

            </div>
        </div>
    </div>
</template>
<script setup lang="ts">
import { Api } from '@/api/client.ts/Api';
import { BACKEND_URL } from '@/utils/config';
import { Node } from '@/utils/sparql/representation';
import { ref, watch, reactive, computed, onMounted, defineProps } from 'vue'

const { query_string, root_node } = defineProps({
    query_string: {
        type: String,
        required: true
    },
    root_node: {
        type: Object as () => Node,
        required: true
    }
})
const last_request_id = ref(0)
const query_results = ref(null as Array<Record<string, any>> | null)
const api = new Api({
    baseURL: BACKEND_URL
})
watch(() => query_string, () => {
    (async () => {
        console.log('Query string changed!', query_string)
        last_request_id.value += 1
        const request_id = last_request_id.value
        const response = await api.sparql.sparqlQuerySparqlPost({
            query: query_string
        })
        if (request_id == last_request_id.value) {
            query_results.value = response.data
        }
    })().catch((err) => {
        console.error('Error while querying!', err)
    })
}, { deep: true })

const query_results_mapped = computed(() => {
    if (!query_results.value) {
        return []
    }
    return query_results.value.map((result) => {
        
        
    })
})


</script>
<style lang="scss"></style>