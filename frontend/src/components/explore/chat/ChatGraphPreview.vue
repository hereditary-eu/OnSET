<template>
    <!-- Mini graph of the subjects/links a tool call added (highlighted) or removed (struck),
         drawn with the editor's graph components and fitted to the box via the viewBox. -->
    <svg class="chat_graph_preview" :class="{ chat_graph_preview_tall: has_subqueries }" :viewBox="view_box"
        preserveAspectRatio="xMidYMid meet">
        <GraphView :store="repos.after" :diff="diff" :display-mode="DisplayMode.SELECT"></GraphView>
    </svg>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import GraphView from '../elements/GraphView.vue'
import { CONSTRAINT_PADDING, DisplayMode, SUBQUERY_INDENT } from '@/utils/sparql/helpers'
import type { SubjectNode } from '@/utils/sparql/representation'
import { NodeLinkRepositoryDiff } from '@/utils/sparql/diff'
import { changeRepositories } from '@/utils/agent/graph_sync'
import type { GraphChange, GraphDetails } from '@/utils/agent/protocol'

const { change, details = null } = defineProps<{
    change: GraphChange
    details?: GraphDetails | null
}>()

const PADDING = 12
const MIN_WIDTH = 300
const MIN_HEIGHT = 64

const repos = computed(() => changeRepositories(change, details))
const diff = computed(() => new NodeLinkRepositoryDiff(repos.value.before, repos.value.after))
// a node's extent with its subqueries, which hang below it (Node.vue/Subquery.vue layout)
const extent = (n: SubjectNode) => {
    const subqueries = (n.subqueries || []).filter((sq) => sq != null)
    const below = subqueries.reduce((sum, sq) => sum + sq.height + CONSTRAINT_PADDING, 0)
    const right = Math.max(n.width, ...subqueries.map((sq) => n.width / 2 + 2 * SUBQUERY_INDENT + sq.width))
    return { right: n.x + right, bottom: n.y + n.height + below }
}
const has_subqueries = computed(() => [...repos.value.before.nodes, ...repos.value.after.nodes]
    .some((n) => n.subqueries?.length))
const view_box = computed(() => {
    const nodes = [...repos.value.before.nodes, ...repos.value.after.nodes]
    if (!nodes.length) {
        return '0 0 100 30'
    }
    const min_x = Math.min(...nodes.map((n) => n.x))
    const min_y = Math.min(...nodes.map((n) => n.y))
    const max_x = Math.max(...nodes.map((n) => extent(n).right))
    const max_y = Math.max(...nodes.map((n) => extent(n).bottom))
    // a minimum extent keeps small changes (one node) at about the editor's scale
    const width = Math.max(max_x - min_x + 2 * PADDING, MIN_WIDTH)
    const height = Math.max(max_y - min_y + 2 * PADDING, MIN_HEIGHT)
    const x = (min_x + max_x - width) / 2
    const y = (min_y + max_y - height) / 2
    return `${x} ${y} ${width} ${height}`
})
</script>
<style scoped>
.chat_graph_preview {
    display: block;
    width: 100%;
    height: 4.5rem;
    border-top: 1px solid var(--c-border);
    background: var(--c-surface);
    pointer-events: none;
}

/* nodes with subqueries (e.g. progressive constraints) are about twice as tall */
.chat_graph_preview_tall {
    height: 7rem;
}
</style>
