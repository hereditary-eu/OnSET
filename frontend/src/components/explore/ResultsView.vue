<template>
    <div class="results_view">
        <div class="result_instance_header">Results</div>
        <div class="results_instance_container">
            <div class="result_instance_element" v-for="subject of mapped_root_nodes">
                <ResultView :subject="subject" :expanded="false" :scale="ui_state.scale" :offset="ui_state.offset">
                </ResultView>
            </div>
            <Loading v-if="ui_state.loading"></Loading>
            <OnsetBtn v-if="mapped_root_nodes.length > 0 && !ui_state.paging_end" @click="loadMore" btn_width="100%"
                :toggleable="false">Load more</OnsetBtn>
            <div class="result_instance_element" ref="view_container" v-show="mapped_root_nodes.length == 0"></div>
        </div>
    </div>
</template>
<script setup lang="ts">
import { ref, watch, reactive, computed, onMounted, defineProps } from 'vue'
import { MixedResponse, Node, Link } from '@/utils/sparql/representation';
import NodeComp from './elements/Node.vue';
import Propview from './elements/Propview.vue';
import { InstanceNode, PropertiesOpenEvent, QueryMapper } from '@/utils/sparql/querymapper';
import { Vector2, type Vector2Like } from 'three';
import { DisplayMode } from '@/utils/sparql/helpers';
import Loading from '../ui/Loading.vue';
import ResultView from '../explore/Result.vue';
import OnsetBtn from '../ui/OnsetBtn.vue';

const { root_node, query_string } = defineProps({
    root_node: {
        type: Object as () => MixedResponse,
        required: true
    },
    query_string: {
        type: String,
        required: true
    }
})
const mapper = ref(null as QueryMapper | null)
const mapped_root_nodes = ref([] as InstanceNode[])
const view_container = ref(null as SVGSVGElement | null)
const root_subject = ref(null as Node | null)
const ui_state = reactive({
    loading: false,
    last_query_id: 0,
    scale: 1,
    offset: new Vector2(0, 0),
    initial_size: new Vector2(0, 0),
    computed_size: new Vector2(0, 0),
    prop_open: false,
    prop_open_event: null as PropertiesOpenEvent | null,
    paging_offset: 0,
    paging_end: false
})
watch(() => query_string, () => {

    if (root_node.link) {
        root_subject.value = root_node.link.from_subject
    } else if (root_node.subject) {
        root_subject.value = root_node.subject
    }
    console.log('Query string changed!', query_string, root_subject.value)
    if (mapped_root_nodes.value.length == 0) {
        ui_state.initial_size.x = view_container.value?.clientWidth || 0
        ui_state.initial_size.y = view_container.value?.clientHeight || 0
        ui_state.initial_size.x -= 50
        ui_state.initial_size.y -= 50
    }
    mapper.value = new QueryMapper(root_subject.value, ui_state.initial_size)
    ui_state.paging_offset = 0
    mapped_root_nodes.value = []
    loadMore().catch((err) => {
        console.error('Error while mapping query!', err)
        ui_state.loading = false
    })
}, { deep: true })

const loadMore = async () => {
    let query_id = ui_state.last_query_id + 1
    ui_state.last_query_id = query_id
    ui_state.loading = true
    const results = await mapper.value.runAndMap(query_string, ui_state.paging_offset)

    console.log('Mapped results!', results, query_id, ui_state.last_query_id)
    if (query_id == ui_state.last_query_id) {
        mapped_root_nodes.value = results.mapped_nodes
        ui_state.scale = results.scale
        ui_state.offset = results.offset
        ui_state.computed_size = results.size

        ui_state.paging_offset += results.mapped_nodes.length
        mapped_root_nodes.value = mapped_root_nodes.value.concat(results.mapped_nodes)
        if (results.mapped_nodes.length == 0) {
            ui_state.paging_end = true
        }
        ui_state.loading = false

    }
}
</script>
<style lang="scss">
.results_view {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 70vh;
    width: 30%;
    border-left: 1px solid rgb(192, 213, 191);
}

.results_instance_container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    width: 100%;
    height: 100%;
    overflow: auto;
    padding: 5px;
}

.result_instance_element {
    width: 95%;
    height: 20%;
    display: flex;
    justify-content: center;
    align-items: center;
    margin: 4px;
}

.result_instance_svg {
    width: 100%;
    height: 100%;
}

.result_interact_svg {
    width: 100%;
    height: 100%;
}

.result_instance_header {
    font-size: 1.5rem;
    font-weight: bold;
    padding: 5px;
    border-bottom: 1px solid rgb(192, 213, 191);
    width: 100%;
}

.result_instance_overview_header {
    font-size: 2rem;
}
</style>
