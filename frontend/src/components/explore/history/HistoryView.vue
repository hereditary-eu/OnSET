<template>
    <section class="panel history_view">
        <header class="panel_header">
            <span class="panel_title">History</span>
            <span class="toolbar_spacer"></span>
            <SelectorGroup v-model="ui_state.history_mode" :options="Object.keys(HistoryMode).map(qm => {
                return { value: HistoryMode[qm], label: HistoryMode[qm] }
            })"></SelectorGroup>
            <slot name="actions"></slot>
        </header>
        <div v-if="ui_state.history_mode == HistoryMode.DETAILED" class="panel_body history_list">
            <div class="toolbar history_search_bar">
                <input type="text" v-model="ui_state.query_string" @keypress="submit_query"
                    class="text_input history_search_input" placeholder="Search history..." />
                <OnsetBtn @click="submit_query" :toggleable="false" size="small">Search</OnsetBtn>
            </div>
            <Loading v-if="ui_state.similar_entries.loading"></Loading>
            <HistoryElement v-for="(entry, index) of history_filtered" :key="index" :entry="(entry as HistoryEntry)"
                @revert="emit('revert', $event)" @compare="emit('compare', $event)">
            </HistoryElement>
        </div>
        <div v-else class="panel_body">
            <TimeEmbeddingsOverlay :history="(history as QueryHistory)" @show-tooltip='emit("showTooltip", $event)'>
            </TimeEmbeddingsOverlay>
        </div>
    </section>
</template>
<script setup lang="ts">
import { reactive, computed } from 'vue'
import SelectorGroup from '@/components/ui/SelectorGroup.vue';
import { HistoryEntry, QueryHistory } from '@/utils/sparql/history';
import { HistoryTooltipEvent } from '@/utils/sparql/helpers';
import HistoryElement from './HistoryElement.vue';
import TimeEmbeddingsOverlay from './TimeEmbeddingsOverlay.vue';
import OnsetBtn from '@/components/ui/OnsetBtn.vue';
import Loading from '@/components/ui/Loading.vue';
enum HistoryMode {
    OVERVIEW = 'Overview',
    DETAILED = 'Detailed',
}
const { history } = defineProps({
    history: {
        type: Object as () => QueryHistory,
        required: true
    },
})
const ui_state = reactive({
    history_mode: HistoryMode.OVERVIEW,
    query_string: '',
    similar_entries: {
        loading: false,
        entries: [] as HistoryEntry[],
    }
})

const emit = defineEmits<{
    revert: [HistoryEntry],
    compare: [HistoryEntry],
    showTooltip: [HistoryTooltipEvent],
}>()

const history_filtered = computed(() => {
    if(ui_state.similar_entries.loading) {
        return []
    }
    if (ui_state.query_string.trim() === '') {
        return history.reverse_entries
    }
    return ui_state.similar_entries.entries
})

function submit_query(event: KeyboardEvent | MouseEvent) {
    if (event instanceof KeyboardEvent) {
        if (event.key !== "Enter") {
            return
        }
    }
    ui_state.similar_entries.loading = true
    history.searchSimilarEntries(ui_state.query_string).then((entries) => {
        console.log("Similar entries searched")

        ui_state.similar_entries.entries = entries.map(e => e.entry)

    }).finally(() => {
        ui_state.similar_entries.loading = false
    })
}
</script>
<style scoped>
.history_view {
    height: 100%;
    width: 100%;
}

.history_list {
    display: flex;
    flex-direction: column;
}

.history_search_bar {
    padding: var(--space-1);
    border-bottom: 1px solid var(--c-border);
}

.history_search_input {
    flex: 1 1 auto;
}
</style>
