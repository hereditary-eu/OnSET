<template>

    <div class="history_view">
        <div class="history_instance_header">History</div>

        <SelectorGroup v-model="ui_state.history_mode" :options="Object.keys(HistoryMode).map(qm => {
            return { value: HistoryMode[qm], label: HistoryMode[qm] }
        })" :width='"7rem"' :height='"1.2rem"'></SelectorGroup>
        <div v-if="ui_state.history_mode == HistoryMode.DETAILED" class="history_instance_container">
            <div class="history_search_bar">
                <input type="text" v-model="ui_state.query_string" @keypress="submit_query" class="query_input" />
                <OnsetBtn @click="submit_query" :toggleable="false" btn_height="1.3rem" btn_width="4rem">Search
                </OnsetBtn>
            </div>
            <div v-if="ui_state.similar_entries.loading">
                <Loading></Loading>
            </div>
            <div v-for="(entry, index) of history_filtered" :key="index" class="history_instance_element">
                <HistoryElement :entry="(entry as HistoryEntry)" :display_mode="DisplayMode.EDIT_NO_ADD" @revert="emit('revert', $event)"
                    @compare="emit('compare', $event)">
                </HistoryElement>
            </div>
            <!-- <div v-else class="history_instance_container">
            <historyPlot :store="store" :query_string="query_string" :diff="diff"></historyPlot>
            -->
        </div>
        <div v-else class="history_overview_container">
            <TimeEmbeddingsOverlay :history="(history as QueryHistory)" @show-tooltip='emit("showTooltip", $event)'>
            </TimeEmbeddingsOverlay>
        </div>
    </div>
</template>
<script setup lang="ts">
import { watch, reactive, defineProps, computed } from 'vue'
import type { NodeLinkRepository } from '@/utils/sparql/store';
import SelectorGroup from '@/components/ui/SelectorGroup.vue';
import { HistoryEntry, QueryHistory } from '@/utils/sparql/history';
import { DisplayMode, HistoryTooltipEvent } from '@/utils/sparql/helpers';
import HistoryElement from './HistoryElement.vue';
import TimeEmbeddingsOverlay from './TimeEmbeddingsOverlay.vue';
import type { Vector2 } from 'three';
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
<style lang="scss">
.history_view {
    display: flex;
    position: relative;
    flex-direction: column;
    align-items: center;
    justify-content: start;
    height: 100%;
    width: 80%;
    border: 1px solid rgb(192, 213, 191);
    background-color: white;
    z-index: inherit;
}

.history_instance_container {

    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    width: 100%;
    height: 100%;
    overflow: auto;
    padding: 5px;
    margin-top: 10px;
    z-index: inherit;
}


.history_instance_header {
    font-size: 1.5rem;
    font-weight: bold;
    padding: 5px;
    border-bottom: 1px solid rgb(192, 213, 191);
    width: 100%;
    margin-bottom: 12px;
    z-index: inherit;
}

.history_overview_container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    width: 100%;
    height: 100%;
    overflow: hidden;
    padding: 5px;
    margin-top: 10px;
    z-index: inherit;
}
.history_search_bar {
    display: flex;
    flex-direction: row;
    align-items: center;
    justify-content: center;
    gap: 10px;
    margin-bottom: 10px;
    width: 100%;
    border-bottom: 1px solid rgb(192, 213, 191);
}
.query_input {
    width: 60%;
    height: 1.3rem;
    font-size: 0.8rem;
    margin: 10px;
    border: 1px solid rgb(192, 213, 191);
    background-color: white;
    // border-radius: 4px;
}
</style>
