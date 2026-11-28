<template>
    <!-- GROUP BY toggle and aggregate of a node or property (see AggregateFunction).
         The controls keep their size while hovered (no popping): the aggregate select is a
         compact Σ until an aggregate is set; collapsible controls fade instead of (un)mounting. -->
    <span class="aggregate_controls" :class="{ aggregate_hidden: !visible }" @pointerdown.stop
        @focusin="focused = true" @focusout="focused = false">
        <OnsetBtn v-if="!readonly" size="small" :model-value="target.group_by" @update:model-value="setGroupBy"
            icon="mdi-group" btn_height="1.25rem" :title="target.group_by ? 'Grouped by (click to ungroup)' : 'Group by'" />
        <OnsetIcon v-else-if="target.group_by" icon="mdi-group" title="Grouped by" />
        <template v-if="!target.group_by">
            <select v-if="!readonly" class="aggregate_select" :class="{ aggregate_select_empty: !target.aggregate }"
                :value="target.aggregate ?? ''" :title="target.aggregate ? 'Aggregate' : 'Aggregate…'"
                @change="setAggregate">
                <option value="">{{ target.aggregate ? 'none' : 'Σ' }}</option>
                <option v-for="fn in options" :key="fn" :value="fn">{{ AGGREGATE_LABELS[fn] }}</option>
            </select>
            <span v-else-if="target.aggregate" class="constraint_aggregate">{{ AGGREGATE_LABELS[target.aggregate] }}</span>
        </template>
    </span>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { AGGREGATE_LABELS, AGGREGATES_OF, AggregateFunction, AggregateKind, isTensorAggregate, type Aggregatable } from '@/utils/sparql/representation'
import { activeConfigId } from '@/utils/api'
import OnsetBtn from '@/components/ui/OnsetBtn.vue'
import OnsetIcon from '@/components/ui/OnsetIcon.vue'

const { target, kind, expanded, readonly, collapsible } = defineProps({
    target: {
        type: Object as () => Aggregatable,
        required: true
    },
    kind: {
        type: String as () => AggregateKind,
        default: AggregateKind.TEXT
    },
    // show collapsible controls even if nothing is set (e.g. while hovered)
    expanded: {
        type: Boolean,
        default: true
    },
    // only show the grouping/aggregate (e.g. in previews of the history)
    readonly: {
        type: Boolean,
        default: false
    },
    // hide everything (also the group toggle) unless expanded, focused or set
    collapsible: {
        type: Boolean,
        default: false
    },
})
const focused = ref(false)
const visible = computed(() => !collapsible || expanded || focused.value || target.group_by || !!target.aggregate)
// the ontology builder's stores (rdflib/Tentris) have no tensor aggregates (QLever only)
const options = computed(() => AGGREGATES_OF[kind].filter((fn) =>
    !(isTensorAggregate(fn) && activeConfigId.value?.startsWith('builder:'))))
const setGroupBy = (value: boolean) => {
    target.group_by = value
    if (value) {
        target.aggregate = null
    }
}
const setAggregate = (event: Event) => {
    const value = (event.target as HTMLSelectElement).value
    target.aggregate = value ? value as AggregateFunction : null
    if (target.aggregate) {
        target.group_by = false
    }
}
</script>
<style>
.aggregate_controls {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    transition: opacity 120ms ease;
}

.aggregate_controls.aggregate_hidden {
    opacity: 0;
    pointer-events: none;
}

.aggregate_controls .aggregate_select {
    font: inherit;
    height: 1.25rem;
    padding: 0 2px;
    border: 1px solid rgb(105, 132, 99);
    border-radius: 0;
    background: var(--c-surface);
}

/* no aggregate yet: a fixed-size Σ instead of the widest option's width */
.aggregate_controls .aggregate_select_empty {
    width: 1.25rem;
    padding: 0;
    text-align: center;
    text-align-last: center;
    appearance: none;
    cursor: pointer;
}

.constraint_aggregate {
    padding: 0 3px;
    font-variant: small-caps;
    color: var(--c-accent, rgb(105, 132, 99));
    border: 1px solid currentColor;
    white-space: nowrap;
}
</style>
