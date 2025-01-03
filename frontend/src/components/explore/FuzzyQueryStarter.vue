<template>
    <div class="fuzzy_query_starter">
        <div class="input_step">
            <h3>Enter your query:</h3>
            <div class="fuzzy_query_input_row">
                <input type="text" v-model="state.query_string" @keypress="submit_query" class="query_input" />
                <OnsetBtn @click="submit_query" :toggleable="false">Submit</OnsetBtn>
            </div>
            <div v-if="state.loading && state.running_query" class="input_step">
                <Loading></Loading>
                <OnsetProgress :progress="state.running_query.progress" :max="state.running_query.max_steps">
                </OnsetProgress>
                <h3 v-if="state.updated_query">{{ state.updated_query.message }}</h3>
            </div>
            <FuzzyQueryIntermediate v-if="updated_steps && state.updated_query.relations_steps.length > 0"
                :erl="state.updated_query.relations_steps[state.updated_query.relations_steps.length - 1]">>
            </FuzzyQueryIntermediate>
        </div>

    </div>

</template>

<script setup lang="ts">
import { Api, type Candidates, type QueryProgress } from '@/api/client.ts/Api';
import { BACKEND_URL } from '@/utils/config';
import { ref, watch, reactive, computed, onMounted, onBeforeMount } from 'vue'
import { ca, fa, fr } from 'vuetify/locale';
import OnsetProgress from '../ui/OnsetProgress.vue';
import OnsetBtn from '../ui/OnsetBtn.vue';
import { NodeLinkRepository } from '@/utils/sparql/store';
import { Constraint, Link, Node } from '@/utils/sparql/representation';
import { NodeSide } from '@/utils/sparql/helpers';
import Loading from '../ui/Loading.vue';
import FuzzyQueryIntermediate from './FuzzyQueryIntermediate.vue';
const state = reactive({
    query_string: 'the birthplace of a ceo of a company',
    running_query: null as QueryProgress | null,
    updated_query: null as QueryProgress | null,
    running_timer: null as number | null,
    loading: false

})
const api = new Api({
    baseURL: BACKEND_URL
})

onBeforeMount(() => {

    state.running_query = {
        id: "query:2:2025-01-03T10:09:40.436340",
        progress: 2,
        max_steps: 10,
        message: "TEST QUERY",
        start_time: "2025-01-03T09:34:26.189876",
    }
    state.loading = true
})

watch(() => state.running_query, (new_val) => {
    if (new_val) {
        if (state.running_timer) clearInterval(state.running_timer)
        state.running_timer = setInterval(() => {
            console.log('Running query', state.running_query.id);
            (async () => {
                const response = await api.classes.getLlmResultsRunningClassesSearchLlmRunningGet({
                    query_id: state.running_query.id
                })
                if (!state.updated_query || state.updated_query.relations_steps.length != response.data.relations_steps.length) {
                    state.updated_query = response.data
                }
                if (state.updated_query.enriched_relations) {
                    clearInterval(state.running_timer)
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
    console.log('Running query', state.query_string);
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
</script>
<style lang="css" scoped>
.input_step {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    padding: 1rem;
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
    flex-direction: row;
    justify-content: center;
    align-items: center;
}
</style>