<template>
    <div class="fuzzy_query_starter">
        <div class="input_step">
            <h3>Enter your query:</h3>
            <div  class="fuzzy_query_input_row">
                <input type="text" v-model="state.query_string" @keydown="submit_query"  class="query_input"/>
                <OnsetBtn @click="submit_query" :toggleable="false">Submit</OnsetBtn>
            </div>
            <div v-if="state.loading && state.running_query">
                <OnsetProgress :progress="state.running_query.progress" :max="state.running_query.max_steps">
                </OnsetProgress>
            </div>

        </div>

    </div>

</template>

<script setup lang="ts">
import { Api, type QueryProgress } from '@/api/client.ts/Api';
import { BACKEND_URL } from '@/utils/config';
import { ref, watch, reactive, computed, onMounted, onBeforeMount } from 'vue'
import { fa } from 'vuetify/locale';
import OnsetProgress from '../ui/OnsetProgress.vue';
import OnsetBtn from '../ui/OnsetBtn.vue';
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

watch(() => state.running_query, (new_val) => {
    if (new_val) {
        if (state.running_timer) clearInterval(state.running_timer)
        state.running_timer = setInterval(() => {
            console.log('Running query', state.running_query.id);
            (async () => {
                const response = await api.classes.getLlmResultsRunningClassesSearchLlmRunningGet({
                    query_id: state.running_query.id
                })
                state.updated_query = response.data
                if (state.updated_query.enriched_relations) {
                    clearInterval(state.running_timer)
                    state.loading = false
                }
            })().catch(console.error)
        }, 100)
    } else {
        clearInterval(state.running_timer)
    }
})
const submit_query = (evt: KeyboardEvent | MouseEvent) => {
    if (evt instanceof KeyboardEvent && evt.key !== 'Enter') return

    console.log('Running query', state.query_string);
    (async () => {
        state.loading = true
        const response = await api.classes.getLlmResultsClassesSearchLlmGet({
            q: state.query_string
        })
        state.running_query = response.data
    })().catch(console.error)
}
</script>
<style lang="css" scoped>
.input_step {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
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