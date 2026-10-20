<template>
    <div class="constraint">
        <span class="constraint_label">{{ constraint.link.label }}</span>
        <select @change="change_operator" :value="constraint.type">
            <option v-for="option in operator_options" :value="option.value">{{ option.label }}</option>
        </select>
        <input type="number" v-model="constraint.value">
    </div>
</template>
<script setup lang="ts">
import { NumberConstraint, NumberConstraintType } from '@/utils/sparql/representation';

const { constraint } = defineProps({
    constraint: {
        type: Object as () => NumberConstraint,
        required: true
    }
})
const operator_options = [
    { value: NumberConstraintType.EQUALS, label: '=' },
    { value: NumberConstraintType.GREATER, label: '>' },
    { value: NumberConstraintType.LESS, label: '<' },
]
const change_operator = (event: Event) => {
    const target = event.target as HTMLSelectElement
    constraint.type = target.value as NumberConstraintType
}
</script>
