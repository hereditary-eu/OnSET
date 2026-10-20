<template>
    <div class="node_link_selector">
        <div class="node_link_list" v-if="!ui_state.collapsed">
            <Loading v-if="ui_state.loading"></Loading>
            <template v-else>
                <div v-for="result of node_link_elements" class="node_link_element" @click="selected_node(result)">
                    <svg :width="previewSize(result).width" :height="previewSize(result).height">
                        <GraphView :store="result.store"></GraphView>
                    </svg>
                </div>
            </template>
        </div>
        <OnsetBtn v-else size="small" :toggleable="false" icon="mdi-restart" @click="selected_node(null)">
            Restart (current start: {{ ui_state.selected_link ?
                (ui_state.selected_link.link ? ui_state.selected_link.link.label : ui_state.selected_link.subject.label)
                : '' }})
        </OnsetBtn>
    </div>
</template>
<script setup lang="ts">
import { type FuzzyQueryResult } from '@/api/client.ts/Api';
import {  SubjectNode, type FuzzyQueryRequest } from '@/utils/sparql/representation';
import { ref, watch, reactive } from 'vue';
import OnsetBtn from '@/components/ui/OnsetBtn.vue';
import { fitNode, linkWidth, NODE_HEIGHT } from '@/utils/sparql/helpers';
import Loading from '@/components/ui/Loading.vue';
import GraphView from './elements/GraphView.vue';
import { MixedResponse } from '@/utils/sparql/store';
import { api } from '@/utils/api'

const emits = defineEmits<{
    select: [value: MixedResponse<SubjectNode>]
}>()

const ui_state = reactive({
    collapsed: false,
    selected_link: null as MixedResponse<SubjectNode> | null,
    loading: false
})

const selected_node = (node: MixedResponse<SubjectNode>) => {
    ui_state.collapsed = !!node
    ui_state.selected_link = node
    emits('select', node)
}

const { query } = defineProps({
    query: {
        type: Object as () => FuzzyQueryRequest,
        required: true
    }
})

const node_link_elements = ref([] as MixedResponse<SubjectNode>[])

const fetchNodeLinkElements = async () => {
    ui_state.loading = true
    const response = await api.classes.searchClassesClassesSearchPost(query)
    node_link_elements.value = response.data.results.map((result) => {
        const resp = new MixedResponse<SubjectNode>(result)
        if (resp.link) {
            let from = fitNode(resp.store.from(resp.link))
            let to = fitNode(resp.store.to(resp.link))
            from.x = 0
            from.y = 0
            to.x = from.width + linkWidth(resp.link.label)
            to.y = 0
        } else {
            fitNode(resp.subject)
        }
        return resp
    })
    ui_state.loading = false
}

const previewSize = (result: MixedResponse<SubjectNode>) => {
    if (result.link) {
        const to = result.store.to(result.link)
        return { width: to.x + to.width, height: NODE_HEIGHT }
    }
    return { width: result.subject.width, height: NODE_HEIGHT }
}

watch(() => query, fetchNodeLinkElements, { immediate: true, deep: true })
</script>
<style scoped>
.node_link_list {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
}

.node_link_element {
    max-width: 100%;
    padding: 2px;
    overflow: hidden;
    border: 1px solid var(--c-accent);
    border-radius: var(--radius);
    cursor: pointer;
}

.node_link_element:hover {
    background: var(--c-hover);
}

.node_link_element svg {
    display: block;
}
</style>
