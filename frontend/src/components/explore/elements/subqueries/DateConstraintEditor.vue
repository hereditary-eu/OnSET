<template>
    <div class="constraint">
        <span class="constraint_label">{{ constraint.link.label }}</span>
        <select @change="change_operator" :value="constraint.type">
            <option v-for="option in operator_options" :value="option.value">{{ option.label }}</option>
        </select>
        <input type="date" v-model="date_value">
    </div>
</template>
<script setup lang="ts">
import { DateConstraint, NumberConstraintType } from '@/utils/sparql/representation';
import { ref, watch } from 'vue'

const { constraint } = defineProps({
    constraint: {
        type: Object as () => DateConstraint,
        required: true
    }
})
const date_value = ref((constraint.value && constraint.value instanceof Date) ? constraint.value.toISOString().split('T')[0] : "")

const operator_options = [
    { value: NumberConstraintType.EQUALS, label: '=' },
    { value: NumberConstraintType.GREATER, label: '>' },
    { value: NumberConstraintType.LESS, label: '<' },
]
const change_operator = (event: Event) => {
    const target = event.target as HTMLSelectElement
    constraint.type = target.value as NumberConstraintType
}
watch(() => date_value, () => {
    // console.log('date_value changed!', date_value.value)
    constraint.value = new Date(date_value.value)
}, { deep: true })
</script>
