<template>
    <section class="panel results_view">
        <header class="panel_header">
            <span class="panel_title">Results</span>
            <span class="toolbar_spacer"></span>
            <SelectorGroup v-model="ui_state.result_mode" :options="Object.keys(ResultMode).map(qm => {
                return { value: ResultMode[qm], label: ResultMode[qm] }
            })"></SelectorGroup>
        </header>
        <div class="panel_body">
            <ResultMinitatures v-if="ui_state.result_mode == ResultMode.MINI" :diff="diff" :store="store"
                :query_string="query_string"></ResultMinitatures>
            <ResultPlot v-else :store="store" :query_string="query_string" :diff="diff"></ResultPlot>
        </div>
    </section>
</template>
<script setup lang="ts">
import { watch, reactive } from 'vue'
import { SubQueryType } from '@/utils/sparql/representation';
import ResultPlot from './results/Plot.vue';
import type { NodeLinkRepository } from '@/utils/sparql/store';
import SelectorGroup from '../ui/SelectorGroup.vue';
import type { NodeLinkRepositoryDiff } from '@/utils/sparql/diff';
import ResultMinitatures from './results/MinitatureList.vue';
enum ResultMode {
    MINI = 'Miniatures',
    PROP = 'Properties',
}
const { store, query_string, diff } = defineProps({
    store: {
        type: Object as () => NodeLinkRepository,
        required: true
    },
    query_string: {
        type: String,
        required: true
    },
    diff: {
        type: Object as () => NodeLinkRepositoryDiff | null,
        default: null
    }
})
const ui_state = reactive({
    result_mode: ResultMode.MINI
})
watch(() => query_string, () => {
    if (!store) {
        return
    }
    let query_props = store.nodes.flatMap(n => n.subqueries.filter(sq => sq.constraint_type == SubQueryType.QUERY_PROP))
    if (query_props.length > 0) {
        ui_state.result_mode = ResultMode.PROP
    } else {
        ui_state.result_mode = ResultMode.MINI
    }
}, { deep: true })
</script>
