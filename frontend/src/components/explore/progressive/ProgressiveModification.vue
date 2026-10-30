<template>
    <!-- One candidate modification: its label, row count relative to the current graph, and
         the difference view of what it adds/removes; clicking applies it to the editor. -->
    <div class="prog_mod" :class="{ prog_mod_empty: modification.count === 0 }">
        <button type="button" class="prog_mod_header" :title="modification.description || 'Apply to the query'"
            @click="emit('apply')">
            <span class="prog_mod_label">{{ modification.label }}</span>
            <span class="prog_mod_count" :title="modification.count == null ? 'Count failed or timed out' : undefined">
                {{ formatCount(modification.count, count_limit) }}</span>
            <span v-if="ratio" class="prog_mod_ratio" :class="ratio.cls">{{ ratio.text }}</span>
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
import { formatCount } from '@/utils/progressive/histogram'
import type { ProgressiveModification } from '@/utils/progressive/types'

const { modification, change, base_count = null, count_limit = null, skipped = 0 } = defineProps<{
    modification: ProgressiveModification
    change: GraphChange
    base_count?: number | null
    /** cap of the counts, reached counts are lower bounds */
    count_limit?: number | null
    /** operations without a difference view (subqueries) */
    skipped?: number
}>()
const emit = defineEmits<{
    apply: []
}>()

const empty_change = computed(() => isEmptyChange(change))
// count relative to the current graph's rows
const ratio = computed(() => {
    const count = modification.count
    if (count == null || !base_count) {
        return null
    }
    const r = count / base_count
    const text = r >= 10 ? `×${r.toFixed(0)}` : r >= 1 ? `×${r.toFixed(1)}` : `${(r * 100).toFixed(r < 0.01 ? 2 : 0)}%`
    return { text, cls: r > 1 ? 'prog_mod_more' : 'prog_mod_less' }
})
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
