<template>
    <g>
        <path :d="`M 0,-${extend_path} v ${extend_path}`" class="constraint_connection" />
        <path :d="`M 0,0 V ${constraint.height / 2} H ${constraint.width * 0.2}`" class="constraint_connection" />
        <rect :x="constraint.width * 0.2" :y="0" :width="constraint.width * 0.8" :height="constraint.height"
            class="constraint_box" />
        <foreignObject :x="constraint.width * 0.2" :y="0" :width="constraint.width * 0.8" :height="constraint.height">
            <div class="constraint">
                <!-- {{ constraint.link.to_proptype }} -->
                <NumberConstraintEditor v-if="(constraint.constraint_type == ConstraintType.NUMBER)"
                    :constraint="(constraint as NumberConstraint)" />
                <StringConstraintEditor v-if="(constraint.constraint_type == ConstraintType.STRING)"
                    :constraint="(constraint as StringConstraint)" />
                <DateConstraintEditor v-if="(constraint.constraint_type == ConstraintType.DATE)"
                    :constraint="(constraint as DateConstraint)" />
            </div>
        </foreignObject>
    </g>
</template>
<script setup lang="ts">
import { Constraint, ConstraintType, DateConstraint, NumberConstraint, StringConstraint } from '@/utils/sparql/representation';
import { defineProps, defineModel } from 'vue'
import NumberConstraintEditor from './constraints/NumberConstraintEditor.vue';
import StringConstraintEditor from './constraints/StringConstraintEditor.vue';
import DateConstraintEditor from './constraints/DateConstraintEditor.vue';

const { extend_path, constraint } = defineProps({
    extend_path: {
        type: Number,
        required: true
    },
    constraint: {
        type: Object as () => Constraint,
        required: true
    }
})


</script>
<style lang="scss">
.constraint_connection {
    fill: none;
    stroke: #828282;
    stroke-width: 1px;
}

.constraint_box {
    fill: #dfdfdf;
    stroke: #a0c2a9;
    stroke-width: 1px;
    stroke-dasharray: 5, 5;
}

.constraint {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    // justify-items: center;

}
</style>
