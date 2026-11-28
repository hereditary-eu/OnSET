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
            <template v-for="(entry, index) of history_filtered" :key="index">
                <!-- the element of an entry; the query history's by default -->
                <slot name="entry" :entry="(entry as E)">
                    <HistoryElement :entry="(entry as unknown as HistoryEntry)"
                        @revert="emit('revert', $event as unknown as E)" @compare="emit('compare', $event as unknown as E)"
                        @show-in-chat="emit('showInChat', $event)">
                    </HistoryElement>
                </slot>
            </template>
        </div>
        <div v-else class="panel_body">
            <TimeEmbeddingsOverlay :history="history" @show-tooltip='emit("showTooltip", $event)'
                @show-in-chat="emit('showInChat', $event)">
            </TimeEmbeddingsOverlay>
        </div>
    </section>
</template>
<script setup lang="ts" generic="E extends TimelineEntry">
// History panel of the query builder (QueryHistory, default) or the ontology builder (its own
// entry elements in the `entry` slot): the time embedding curve or the list of entries.
import { reactive, computed, shallowRef } from 'vue'
import type { Vector2Like } from 'three';
import SelectorGroup from '@/components/ui/SelectorGroup.vue';
import type { HistoryEntry } from '@/utils/sparql/history';
import type { SearchableHistory, TimelineEntry } from '@/utils/sparql/timeline';
import HistoryElement from './HistoryElement.vue';
import TimeEmbeddingsOverlay from './TimeEmbeddingsOverlay.vue';
import OnsetBtn from '@/components/ui/OnsetBtn.vue';
import Loading from '@/components/ui/Loading.vue';
enum HistoryMode {
    OVERVIEW = 'Overview',
    DETAILED = 'Detailed',
}
const { history } = defineProps<{ history: SearchableHistory<E> }>()
defineSlots<{ actions?(): unknown, entry?(props: { entry: E }): unknown }>()
const ui_state = reactive({
    history_mode: HistoryMode.OVERVIEW,
    query_string: '',
    similar_entries: {
        loading: false,
    }
})
const similar_entries = shallowRef<E[]>([])

const emit = defineEmits<{
    revert: [E],
    compare: [E],
    showTooltip: [{ position: Vector2Like, entry: E, event: MouseEvent }],
    showInChat: [string[]],
}>()

const history_filtered = computed(() => {
    if(ui_state.similar_entries.loading) {
        return []
    }
    if (ui_state.query_string.trim() === '') {
        return history.reverse_entries
    }
    return similar_entries.value
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

        similar_entries.value = entries.map(e => e.entry)

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
