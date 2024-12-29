<template>
    <g v-if="store">
        <g v-for="link in store.links">
            <LinkComp :link="link" :store="store" />
        </g>
        <g v-for="node in store.nodes" :key="node.internal_id">
            <NodeComp :subject="node" :store="store" :mode="displayMode"
                @edit-point-clicked="emit('editPointClicked', $event)"
                @prop-point-clicked="emit('propPointClicked', $event)"
                @instance-search-clicked="emit('instanceSearchClicked', $event)" />
        </g>
    </g>
</template>
<script setup lang="ts">
import { defineProps } from 'vue'
import { Link } from '@/utils/sparql/representation';
import NodeComp from './Node.vue';
import LinkComp from './Link.vue';
import type { NodeLinkRepository } from '@/utils/sparql/store';
import { DisplayMode, InstanceSelectorOpenEvent, OutlinkSelectorOpenEvent } from '@/utils/sparql/helpers';
import type { PropertiesOpenEvent } from '@/utils/sparql/querymapper';
const emit = defineEmits<{
    editPointClicked: [value: OutlinkSelectorOpenEvent]
    propPointClicked: [value: PropertiesOpenEvent]
    instanceSearchClicked: [value: InstanceSelectorOpenEvent]
}>()

const { store } = defineProps({
    store: {
        type: Object as () => NodeLinkRepository,
        required: true
    },
    displayMode: {
        type: String as () => DisplayMode,
        default: DisplayMode.SELECT
    }
})

</script>
<style lang="css" scoped></style>