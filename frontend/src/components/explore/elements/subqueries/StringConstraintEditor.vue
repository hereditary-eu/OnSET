<template>
    <div class="constraint constraint_column">
        <span class="constraint_label">{{ constraint.link.label }}</span>
        <div class="constraint">
            <select @change="change_operator" :value="constraint.type">
                <option v-for="option in operator_options" :value="option.value">{{ option.label }}</option>
            </select>
            <input v-model="constraint.value">
        </div>
    </div>
</template>
<script setup lang="ts">
import { StringConstraint, StringConstraintType } from '@/utils/sparql/representation';

const { constraint } = defineProps({
    constraint: {
        type: Object as () => StringConstraint,
        required: true
    }
})
const operator_options = [
    { value: StringConstraintType.EQUALS, label: '=' },
    { value: StringConstraintType.NEQUALS, label: '!=' },
    { value: StringConstraintType.CONTAINS, label: 'contains' },
    { value: StringConstraintType.ENDSWITH, label: 'ends with' },
    { value: StringConstraintType.STARTSWITH, label: 'starts with' },
    { value: StringConstraintType.REGEX, label: 'matches regex' },
]
const change_operator = (event: Event) => {
    const target = event.target as HTMLSelectElement
    constraint.type = target.value as StringConstraintType
}
</script>
