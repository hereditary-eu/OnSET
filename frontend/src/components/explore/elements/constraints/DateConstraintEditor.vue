<template>
    <div class="constraint">
        <span class="constraint_label">{{ constraint.link.label }}</span><span class="constraint_select"><select
                @change="change_operator" :value="constraint.type">
                <option v-for="option in operator_options" :value="option.value">{{ option.label }}</option>
            </select></span><span><input type="date" v-model="constraint.value" class="constraint_input"></span>
    </div>
</template>
<script setup lang="ts">
import { Constraint, DateConstraint, NumberConstraint, NumberConstraintType, StringConstraint, StringConstraintType } from '@/utils/sparql/representation';
import { defineProps, defineModel, computed } from 'vue'

const { constraint } = defineProps({
    constraint: {
        type: Object as () => DateConstraint,
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
<style lang="scss">
.constraint_label {
    margin-right: 5px;
}

.constraint_select {
    margin-right: 5px;
    border: rgb(105, 132, 99) 1px solid;
    border-radius: 0px;

}

.constraint_input {
    width: 50px;
    border: rgb(105, 132, 99) 1px solid;
    border-radius: 0px;
}
</style>
