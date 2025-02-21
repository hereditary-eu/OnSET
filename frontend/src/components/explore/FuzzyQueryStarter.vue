<template>
    <div class="fuzzy_query_starter">
        <div class="input_step">
            <h3>Enter your query:</h3>
            <div class="fuzzy_query_input_row">
                <input type="text" v-model="state.query_string" @keypress="submit_query" class="query_input" />
                <OnsetBtn @click="submit_query" :toggleable="false">Search</OnsetBtn>
            </div>
            <div v-if="state.loading && state.updated_query" class="input_step">
                <Loading></Loading>
                <OnsetProgress :progress="state.updated_query.progress" :max="state.updated_query.max_steps">
                </OnsetProgress>
                <h3>{{ state.updated_query.message }}</h3>
            </div>
            <div v-if="updated_steps && state.updated_query.relations_steps.length > 0" class="query_steps">
                <FuzzyQueryIntermediate :erl="step" v-for="step in updated_steps"
                    :last_one="step == updated_steps[updated_steps.length - 1]">
                </FuzzyQueryIntermediate>
            </div>

            <h3>Example queries:</h3>
            <Loading v-if="state.loading_example_queries"></Loading>
            <div class="example_query_box">
                <div class="example_query" v-for="example in state.example_queries" @click="selected_example(example)">
                    {{ example.message }}
                </div>
            </div>
        </div>

    </div>

</template>

<script setup lang="ts">
import { Api, type Candidates, type QueryProgress, type EntitiesRelations, type EnrichedEntitiesRelations } from '@/api/client.ts/Api';
import { BACKEND_URL } from '@/utils/config';
import { ref, watch, reactive, computed, onMounted, onBeforeMount } from 'vue'
import OnsetProgress from '../ui/OnsetProgress.vue';
import OnsetBtn from '../ui/OnsetBtn.vue';
import { MixedResponse, NodeLinkRepository } from '@/utils/sparql/store';
import { mapERLToStore, NodeSide } from '@/utils/sparql/helpers';
import Loading from '../ui/Loading.vue';
import FuzzyQueryIntermediate from './FuzzyQueryIntermediate.vue';
const emit = defineEmits<{
    query_complete: [value: MixedResponse]
}>()

const state = reactive({
    query_string: 'the birthplace of a ceo of a company',
    running_query: null as QueryProgress | null,
    updated_query: null as QueryProgress | null,
    running_timer: null as number | null,
    loading: false,
    loading_example_queries: false,
    example_queries: [] as EnrichedEntitiesRelations[]
})
const api = new Api({
    baseURL: BACKEND_URL
})

onMounted(() => {
    // state.running_query = {
    //     id: "query:2:2025-01-03T13:24:59.302482",
    //     progress: 2,
    //     max_steps: 10,
    //     message: "TEST QUERY",
    //     start_time: "2025-01-03T09:34:26.189876",
    // }

    (async () => {
        const response = await api.classes.getLlmExamplesClassesSearchLlmExamplesGet()
        state.example_queries = response.data
        state.loading_example_queries = false
    })().catch((e) => {
        console.error(e)
        state.loading_example_queries = false
    })
    state.loading_example_queries = true
})

watch(() => state.running_query, (new_val) => {
    if (state.running_query) {
        if (state.running_timer) clearInterval(state.running_timer)
        state.running_timer = setInterval(() => {
            console.log('Running query', state.running_query.id);
            (async () => {
                const response = await api.classes.getLlmResultsRunningClassesSearchLlmRunningGet({
                    query_id: state.running_query.id
                })
                if (!state.updated_query
                    || state.updated_query.relations_steps.length != response.data.relations_steps.length
                    || state.updated_query.enriched_relations) {
                    state.updated_query = response.data
                }
                if (state.updated_query && state.updated_query.enriched_relations) {
                    clearInterval(state.running_timer)
                    let store = mapERLToStore(state.updated_query.enriched_relations)
                    let response = new MixedResponse()
                    response.store = store
                    emit('query_complete', response)
                    state.loading = false
                }
            })().catch(console.error)
        }, 250)
    } else {
        clearInterval(state.running_timer)
    }
})
const submit_query = (evt: KeyboardEvent | MouseEvent) => {
    if (evt instanceof KeyboardEvent && evt.key !== 'Enter') return
    console.log('Running query', state.query_string, evt);
    (async () => {
        state.running_query = null
        state.updated_query = null
        state.loading = true
        const response = await api.classes.getLlmResultsClassesSearchLlmGet({
            q: state.query_string
        })
        state.running_query = response.data
    })().catch(console.error)
}
const updated_steps = computed(() => {
    if (!state.updated_query || state.updated_query.relations_steps.length == 0) {
        return null
    }
    return state.updated_query.relations_steps


})
const selected_example = (example: EnrichedEntitiesRelations) => {
    state.query_string = example.message
    state.updated_query = {
        progress: 1,
        max_steps: 1,
        id: '-1',
        start_time: new Date().toISOString(),
        message: 'Example query',
        relations_steps: [{ ...example, message: "" }]
    }
    clearInterval(state.running_timer)
    let store = mapERLToStore(example)
    let response = new MixedResponse()
    response.store = store
    emit('query_complete', response)
    state.loading = false
}
</script>
<style lang="css" scoped>
.input_step {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    padding: 1rem;
    width: 100%;
}

.fuzzy_query_starter {
    display: flex;
    justify-content: center;
    align-items: center;
    flex-direction: row;
    width: 100%;
}

.query_input {
    width: 100%;
    height: 2.8rem;
    font-size: 1.5rem;
    padding: 0.5rem;
    margin: 0.5rem;
    border: 1px solid #8fa88f;
}

.fuzzy_query_input_row {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    width: 50vw;
}

.query_steps {
    display: flex;
    flex-direction: row;
    justify-content: center;
    align-items: center;
    width: 100%;
    padding: 1rem;
    margin: 1rem;
    overflow-x: auto;
}

.example_query_box {
    display: flex;
    flex-direction: row;
    flex-wrap: wrap;
    justify-content: center;
    align-items: center;
    width: 100%;
    padding: 1rem;
    margin: 1rem;
    overflow-x: auto;
    overflow-y: auto;
    max-height: 20rem;
}

.example_query {
    padding: 0.5rem;
    margin: 0.5rem;
    border: 1px solid #8fa88f;
    cursor: pointer;
    word-wrap: break-word;
    max-width: 25rem;
}
</style>