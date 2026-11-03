<template>
    <!-- The tree of modifications (tree expansion): every modification with its row count and
         the ratio to its parent's (the current query's on the first level). Clicking a row
         selects it (the histogram scrubs to its count), the plus applies all steps down to it.
         Continued modifications come first, then by count. -->
    <div class="prog_tree">
        <div class="toolbar prog_tree_toolbar">
            <span>{{ total }} modification{{ total == 1 ? '' : 's' }}<template v-if="levels.length > 1"> ·
                    {{ levels.map((n, i) => `${n} at depth ${i + 1}`).join(', ') }}</template></span>
            <span class="toolbar_spacer"></span>
            <OnsetBtn size="small" :toggleable="false" icon="mdi-unfold-more-horizontal" title="Expand all"
                :active="expandable.length > 0" @click="open = new Set(expandable)"></OnsetBtn>
            <OnsetBtn size="small" :toggleable="false" icon="mdi-unfold-less-horizontal" title="Collapse all"
                :active="open.size > 0" @click="open = new Set()"></OnsetBtn>
        </div>
        <div ref="list" class="prog_tree_list" role="tree">
            <div v-for="row in rows" :key="row.m.id" class="prog_tree_row" role="treeitem"
                :aria-expanded="row.children ? row.open : undefined" :aria-selected="row.m.id == selected_id"
                :data-id="row.m.id"
                :class="{ prog_tree_selected: row.m.id == selected_id, prog_tree_empty: row.m.count === 0, prog_tree_constraint: isConstraint(row.m) }"
                :style="{ paddingLeft: `${(row.m.depth - 1) * 14 + 2}px` }" :title="row.m.description ?? undefined"
                @click="emit('select', row.m.id == selected_id ? null : row.m.id)">
                <button v-if="row.children" type="button" class="prog_tree_toggle"
                    :title="row.open ? 'Collapse' : `Show the ${row.children} modifications continuing from here`"
                    @click.stop="toggle(row.m.id)">
                    <OnsetIcon :icon="row.open ? 'mdi-chevron-down' : 'mdi-chevron-right'" />
                </button>
                <span v-else class="prog_tree_toggle"></span>
                <OnsetIcon :icon="isConstraint(row.m) ? 'mdi-filter-outline' : 'mdi-vector-polyline-plus'"
                    class="prog_tree_kind" />
                <span class="prog_tree_label">{{ row.m.label }}</span>
                <span v-if="row.children && !row.open" class="prog_tree_more">+{{ row.children }}</span>
                <OnsetIcon v-if="row.m.pending" icon="mdi-loading mdi-spin" class="prog_tree_count" title="Counting…" />
                <span v-else class="prog_tree_count">{{ formatCount(row.m.count, count_limit) }}</span>
                <span class="prog_tree_ratio" :class="row.ratio ? (row.ratio.more ? 'prog_tree_up' : 'prog_tree_down') : ''"
                    :title="row.m.depth > 1 ? 'Rows relative to the modification it continues' : 'Rows relative to the current query'">
                    {{ row.ratio?.text ?? '' }}</span>
                <button type="button" class="prog_tree_apply"
                    :title="row.m.depth > 1 ? `Apply all ${row.m.depth} steps to the query` : 'Apply to the query'"
                    @click.stop="emit('apply', row.m)">
                    <OnsetIcon icon="mdi-plus-circle-outline" />
                </button>
            </div>
        </div>
    </div>
</template>
<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import OnsetBtn from '@/components/ui/OnsetBtn.vue'
import OnsetIcon from '@/components/ui/OnsetIcon.vue'
import { formatCount, formatRatio, isConstraint } from '@/utils/progressive/histogram'
import { ancestorIds, depthCounts, referenceCount, type ModificationNode, type ModificationTree } from '@/utils/progressive/tree'
import type { ProgressiveModification } from '@/utils/progressive/types'

const { tree, by_id, base_count = null, count_limit = null, selected_id = null } = defineProps<{
    tree: ModificationTree
    by_id: Map<string, ProgressiveModification>
    base_count?: number | null
    count_limit?: number | null
    selected_id?: string | null
}>()
const emit = defineEmits<{
    select: [id: string | null]
    apply: [modification: ProgressiveModification]
}>()

