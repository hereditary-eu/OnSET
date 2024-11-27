<template>
    <div>
        <div class="node_link_carousel">
            <div v-for="result of node_link_elements">
                <div class="node_link_element">
                    <div v-if="result.link">
                        <svg :width="params.node_width * 2 + params.link_width" :height="params.node_height">
                            <NodeLink :link="result.link"></NodeLink>
                        </svg>
                    </div>
                    <div v-else>
                        <svg :width="params.node_width" :height="params.node_height">
                            <Node :subject="result.subject"></Node>
                        </svg>
                    </div>
                </div>

            </div>
        </div>
    </div>
</template>
<script setup lang="ts">
import { Api, type FuzzyQueryResult } from '@/api/client.ts/Api';
import { BACKEND_URL } from '@/utils/config';
import { MixedResponse, type FuzzyQueryRequest } from '@/utils/sparql/representation';
import { ref, watch, reactive } from 'vue';
import Node from './elements/Node.vue';
import NodeLink from './elements/NodeLink.vue';
const params = reactive({
    node_width: 150,
    node_height: 100,
    link_width: 75,
})

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
    const response = await api.classes.searchClassesClassesSearchPost(query)
    node_link_elements.value = response.data.results.map((result) => {
        const resp = new MixedResponse(result)
        if (resp.link) {
            resp.link.from_subject.width = params.node_width
            resp.link.from_subject.height = params.node_height
            resp.link.to_subject.x = params.node_width + params.link_width
            resp.link.to_subject.width = params.node_width
            resp.link.to_subject.height = params.node_height
        } else {
            resp.subject.width = params.node_width
            resp.subject.height = params.node_height
        }
        return resp
    })
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