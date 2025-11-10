<template>

    <div class="history_view">
        <div class="history_instance_header">History</div>

        <SelectorGroup v-model="ui_state.history_mode" :options="Object.keys(HistoryMode).map(qm => {
            return { value: HistoryMode[qm], label: HistoryMode[qm] }
        })" :width='"7rem"' :height='"1.2rem"'></SelectorGroup>
        <div v-if="ui_state.history_mode == HistoryMode.DETAILED" class="history_instance_container">
            <div v-for="(entry, index) of history.reverse_entries" :key="index" class="history_instance_element">
                <HistoryElement :entry="entry" :display_mode="DisplayMode.EDIT_NO_ADD" @revert="emit('revert', $event)"
                    @compare="emit('compare', $event)">
                </HistoryElement>
            </div>
            <!-- <div v-else class="history_instance_container">
            <historyPlot :store="store" :query_string="query_string" :diff="diff"></historyPlot>
            -->
        </div>
        <div v-else class="history_overview_container">
            <TimeEmbeddingsOverlay :history="(history as QueryHistory)"></TimeEmbeddingsOverlay>
        </div>
    </div>
</template>
<script setup lang="ts">
import { watch, reactive, defineProps } from 'vue'
import type { NodeLinkRepository } from '@/utils/sparql/store';
import SelectorGroup from '@/components/ui/SelectorGroup.vue';
import { HistoryEntry, QueryHistory } from '@/utils/sparql/history';
import { DisplayMode } from '@/utils/sparql/helpers';
import HistoryElement from './HistoryElement.vue';
import TimeEmbeddingsOverlay from './TimeEmbeddingsOverlay.vue';
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
})

const emit = defineEmits<{
    revert: [HistoryEntry],
    compare: [HistoryEntry]
}>()
</script>
<style lang="scss">
.history_view {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: start;
    height: 100%;
    width: 80%;
    border: 1px solid rgb(192, 213, 191);
    background-color: rgba(251, 248, 243, 0.905);
}

.history_instance_container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    width: 100%;
    height: 100%;
    overflow: auto;
    padding: 5px;
    margin-top: 10px;
}


.history_instance_header {
    font-size: 1.5rem;
    font-weight: bold;
    padding: 5px;
    border-bottom: 1px solid rgb(192, 213, 191);
    width: 100%;
    margin-bottom: 12px;
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
}
</style>