const list = ref<HTMLElement | null>(null)
const modifications = computed(() => [...by_id.values()])
const total = computed(() => modifications.value.length)
const levels = computed(() => depthCounts(modifications.value))
const expandable = computed(() => [...tree.nodes.values()].filter((n) => n.children.length).map((n) => n.modification.id))

// open nodes: by default the first level's continued ones
const open = ref(new Set<string>())
watch(() => tree, () => {
    open.value = new Set(tree.roots.filter((n) => n.children.length).map((n) => n.modification.id))
}, { immediate: true })
const toggle = (id: string) => {
    const next = new Set(open.value)
    if (!next.delete(id)) {
        next.add(id)
    }
    open.value = next
}

// continued modifications first, then by count (failed ones last)
const ordered = (nodes: ModificationNode[]) => [...nodes].sort((a, b) =>
    Number(b.children.length > 0) - Number(a.children.length > 0)
    || (b.modification.count ?? -1) - (a.modification.count ?? -1))

const rows = computed(() => {
    const rows: { m: ProgressiveModification, children: number, open: boolean, ratio: ReturnType<typeof formatRatio> }[] = []
    const visit = (nodes: ModificationNode[]) => {
        for (const node of ordered(nodes)) {
            const m = node.modification
            const is_open = open.value.has(m.id)
            rows.push({
                m, children: node.children.length, open: is_open,
                ratio: formatRatio(m.count, referenceCount(m, by_id, base_count)),
            })
            if (is_open) {
                visit(node.children)
            }
        }
    }
    visit(tree.roots)
    return rows
})

// a modification selected elsewhere (the histogram, the nearest list): open the tree down to it
watch(() => selected_id, async (id) => {
    if (id == null) {
        return
    }
    const ancestors = ancestorIds(id, by_id)
    if (ancestors.some((a) => !open.value.has(a))) {
        open.value = new Set([...open.value, ...ancestors])
    }
    await nextTick()
    list.value?.querySelector(`[data-id="${CSS.escape(id)}"]`)?.scrollIntoView({ block: 'nearest' })
}, { immediate: true })
</script>
<style scoped>
.prog_tree {
    display: flex;
    flex-direction: column;
    min-height: 0;
    flex: 1 1 auto;
    font-size: var(--fs-xs);
}

.prog_tree_toolbar {
    flex: 0 0 auto;
    opacity: 0.9;
}

.prog_tree_list {
    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto;
    border: 1px solid var(--c-border);
    border-radius: var(--radius);
    background: var(--c-surface);
}

.prog_tree_row {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    padding: 1px var(--space-1) 1px 2px;
    cursor: pointer;
    border-left: 3px solid transparent;
}

.prog_tree_row:hover {
    background: var(--c-hover);
}

.prog_tree_selected,
.prog_tree_selected:hover {
    background: var(--c-hover);
    border-left-color: var(--c-accent);
    font-weight: 600;
}

.prog_tree_empty {
    opacity: 0.6;
}

.prog_tree_toggle {
    display: inline-flex;
    flex: 0 0 1rem;
    justify-content: center;
    padding: 0;
    border: none;
    background: none;
    color: inherit;
    cursor: pointer;
}

.prog_tree_kind {
    opacity: 0.6;
}

.prog_tree_constraint .prog_tree_kind {
    color: var(--c-constraint);
    opacity: 1;
}

.prog_tree_label {
    flex: 1 1 auto;
    min-width: 0;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
}

.prog_tree_more {
    padding: 0 var(--space-1);
    border-radius: 999px;
    background: var(--c-hover);
    opacity: 0.8;
    white-space: nowrap;
}

.prog_tree_count {
    font-family: var(--font-mono);
    font-weight: 600;
    white-space: nowrap;
}

.prog_tree_ratio {
    flex: 0 0 2.8rem;
    text-align: right;
    white-space: nowrap;
    opacity: 0.8;
}

.prog_tree_up {
    color: var(--c-accent);
}

.prog_tree_down {
    color: var(--c-node-removed);
}

.prog_tree_apply {
    display: inline-flex;
    padding: 0;
    border: none;
    background: none;
    color: var(--c-accent);
    cursor: pointer;
}
</style>
