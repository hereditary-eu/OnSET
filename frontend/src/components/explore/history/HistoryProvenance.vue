<template>
    <!-- Who made a history entry: a source badge (robot for the agent) and the icons of its ops,
         grouped by kind with a count. User edits only get a subtle user icon. -->
    <div class="history_prov" :class="`history_prov_${prov.source}`" :title="summary">
        <button v-if="linkable" type="button" class="history_prov_badge history_prov_link"
            title="Show the agent's tool calls in the chat" @click.stop="emit('showInChat', prov.chat_entry_ids!)">
            <OnsetIcon :icon="source.icon" />
        </button>
        <span v-else class="history_prov_badge">
            <OnsetIcon :icon="source.icon" />
        </span>
        <span v-for="group in groups" :key="group.kind" class="history_prov_op"
            :class="`history_prov_${group.style.direction}`"
            :title="group.ops.map((op) => `${group.style.label}${op.label ? `: ${op.label}` : ''}`).join('\n')">
            <OnsetIcon :icon="group.style.icon" />
            <sub v-if="group.ops.length > 1">{{ group.ops.length }}</sub>
        </span>
    </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import OnsetIcon from '@/components/ui/OnsetIcon.vue'
import {
    groupedOps, provenanceSummary, SOURCE_STYLES, userProvenance, type EditProvenance,
} from '@/utils/sparql/provenance'

const props = defineProps<{ provenance?: EditProvenance | null }>()
const emit = defineEmits<{ showInChat: [string[]] }>()

const prov = computed(() => props.provenance ?? userProvenance())
// a revert shows the ops of the entry it went back to
const groups = computed(() => groupedOps(prov.value.source == 'revert' ? prov.value.reverted_from : prov.value))
const source = computed(() => SOURCE_STYLES[prov.value.source] ?? SOURCE_STYLES.user)
const summary = computed(() => provenanceSummary(prov.value))
const linkable = computed(() => prov.value.source == 'agent' && !!prov.value.chat_entry_ids?.length)
</script>
<style scoped>
.history_prov {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    padding: 1px 3px;
    border-radius: var(--radius);
    background: color-mix(in srgb, var(--c-surface) 85%, transparent);
    font-size: var(--fs-xs);
    line-height: 1;
}

.history_prov_badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.3em;
    height: 1.3em;
    padding: 0;
    border: none;
    border-radius: 50%;
    color: inherit;
    background: transparent;
}

.history_prov_user .history_prov_badge {
    opacity: 0.45;
}

.history_prov_agent .history_prov_badge {
    color: var(--c-surface);
    background: var(--c-accent);
}

.history_prov_progressive .history_prov_badge,
.history_prov_revert .history_prov_badge,
.history_prov_import .history_prov_badge {
    color: var(--c-surface);
    background: var(--c-link-normal);
}

.history_prov_link {
    cursor: pointer;
}

.history_prov_link:hover {
    outline: 2px solid var(--c-accent-soft);
}

.history_prov_op {
    display: inline-flex;
    align-items: flex-end;
}

.history_prov_op sub {
    font-size: 0.75em;
    margin-left: -1px;
}

.history_prov_add {
    color: var(--c-link-added);
}

.history_prov_remove {
    color: var(--c-link-removed);
}

.history_prov_change {
    color: var(--c-constraint);
}

/* a revert's ops are those of the entry it went back to */
.history_prov_revert .history_prov_op {
    opacity: 0.6;
}
</style>
