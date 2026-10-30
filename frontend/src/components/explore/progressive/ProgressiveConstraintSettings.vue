<template>
    <!-- Settings of the constraint modifications: the percentiles of numeric/date values that
         become thresholds (chips, add by typing a value 0-100), the values sampled per
         categorical property and the number of constrained properties. Changes apply on
         blur/Enter, so the panel does not re-count on every keystroke. -->
    <div class="prog_cset">
        <div class="prog_cset_row">
            <span class="prog_cset_name" title="Percentiles of numeric and date values that become thresholds">
                Percentiles</span>
            <span class="prog_cset_chips">
                <span v-for="p in settings.numeric_percentiles" :key="p" class="prog_cset_chip">
                    p{{ p }}
                    <button type="button" class="prog_cset_chip_remove" :title="`Remove p${p}`"
                        @click="update({ numeric_percentiles: settings.numeric_percentiles.filter((q) => q != p) })">
                        <OnsetIcon icon="mdi-close" />
                    </button>
                </span>
                <input class="prog_cset_input prog_cset_add" type="text" inputmode="decimal" placeholder="add…"
                    title="Add percentiles (0-100, comma-separated)" :class="{ prog_cset_invalid: invalid }"
                    v-model="draft" @keydown.enter.prevent="addPercentiles" @blur="addPercentiles">
            </span>
        </div>
        <div v-if="invalid" class="prog_cset_error">Percentiles are numbers from 0 to 100</div>
        <div class="prog_cset_row">
            <label class="prog_cset_name" for="prog_cset_categories"
                title="Values sampled per categorical property, by their frequency">Values per category</label>
            <input id="prog_cset_categories" class="prog_cset_input" type="number" min="1"
                :value="settings.categorical_samples"
                @change="update({ categorical_samples: ($event.target as HTMLInputElement).valueAsNumber })">
        </div>
        <div class="prog_cset_row">
            <label class="prog_cset_name" for="prog_cset_properties"
                title="Constrained properties to sample, each yields several modifications">Properties</label>
            <input id="prog_cset_properties" class="prog_cset_input" type="number" min="0"
                :max="max_properties ?? undefined" :value="settings.constraint_sample_size"
                @change="update({ constraint_sample_size: ($event.target as HTMLInputElement).valueAsNumber })">
        </div>
    </div>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import OnsetIcon from '@/components/ui/OnsetIcon.vue'
import type { ConstraintSettings } from '@/utils/progressive/types'
import { parsePercentiles } from '@/utils/progressive/histogram'

const { settings, max_properties = null } = defineProps<{
    settings: ConstraintSettings
    /** cap of the constrained properties of the configuration */
    max_properties?: number | null
}>()
const emit = defineEmits<{
    update: [settings: Partial<ConstraintSettings>]
}>()

const draft = ref('')
const invalid = ref(false)
const update = (settings: Partial<ConstraintSettings>) => emit('update', settings)
const addPercentiles = () => {
    if (!draft.value.trim()) {
        invalid.value = false
        return
    }
    const parsed = parsePercentiles(draft.value)
    invalid.value = parsed == null
    if (parsed) {
        update({ numeric_percentiles: [...settings.numeric_percentiles, ...parsed] })
        draft.value = ''
    }
}
</script>
<style scoped>
.prog_cset {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: var(--space-1);
    border: 1px solid var(--c-border);
    border-radius: var(--radius);
    background: var(--c-surface);
    font-size: var(--fs-xs);
}

.prog_cset_row {
    display: flex;
    align-items: center;
    gap: var(--space-1);
}

.prog_cset_name {
    flex: 0 0 7.5rem;
    opacity: 0.8;
}

.prog_cset_chips {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 2px;
}

.prog_cset_chip {
    display: inline-flex;
    align-items: center;
    padding: 0 0 0 var(--space-1);
    border-radius: 999px;
    background: var(--c-constraint, var(--c-hover));
    font-family: var(--font-mono);
}

.prog_cset_chip_remove {
    display: inline-flex;
    padding: 0 2px;
    border: none;
    background: none;
    color: inherit;
    cursor: pointer;
    opacity: 0.7;
}

.prog_cset_chip_remove:hover {
    opacity: 1;
}

.prog_cset_input {
    width: 3.5rem;
    padding: 0 var(--space-1);
    border: 1px solid var(--c-border-ctrl);
    border-radius: var(--radius);
    font-size: inherit;
}

.prog_cset_add {
    width: 4.5rem;
}

.prog_cset_invalid {
    border-color: #b3261e;
}

.prog_cset_error {
    color: #b3261e;
    padding-left: calc(7.5rem + var(--space-1));
}
</style>
