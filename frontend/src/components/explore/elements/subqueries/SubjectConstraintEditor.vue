<template>
    <div class="constraint">
        <span class="constraint_label">is</span>
        <span class="constraint_value" :title="instance_name">{{ instance_name }}</span>
        <OnsetBtn size="small" :toggleable="false" @click="emits('open_search', {
            constraint: constraint,
            node: node
        })">Choose</OnsetBtn>
    </div>
</template>
<script setup lang="ts">
import OnsetBtn from '@/components/ui/OnsetBtn.vue';
import type { InstanceSelectorOpenEvent } from '@/utils/sparql/helpers';
import { readableName } from '@/utils/sparql/querymapper';
import { SubjectNode, SubjectConstraint } from '@/utils/sparql/representation';
import { computed } from 'vue'
const emits = defineEmits<{
    open_search: [value: InstanceSelectorOpenEvent]
}>()
const { constraint } = defineProps({
    constraint: {
        type: Object as () => SubjectConstraint,
        required: true
    },
    node: {
        type: Object as () => SubjectNode,
        required: true
    },
})
const instance_name = computed(() => readableName(constraint.instance?.id, constraint.instance?.label))
</script>
