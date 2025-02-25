<template>
    <div class="selection_group">
        <OnsetBtn v-for="option in options_selections" :key="option.value" :toggleable="true" :value="option.value"
            :label="option.label" v-model="option.selected" @click="selection = option.value" :btn_width="width" :btn_height="height">
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
    defaultOption: {
        type: String,
        required: false,
        default: ''
    },
    width: {
        type: String,
        required: false,
        default: '20rem'
    },
    height: {
        type: String,
        required: false,
        default: '2rem'
    }
})
const options_selections = computed(() => options.map(option => {
    return {
        selected: option.value === selection.value,
        ...option
    }

}))
const selection = defineModel({
    type: String,
    default: ''
})

</script>
<style lang="css" scoped>
.selection_group {
    display: flex;
    flex-direction: row;
    justify-items: center;
    align-items: center;
}
</style>