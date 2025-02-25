<template>
    <g>
        <path :d="`M 0,-${extend_path} v ${extend_path}`" class="subquery_connection" />
        <path :d="`M 0,0 V ${subquery.height / 2} H ${subquery.width * 0.2}`" class="subquery_connection" />
        <rect :x="subquery.width * 0.2" :y="0" :width="subquery.width * 0.8" :height="subquery.height"
            class="subquery_box" />
        <circle v-show="show_editpoints" :cx="subquery.width" :cy="0" :r="7" class="edit_point edit_point_delete"
            @click="emit('delete', subquery)">
        </circle>
        <foreignObject :x="subquery.width * 0.2" :y="0" :width="subquery.width * 0.8" :height="subquery.height">
            <div class="subquery">
                <!-- {{ constraint.link.to_proptype }} -->
                <NumberConstraintEditor v-if="(subquery.constraint_type == SubQueryType.NUMBER)"
                    :constraint="(subquery as NumberConstraint)" />
                <StringConstraintEditor v-if="(subquery.constraint_type == SubQueryType.STRING)"
                    :constraint="(subquery as StringConstraint)" />
                <DateConstraintEditor v-if="(subquery.constraint_type == SubQueryType.DATE)"
                    :constraint="(subquery as DateConstraint)" />
                <SubjectConstraintEditor v-if="(subquery.constraint_type == SubQueryType.SUBJECT)"
                    :constraint="(subquery as SubjectConstraint)" :node="node"
                    @open_search="emit('instanceSearchClicked', $event)" />
                <BooleanConstraintEditor v-if="(subquery.constraint_type == SubQueryType.BOOLEAN)"
                    :constraint="(subquery as BooleanConstraint)" />
                <Property v-if="(subquery.constraint_type == SubQueryType.QUERY_PROP)"
                    :query="(subquery as QueryProp)" />
            </div>
        </foreignObject>
    </g>
</template>
<script setup lang="ts">
import { SubQuery, SubQueryType, DateConstraint, SubjectNode, NumberConstraint, StringConstraint, SubjectConstraint, BooleanConstraint, QueryProp } from '@/utils/sparql/representation';
import { defineProps, defineModel } from 'vue'
import NumberConstraintEditor from './constraints/NumberConstraintEditor.vue';
import StringConstraintEditor from './constraints/StringConstraintEditor.vue';
import DateConstraintEditor from './constraints/DateConstraintEditor.vue';
import SubjectConstraintEditor from './constraints/SubjectConstraintEditor.vue';
import type { InstanceSelectorOpenEvent } from '@/utils/sparql/helpers';
import BooleanConstraintEditor from './constraints/BooleanConstraintEditor.vue';
import Property from './Property.vue';
const emit = defineEmits<{
    delete: [value: SubQuery]
    instanceSearchClicked: [value: InstanceSelectorOpenEvent]
}>()
const { extend_path, subquery: subquery } = defineProps({
    extend_path: {
        type: Number,
        required: true
    },
    subquery: {
        type: Object as () => SubQuery,
        required: true
    },
    node: {
        type: Object as () => SubjectNode,
        required: true
    },
    show_editpoints: {
        type: Boolean,
        required: true
    },
})


</script>
<style lang="scss" scoped>
.subquery_connection {
    fill: none;
    stroke: #828282;
    stroke-width: 1px;
}

.subquery_box {
    fill: #dfdfdf;
    stroke: #a0c2a9;
    stroke-width: 1px;
    stroke-dasharray: 5, 5;
}

.subquery {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    // justify-items: center;

}
</style>
