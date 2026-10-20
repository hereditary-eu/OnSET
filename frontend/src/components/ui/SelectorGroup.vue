<template>
    <div class="selection_group toolbar">
        <OnsetBtn v-for="option in options_selections" :key="option.value" :toggleable="true"
            v-model="option.selected" @click="selection = option.value" :btn_width="width" :btn_height="height"
            :size="size">
            {{ option.label }}
        </OnsetBtn>
    </div>
</template>
<script setup lang="ts">
import OnsetBtn from './OnsetBtn.vue';
import { computed } from 'vue';
interface Option {
    value: string;
    label: string;
}
const { options } = defineProps({
    options: {
        type: Array as () => Option[],
        required: true
    },
    width: {
        type: String,
        required: false,
        default: ''
    },
    height: {
        type: String,
        required: false,
        default: ''
    },
    size: {
        type: String as () => 'small' | 'default',
        default: 'small'
    }
})
const selection = defineModel({
    type: String,
    default: ''
})
const options_selections = computed(() => options.map(option => {
    return {
        selected: option.value === selection.value,
        ...option
    }
}))
</script>
<style>
.selection_group {
    gap: var(--space-1);
}

.selection_group .onset_btn:not(:first-child) {
    margin-left: -1px;
}
</style>
