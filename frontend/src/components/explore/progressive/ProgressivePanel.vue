<template>
    <!-- Progressive discovery of the explore view's side panel: row counts of sampled
         modifications of the query as a scrubbable histogram, and the modifications nearest
         to the scrubbed count as difference views that can be applied to the editor, or (with
         a depth > 1, modifications continued from modifications) the tree of them. -->
    <div class="prog_panel">
        <div class="toolbar prog_panel_status">
            <OnsetIcon v-if="prog.state.status == 'loading'" icon="mdi-loading mdi-spin" />
            <OnsetIcon v-else-if="prog.state.status == 'error'" icon="mdi-alert-circle-outline" class="prog_panel_error" />
            <span class="prog_panel_status_text">{{ status_text }}</span>
            <span class="toolbar_spacer"></span>
            <label class="prog_panel_size" title="Modifications to sample and count">
                <OnsetIcon icon="mdi-dice-multiple-outline" />
                <input type="number" min="1" :max="prog.state.max_sample_size ?? undefined"
                    :value="prog.state.sample_size" @change="setSampleSize">
            </label>
            <span v-if="prog.source.label" class="prog_panel_source" :title="'Data source: ' + prog.source.label">
                {{ prog.source.label }}</span>
            <OnsetBtn size="small" :toggleable="false" icon="mdi-refresh" title="Count again" @click="prog.refresh()" />
        </div>
        <div class="toolbar prog_panel_constraints">
            <OnsetBtn size="small" icon="mdi-filter-outline" :model-value="prog.state.constraints.sample_constraints"
                title="Also sample constraints of the subjects: thresholds at percentiles of numeric/date values, values of categorical properties"
                @update:model-value="(on: boolean) => prog.setConstraints({ sample_constraints: on })">
                Sample constraints</OnsetBtn>
            <span class="toolbar_spacer"></span>
            <span v-if="prog.state.tree.depth > 1" class="prog_panel_depth" title="Levels of modifications">
                <OnsetIcon icon="mdi-file-tree-outline" />depth {{ prog.state.tree.depth }}</span>
            <OnsetBtn size="small" v-model="show_settings" :icon="show_settings ? 'mdi-chevron-up' : 'mdi-tune-variant'"
                title="Sampling settings: depth of the modifications and constraints">Settings</OnsetBtn>
        </div>
        <template v-if="show_settings">
            <ProgressiveDepthSettings :settings="prog.state.tree" :max_depth="prog.state.max_depth"
                :max_branching="prog.state.max_branching" :max_children="prog.state.max_sample_size"
                @update="prog.setTree"></ProgressiveDepthSettings>
            <ProgressiveConstraintSettings :settings="prog.state.constraints"
                :max_properties="prog.state.max_constraint_sample_size" @update="prog.setConstraints">
            </ProgressiveConstraintSettings>
        </template>
        <div v-if="prog.state.error" class="message prog_panel_error">{{ prog.state.error }}</div>
        <template v-if="prog.modifications.value.length">
            <ProgressiveHistogram :bins="prog.bins.value" :extent="prog.extent.value" :base_count="prog.base_count.value"
                :scrub_count="prog.scrub_count.value" :nearest_ids="prog.nearest_ids.value"
                :selected_id="prog.state.selected_id"
                v-model:scrub="prog.state.scrub_count"></ProgressiveHistogram>
            <div class="toolbar prog_panel_scrub">
                <span>{{ prog.nearest.value.length }} nearest to
                    <b>{{ formatCount(prog.scrub_count.value) }}</b> rows</span>
                <span class="toolbar_spacer"></span>
                <OnsetBtn v-if="prog.state.scrub_count != null && prog.base_count.value != null" size="small"
                    :toggleable="false" icon="mdi-target" title="Scrub back to the current row count"
                    @click="prog.setScrub(null); prog.state.selected_id = null">Current</OnsetBtn>
                <OnsetBtn size="small" icon="mdi-format-list-bulleted" :model-value="prog.state.view == 'nearest'"
                    title="The modifications nearest to the scrubbed count, with their differences"
                    @click="prog.state.view = 'nearest'">Nearest</OnsetBtn>
                <OnsetBtn size="small" icon="mdi-file-tree-outline" :model-value="prog.state.view == 'tree'"
                    title="All modifications as a tree of steps" @click="prog.state.view = 'tree'">Tree</OnsetBtn>
            </div>
            <div v-if="prog.state.view == 'nearest'" class="prog_panel_list">
                <ProgressiveModification v-for="item in prog.nearest_changes.value" :key="item.modification.id"
                    :modification="item.modification" :change="item.change" :path="item.path"
                    :selected="item.modification.id == prog.state.selected_id" :base_count="prog.base_count.value"
                    :count_limit="prog.state.result?.count_limit ?? null"
                    :skipped="item.skipped.length" @apply="apply(item.modification, item.change)"
                    @select="prog.select">
                </ProgressiveModification>
            </div>
            <ProgressiveTree v-else :tree="prog.tree.value" :by_id="prog.by_id.value" :base_count="prog.base_count.value"
                :count_limit="prog.state.result?.count_limit ?? null" :selected_id="prog.state.selected_id"
                @select="prog.select" @apply="(m) => apply(m, prog.changeOf(m).change)"></ProgressiveTree>
        </template>
        <div v-else-if="prog.state.status == 'ready'" class="message">No modifications found for this query.</div>
    </div>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import OnsetBtn from '@/components/ui/OnsetBtn.vue'
