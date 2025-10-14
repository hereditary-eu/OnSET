<template>
    <div class="history_view">
        <div class="history_instance_header">History</div>

        <SelectorGroup v-model="ui_state.history_mode" :options="Object.keys(HistoryMode).map(qm => {
            return { value: HistoryMode[qm], label: HistoryMode[qm] }
        })" :width='"7rem"' :height='"1.2rem"'></SelectorGroup>
        <div v-if="ui_state.history_mode == HistoryMode.DETAILED" class="history_instance_container">
            <div v-for="(entry, index) of ui_state.history.entries" :key="index" class="result_instance_element">
                <HistoryElement :entry="entry" :display_mode="DisplayMode.EDIT_NO_ADD">
                </HistoryElement>
            </div>
            <!-- <div v-else class="history_instance_container">
            <historyPlot :store="store" :query_string="query_string" :diff="diff"></historyPlot>
            -->
        </div>
    </div>
</template>
<script setup lang="ts">
import { watch, reactive, defineProps } from 'vue'
import type { NodeLinkRepository } from '@/utils/sparql/store';
import SelectorGroup from '@/components/ui/SelectorGroup.vue';
import { QueryHistory } from '@/utils/sparql/history';
import { DisplayMode } from '@/utils/sparql/helpers';
import HistoryElement from './HistoryElement.vue';
enum HistoryMode {
    OVERVIEW = 'Overview',
    DETAILED = 'Detailed',
}
const { store } = defineProps({
    store: {
        type: Object as () => NodeLinkRepository,
        required: true
    },
})
const ui_state = reactive({
    history_mode: HistoryMode.DETAILED,
    history: new QueryHistory(),
})

watch(() => store, () => {
    ui_state.history.tryAddEntry(store)
}, { deep: true })
watch(() => ui_state.history, () => {
}, { deep: true })
</script>
<style lang="scss">
.history_view {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: start;
    height: 95%;
    width: 30%;
    border-right: 1px solid rgb(192, 213, 191);
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
</style>
