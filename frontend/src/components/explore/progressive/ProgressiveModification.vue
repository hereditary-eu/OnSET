<template>
    <!-- One candidate modification: its label, row count relative to the current graph, and
         the difference view of what it adds/removes; clicking applies it to the editor. A
         deeper modification (tree expansion) shows the steps before it as a breadcrumb, its
         difference view and count are of all steps. -->
    <div class="prog_mod"
        :class="{ prog_mod_empty: modification.count === 0, prog_mod_constraint: tag, prog_mod_selected: selected }">
        <div v-if="path.length" class="prog_mod_path" :title="path.map((m) => m.label).join(' › ')">
            <span class="prog_mod_depth" :title="`${modification.depth} steps`">{{ modification.depth }}</span>
            <template v-for="step in path" :key="step.id">
                <button type="button" class="prog_mod_step" :title="`Select: ${step.description ?? step.label}`"
                    @click="emit('select', step.id)">{{ step.label }}</button>
                <span class="prog_mod_sep">›</span>
            </template>
        </div>
        <button type="button" class="prog_mod_header" :title="modification.description || 'Apply to the query'"
            @click="emit('apply')">
            <OnsetIcon :icon="tag ? 'mdi-filter-outline' : 'mdi-vector-polyline-plus'" class="prog_mod_kind"
                :title="tag ? 'Constraint' : 'Link'" />
            <span class="prog_mod_label">{{ modification.label }}</span>
            <span v-if="tag" class="prog_mod_tag" :title="tag_title">{{ tag }}</span>
            <OnsetIcon v-if="modification.pending" icon="mdi-loading mdi-spin" class="prog_mod_count"
                title="Counting…" />
            <span v-else class="prog_mod_count" :title="modification.count == null ? 'Count failed or timed out' : undefined">
                {{ formatCount(modification.count, count_limit) }}</span>
            <span v-if="ratio" class="prog_mod_ratio" :class="ratio.more ? 'prog_mod_more' : 'prog_mod_less'"
                title="Rows relative to the current query">{{ ratio.text }}</span>
            <OnsetIcon icon="mdi-plus-circle-outline" class="prog_mod_apply" />
        </button>
        <ChatGraphPreview v-if="!empty_change" :change="change" :details="modification.details"></ChatGraphPreview>
        <div v-if="skipped" class="prog_mod_note">{{ skipped }} operation{{ skipped > 1 ? 's' : '' }} not shown</div>
    </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import OnsetIcon from '@/components/ui/OnsetIcon.vue'
import ChatGraphPreview from '../chat/ChatGraphPreview.vue'
import { isEmptyChange } from '@/utils/agent/graph_sync'
import type { GraphChange } from '@/utils/agent/protocol'
import { constraintTag, formatCount, formatRatio } from '@/utils/progressive/histogram'
import type { ProgressiveModification } from '@/utils/progressive/types'

const { modification, change, path = [], selected = false, base_count = null, count_limit = null, skipped = 0 } = defineProps<{
    modification: ProgressiveModification
    /** the change of all steps (cumulative operations) */
    change: GraphChange
    /** the steps before this one (tree expansion), first level first */
    path?: ProgressiveModification[]
    selected?: boolean
    base_count?: number | null
    /** cap of the counts, reached counts are lower bounds */
    count_limit?: number | null
    /** operations without a difference view (subqueries) */
    skipped?: number
}>()
const emit = defineEmits<{
    apply: []
    /** a step of the path was clicked */
    select: [id: string]
}>()

const empty_change = computed(() => isEmptyChange(change))
const tag = computed(() => constraintTag(modification))
const tag_title = computed(() => {
    const constraint = modification.constraint
    if (!constraint) {
        return undefined
    }
    return constraint.kind == 'percentile'
        ? `Threshold at the ${constraint.percentile}th percentile of ${constraint.property_label} in the current results`
        : `Sampled by frequency: ${formatCount(constraint.frequency)} of the current results`
})
// count relative to the current graph's rows
const ratio = computed(() => formatRatio(modification.count, base_count))
</script>
<style scoped>
.prog_mod {
    /* keep the full preview height in the scrolling list */
    flex: 0 0 auto;
    border: 1px solid var(--c-border);
    border-radius: var(--radius);
    background: var(--c-surface);
    font-size: var(--fs-xs);
    overflow: hidden;
}

.prog_mod_empty {
    opacity: 0.6;
}

.prog_mod_selected {
    border-color: var(--c-accent);
    box-shadow: 0 0 0 1px var(--c-accent);
}

.prog_mod_path {
    display: flex;
    align-items: center;
    gap: 2px;
    padding: 0.1rem var(--space-1) 0;
    overflow: hidden;
    white-space: nowrap;
    opacity: 0.8;
}

.prog_mod_depth {
    flex: 0 0 auto;
    min-width: 1rem;
    padding: 0 3px;
    border-radius: 999px;
    background: var(--c-hover);
    font-family: var(--font-mono);
    text-align: center;
}

.prog_mod_step {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    padding: 0;
    border: none;
    background: none;
    font: inherit;
    color: inherit;
    cursor: pointer;
}

.prog_mod_step:hover {
    text-decoration: underline;
}

.prog_mod_sep {
    flex: 0 0 auto;
    opacity: 0.6;
}

.prog_mod_constraint {
    border-left: 3px solid var(--c-constraint);
}

.prog_mod_kind {
    opacity: 0.6;
}

.prog_mod_constraint .prog_mod_kind {
    color: var(--c-constraint);
    opacity: 1;
}

.prog_mod_tag {
    padding: 0 var(--space-1);
    border-radius: 999px;
    background: var(--c-constraint-soft);
    font-family: var(--font-mono);
    white-space: nowrap;
}

.prog_mod_header {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    width: 100%;
    padding: 0.15rem var(--space-1);
    font: inherit;
    color: inherit;
    text-align: left;
    background: none;
    border: none;
    cursor: pointer;
}

.prog_mod_header:hover {
    background: var(--c-hover);
}

.prog_mod_label {
    flex: 1 1 auto;
    min-width: 0;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
}

.prog_mod_count {
    font-family: var(--font-mono);
    font-weight: 600;
    white-space: nowrap;
}

.prog_mod_ratio {
    white-space: nowrap;
    opacity: 0.8;
}

.prog_mod_more {
    color: var(--c-accent);
}

.prog_mod_less {
    color: var(--c-node-removed);
}

.prog_mod_apply {
    color: var(--c-accent);
}

.prog_mod_note {
    padding: 0 var(--space-1);
    opacity: 0.7;
}
</style>
