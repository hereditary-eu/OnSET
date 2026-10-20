<script setup lang="ts">
import { computed, type ModelRef } from 'vue'
import OnsetIcon from './OnsetIcon.vue'

const model: ModelRef<boolean> = defineModel({ type: Boolean, default: false })
const props = defineProps({
    // explicit sizes are optional: buttons size to their content by default
    btn_height: {
        type: String,
        default: ''
    },
    btn_width: {
        type: String,
        default: ''
    },
    // toggleable buttons flip v-model on click and show a selected state
    toggleable: {
        type: Boolean,
        default: true
    },
    active: {
        type: Boolean,
        default: true
    },
    // optional leading mdi icon, e.g. "mdi-history"
    icon: {
        type: String,
        default: ''
    },
    size: {
        type: String as () => 'small' | 'default',
        default: 'default'
    }
})
const emit = defineEmits(['click'])
function update(evt: MouseEvent) {
    evt.preventDefault()
    if (!props.active) {
        return
    }
    emit('click', evt)
    if (props.toggleable) {
        model.value = !model.value
    }
}
const clses = computed(() => ({
    'onset_btn_small': props.size == 'small',
    'onset_btn_disabled': !props.active,
    'onset_btn_selected': props.toggleable && model.value,
}))
const sizing = computed(() => ({
    height: props.btn_height || undefined,
    width: props.btn_width || undefined,
}))
</script>
<template>
    <button type="button" class="onset_btn" :class="clses" :style="sizing" :aria-disabled="!props.active"
        @click="update">
        <OnsetIcon v-if="props.icon" :icon="props.icon" />
        <slot></slot>
    </button>
</template>
<style>
.onset_btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-1);
    flex: 0 0 auto;
    height: var(--control-h);
    min-width: var(--control-h);
    padding: 0 var(--space-2);
    font: inherit;
    font-size: var(--fs-sm);
    line-height: 1;
    white-space: nowrap;
    color: inherit;
    border: 1px solid var(--c-border-ctrl);
    border-radius: var(--radius);
    background-color: var(--c-surface);
    cursor: pointer;
}

.onset_btn_small {
    height: var(--control-h-sm);
    min-width: var(--control-h-sm);
    padding: 0 var(--space-1);
    font-size: var(--fs-xs);
}

.onset_btn:hover,
.onset_btn:active {
    border-color: var(--c-accent);
}

.onset_btn_selected {
    background-color: var(--c-accent-soft);
}

.onset_btn_disabled {
    cursor: not-allowed;
    border-color: #dcdcdc;
    background-color: var(--c-disabled);
}
</style>
