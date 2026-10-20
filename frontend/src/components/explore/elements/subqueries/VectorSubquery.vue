<template>
    <div class="constraint constraint_column">
        <span class="constraint_label">{{ constraint.link.label }}</span>
        <div class="constraint">
            <span>Modality:</span>
            <select @change="change_operator" :value="constraint.modality">
                <option v-for="option in operator_options" :value="option.value">{{ option.label }}</option>
            </select>
        </div>
        <div v-if="constraint.modality == VectorSortModality.TEXT" class="constraint">
            <span>Text:</span>
            <input v-model="constraint.input_state.text">
        </div>
        <div v-if="constraint.modality == VectorSortModality.IMAGE" class="constraint constraint_column">
            <span>Draw your search!</span>
            <PictureDrawer v-model="constraint.input_state.image" />
        </div>
    </div>
</template>
<script setup lang="ts">
import PictureDrawer from '@/components/ui/PictureDrawer.vue';
import { debounce } from '@/utils/helpers';
import { VectorSort, VectorSortModality } from '@/utils/sparql/representation';
import { reactive, watch } from 'vue'
import { api } from '@/utils/api'

const { constraint } = defineProps({
    constraint: {
        type: Object as () => VectorSort,
        required: true
    }
})


const editor_data = reactive({
    loading: false,
    error: null as string | null,
})

const operator_options = [
    { value: VectorSortModality.TEXT, label: 'Text' },
    { value: VectorSortModality.IMAGE, label: 'Image' },
]
const change_operator = (event: Event) => {
    const target = event.target as HTMLSelectElement
    constraint.input_state.text = ""
    constraint.input_state.image = null
    constraint.modality = target.value as VectorSortModality
}
watch(() => constraint.input_state.text, () => {
    debounced_vector_refresh()
})
watch(() => constraint.input_state.image, () => {
    debounced_vector_refresh()
})

const debounced_vector_refresh = debounce(() => {
    (async () => {
        editor_data.loading = true
        await constraint.reloadVectorFromState(api)
    })().catch((e) => {
        console.error('Error fetching selection options', e)
    }).finally(() => {
        editor_data.loading = false
    })
}, 300, false)
</script>
