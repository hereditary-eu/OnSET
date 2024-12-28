<template>
    <div>
        <div class="node_link_carousel" v-if="!ui_state.collapsed">
            <Loading v-if="ui_state.loading"></Loading>
            <div v-else v-for="result of node_link_elements">
                <div class="node_link_element" @click="selected_node(result)">
                    <div v-if="result.link">
                        <svg :width="NODE_WIDTH * 2 + LINK_WIDTH" :height="NODE_HEIGHT">
                            <NodeLink :link="result.link"></NodeLink>
                        </svg>
                    </div>
                    <div v-else>
                        <svg :width="NODE_WIDTH" :height="NODE_HEIGHT">
                            <Node :subject="result.subject"></Node>
                        </svg>
                    </div>
                </div>
            </div>
        </div>
        <div v-else>
            <OnsetBtn @click="selected_node(null)">Restart (current start: {{ ui_state.selected_link ?
                (ui_state.selected_link.link ? ui_state.selected_link.link.label : ui_state.selected_link.subject.label)
                : ''
                }})
            </OnsetBtn>
        </div>
    </div>
</template>
<script setup lang="ts">
import { Api, type FuzzyQueryResult } from '@/api/client.ts/Api';
import { BACKEND_URL } from '@/utils/config';
import { MixedResponse, type FuzzyQueryRequest } from '@/utils/sparql/representation';
import { ref, watch, reactive, defineEmits } from 'vue';
import Node from './elements/Node.vue';
import NodeLink from './elements/NodeLink.vue';
import OnsetBtn from '@/components/ui/OnsetBtn.vue';
import { LINK_WIDTH, NODE_HEIGHT, NODE_WIDTH } from '@/utils/sparql/helpers';
import Loading from '@/components/ui/Loading.vue';

const emits = defineEmits<{
    select: [value: MixedResponse]
}>()

const ui_state = reactive({
    collapsed: false,
    selected_link: null as MixedResponse | null,
    loading: false
})

const selected_node = (node: MixedResponse) => {
    ui_state.collapsed = !!node
    ui_state.selected_link = node
    emits('select', node)
}

const api = new Api({
    baseURL: BACKEND_URL
})
const { query } = defineProps({
    query: {
        type: Object as () => FuzzyQueryRequest,
        required: true
    }
})

const node_link_elements = ref([] as MixedResponse[])

const fetchNodeLinkElements = async () => {
    ui_state.loading = true
    const response = await api.classes.searchClassesClassesSearchPost(query)
    node_link_elements.value = response.data.results.map((result) => {
        const resp = new MixedResponse(result)
        if (resp.link) {
            resp.link.from_subject.width = NODE_WIDTH
            resp.link.from_subject.height = NODE_HEIGHT
            resp.link.to_subject.x = NODE_WIDTH + LINK_WIDTH
            resp.link.to_subject.width = NODE_WIDTH
            resp.link.to_subject.height = NODE_HEIGHT
        } else {
            resp.subject.width = NODE_WIDTH
            resp.subject.height = NODE_HEIGHT
        }
        return resp
    })
    ui_state.loading = false
}

watch(() => query, fetchNodeLinkElements, { immediate: true, deep: true })
</script>
<style lang="scss">
.node_link_carousel {
    display: flex;
    justify-content: space-around;
    justify-items: center;
    align-items: center;
    padding: 0.5rem;
    border-bottom: 1px solid #e0e0e0;
    flex-wrap: wrap;
    overflow-x: auto;
    max-height: 28rem;
}

.node_link_element {
    margin: 0.5rem;
    padding: 0.5rem;
    border: 1px solid #8fa88f;
    border-radius: 0.5rem;
    cursor: pointer;
    display: flex;
    justify-content: center;
    align-items: center;
    flex-direction: column;
}
</style>