import OnsetIcon from '@/components/ui/OnsetIcon.vue'
import ProgressiveConstraintSettings from './ProgressiveConstraintSettings.vue'
import ProgressiveDepthSettings from './ProgressiveDepthSettings.vue'
import ProgressiveHistogram from './ProgressiveHistogram.vue'
import ProgressiveModification from './ProgressiveModification.vue'
import ProgressiveTree from './ProgressiveTree.vue'
import type { NodeLinkRepository } from '@/utils/sparql/store'
import type { GraphChange, GraphDetails } from '@/utils/agent/protocol'
import { formatCount } from '@/utils/progressive/histogram'
import { useProgressive } from '@/utils/progressive/useProgressive'
import type { ProgressiveModification as Modification } from '@/utils/progressive/types'

const { store } = defineProps<{
    store: NodeLinkRepository | null
}>()
const emit = defineEmits<{
    /** apply a modification's change to the editor graph (like an agent change) */
    apply: [change: GraphChange, details: GraphDetails]
}>()

const prog = useProgressive(() => store)
const show_settings = ref(false)

const status_text = computed(() => {
    const result = prog.state.result
    switch (prog.state.status) {
        case 'loading': {
            // counts streaming in
            const total = result ? result.modifications.length + (result.count_subject != null ? 1 : 0) : 0
            const pending = result ? result.modifications.filter((m) => m.pending).length + (result.base_pending ? 1 : 0) : 0
            return total ? `Counting… ${total - pending} of ${total}` : 'Counting…'
        }
        case 'error':
            return 'Counting failed'
        case 'idle':
            return 'Waiting for the query'
    }
    if (!result) {
        return ''
    }
    const first = result.modifications.filter((m) => m.depth == 1)
    const links = first.filter((m) => m.kind != 'constraint').length
    const constraints = first.length - links
    let sampled = result.candidate_count && result.candidate_count > links
        ? ` (${links} of ${result.candidate_count} sampled`
        : ` (${links}`
    if (result.constraint_candidate_count != null) {
        sampled += ` + ${constraints} constraints`
    }
    const deeper = result.modifications.length - first.length
    if (deeper > 0) {
        sampled += ` + ${deeper} deeper`
    }
    if (result.budget_exhausted) {
        sampled += ', query budget spent'
    }
    sampled += ')'
    if (result.base_count == null) {
        // a counted subject but no count: the current query's count failed
        return result.count_subject
            ? `Count failed · modifications${sampled}`
            : `Empty query · starting points${sampled}`
    }
    return `${formatCount(result.base_count, result.count_limit)} rows · modifications${sampled}`
})

const setSampleSize = (event: Event) => {
    const input = event.target as HTMLInputElement
    prog.setSampleSize(input.valueAsNumber)
    // show the clamped size even if it did not change
    input.value = String(prog.state.sample_size)
}

const apply = (modification: Modification, change: GraphChange) => {
    emit('apply', change, {
        subjects: modification.details?.subjects ?? {},
        links: modification.details?.links ?? {},
    })
}
</script>
<style scoped>
.prog_panel {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    height: 100%;
    min-height: 0;
}

.prog_panel_status,
.prog_panel_constraints,
.prog_panel_scrub {
    flex: 0 0 auto;
    font-size: var(--fs-xs);
}

.prog_panel_status_text {
    opacity: 0.8;
}

.prog_panel_size {
    display: inline-flex;
    align-items: center;
    gap: 2px;
}

.prog_panel_size input {
    width: 3.5rem;
    padding: 0 var(--space-1);
    border: 1px solid var(--c-border-ctrl);
    border-radius: var(--radius);
    font-size: inherit;
}

.prog_panel_depth {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    opacity: 0.8;
}

.prog_panel_source {
    padding: 0 var(--space-1);
    border: 1px dashed var(--c-border-ctrl);
    border-radius: var(--radius);
    opacity: 0.8;
}

.prog_panel_error {
    color: #b3261e;
}

.prog_panel_list {
    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    padding-right: 2px;
}
</style>
