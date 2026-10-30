<template>
    <!-- Settings of the tree expansion: the levels of modifications (depth), how many
         modifications of a level are continued (branching) and the links sampled for each.
         Like the constraint settings, numbers apply on blur/Enter. -->
    <div class="prog_dset">
        <div class="prog_dset_row">
            <span class="prog_dset_name"
                title="Levels of modifications: 1 changes the current query once, deeper levels continue from the results">
                Depth</span>
            <span class="prog_dset_depths">
                <OnsetBtn v-for="d in depths" :key="d" size="small" :model-value="settings.depth == d"
                    :title="d == 1 ? 'Modifications of the current query' : `${d} steps of modifications`"
                    @click="update({ depth: d })">{{ d }}</OnsetBtn>
            </span>
        </div>
        <div class="prog_dset_row" :class="{ prog_dset_off: settings.depth == 1 }">
            <label class="prog_dset_name" for="prog_dset_branching"
                title="Modifications of each level that are continued, spread over their row counts">Expanded per level</label>
            <input id="prog_dset_branching" class="prog_dset_input" type="number" min="1"
                :max="max_branching ?? undefined" :value="settings.branching" :disabled="settings.depth == 1"
                @change="update({ branching: ($event.target as HTMLInputElement).valueAsNumber })">
        </div>
        <div class="prog_dset_row" :class="{ prog_dset_off: settings.depth == 1 }">
            <label class="prog_dset_name" for="prog_dset_children"
                title="Links sampled for each expanded modification">Links per node</label>
            <input id="prog_dset_children" class="prog_dset_input" type="number" min="1"
                :max="max_children ?? undefined" :value="settings.child_sample_size" :disabled="settings.depth == 1"
                @change="update({ child_sample_size: ($event.target as HTMLInputElement).valueAsNumber })">
        </div>
    </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import OnsetBtn from '@/components/ui/OnsetBtn.vue'
import type { DepthSettings } from '@/utils/progressive/types'

const { settings, max_depth = null, max_branching = null, max_children = null } = defineProps<{
    settings: DepthSettings
    /** caps of the configuration */
    max_depth?: number | null
    max_branching?: number | null
    max_children?: number | null
}>()
const emit = defineEmits<{
    update: [settings: Partial<DepthSettings>]
}>()

const depths = computed(() => Array.from({ length: Math.max(1, max_depth ?? 1) }, (_, i) => i + 1))
const update = (settings: Partial<DepthSettings>) => emit('update', settings)
</script>
<style scoped>
.prog_dset {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: var(--space-1);
    border: 1px solid var(--c-border);
    border-radius: var(--radius);
    background: var(--c-surface);
    font-size: var(--fs-xs);
}

.prog_dset_row {
    display: flex;
    align-items: center;
    gap: var(--space-1);
}

.prog_dset_off {
    opacity: 0.5;
}

.prog_dset_name {
    flex: 0 0 7.5rem;
    opacity: 0.8;
}

.prog_dset_depths {
    display: inline-flex;
    gap: 2px;
}

.prog_dset_input {
    width: 3.5rem;
    padding: 0 var(--space-1);
    border: 1px solid var(--c-border-ctrl);
    border-radius: var(--radius);
    font-size: inherit;
}
</style>
