<template>
    <g v-if="store" class="graph_view">
        <g v-for="link in store.links">
            <LinkComp :link="link" :store="store" :diff="diff" :mode="displayMode"
            @link-edit-clicked="emit('linkEditClicked', $event)"/>
        </g>
        <g v-for="node in store.nodes" :key="node.internal_id">
            <NodeComp :subject="node" :store="store" :mode="displayMode" :diff="diff"
                @link-point-clicked="emit('linkPointClicked', $event)"
                @prop-point-clicked="emit('propPointClicked', $event)"
                @instance-search-clicked="emit('instanceSearchClicked', $event)"
                @type-point-clicked="emit('typePointClicked', $event)" />
        </g>
        <g v-if="diff">
            <g v-for="link in diff.diff_links.removed">
                <LinkComp :link="link.left" :store="store" :diff="diff"  :mode="DisplayMode.SELECT"/>
            </g>
            <g v-for="node in diff.diff_nodes.removed" :key="node.left.internal_id">
                <NodeComp :subject="node.left" :store="store" :mode="DisplayMode.SELECT" :diff="diff"
                    @link-point-clicked="emit('linkPointClicked', $event)"
                    @prop-point-clicked="emit('propPointClicked', $event)"
                    @instance-search-clicked="emit('instanceSearchClicked', $event)" />
            </g>
        </g>
    </g>
</template>
<script setup lang="ts">
import { defineProps } from 'vue'
import { Link } from '@/utils/sparql/representation';
import NodeComp from './Node.vue';
import LinkComp from './Link.vue';
import type { NodeLinkRepository } from '@/utils/sparql/store';
import { DisplayMode, InstanceSelectorOpenEvent, SelectorOpenEvent } from '@/utils/sparql/helpers';
import type { PropertiesOpenEvent } from '@/utils/sparql/querymapper';
import type { NodeLinkRepositoryDiff } from '@/utils/sparql/diff';
const emit = defineEmits<{
    linkPointClicked: [value: SelectorOpenEvent]
    linkEditClicked: [value: SelectorOpenEvent]
    typePointClicked: [value: SelectorOpenEvent]
    propPointClicked: [value: PropertiesOpenEvent]
    instanceSearchClicked: [value: InstanceSelectorOpenEvent]
}>()

const { store, diff, displayMode } = defineProps({
    store: {
        type: Object as () => NodeLinkRepository,
        required: true
    },
    displayMode: {
        type: String as () => DisplayMode,
        default: DisplayMode.SELECT
    },
    diff: {
        type: Object as () => NodeLinkRepositoryDiff | null,
        default: null
    }
})

</script>
<style lang="css" scoped>
.graph_view {
    user-select: none;
}
</style>