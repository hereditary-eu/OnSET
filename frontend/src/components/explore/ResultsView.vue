<template>
    <div class="results_view">
        <div class="result_instance_header">Results</div>

        <SelectorGroup v-model="ui_state.result_mode" :options="Object.keys(ResultMode).map(qm => {
            return { value: ResultMode[qm], label: ResultMode[qm] }
        })" :width='"7rem"' :height='"1.2rem"'></SelectorGroup>
        <div v-if="ui_state.result_mode == ResultMode.MINI" class="results_instance_container">
            <div class="result_instance_element" v-for="store of mapped_stores.instances">
                <Result :store="store" :expanded="false" :scale="ui_state.scale" :offset="ui_state.offset">
                </Result>
            </div>
            <Loading v-if="ui_state.loading"></Loading>
            <OnsetBtn v-if="mapped_stores.instances.length > 0 && !ui_state.paging_end" @click="loadMore"
                btn_width="100%" :toggleable="false">Load more</OnsetBtn>
            <div class="result_instance_element" ref="view_container" v-show="mapped_stores.instances.length == 0">
            </div>
        </div>
        <div v-else class="results_instance_container">
            <ResultPlot :store="store" :query_string="query_string"></ResultPlot>
        </div>
    </div>
</template>
<script setup lang="ts">
import { ref, watch, reactive, computed, onMounted, defineProps } from 'vue'
import { SubjectNode, Link, SubQueryType } from '@/utils/sparql/representation';
import NodeComp from './elements/Node.vue';
import Propview from './elements/panels/Propview.vue';
import { InstanceNode, PropertiesOpenEvent, QueryMapper, ResultList, type InstanceNodeLinkRepository } from '@/utils/sparql/querymapper';
import { Vector2, type Vector2Like } from 'three';
import { DisplayMode } from '@/utils/sparql/helpers';
import Loading from '../ui/Loading.vue';
import Result from '../explore/Result.vue';
import ResultPlot from '../explore/ResultPlot.vue';
import OnsetBtn from '../ui/OnsetBtn.vue';
import type { NodeLinkRepository } from '@/utils/sparql/store';
import SelectorGroup from '../ui/SelectorGroup.vue';
import type { NodeLinkRepositoryDiff } from '@/utils/sparql/diff';
enum ResultMode {
    MINI = 'Miniatures',
    PROP = 'Properties',
}
const { store, query_string, diff } = defineProps({
    store: {
        type: Object as () => NodeLinkRepository,
        required: true
    },
    query_string: {
        type: String,
        required: true
    },
    diff: {
        type: Object as () => NodeLinkRepositoryDiff | null,
        default: null
    }
})
const mapper = ref(null as QueryMapper | null)
const mapped_stores = ref(new ResultList())
const view_container = ref(null as SVGSVGElement | null)
const root_subject = ref(null as SubjectNode | null)
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
    paging_end: false,
    result_mode: ResultMode.MINI
})
watch(() => query_string, () => {

    // console.log('Query string changed!', query_string, root_subject.value)

    if (!store) {
        return
    }
    let query_props = store.nodes.flatMap(n => n.subqueries.filter(sq => sq.constraint_type == SubQueryType.QUERY_PROP))
    if (query_props.length > 0) {
        ui_state.result_mode = ResultMode.PROP
    } else {
        ui_state.result_mode = ResultMode.MINI
    }

    if (mapped_stores.value.instances.length == 0) {
        ui_state.initial_size.x = view_container.value?.clientWidth || 0
        ui_state.initial_size.y = view_container.value?.clientHeight || 0
        // ui_state.initial_size.x -= 50
        // ui_state.initial_size.y -= 50
    }
    mapper.value = new QueryMapper(store, ui_state.initial_size)
    ui_state.paging_offset = 0
    ui_state.paging_end = false
    mapped_stores.value = new ResultList()
    loadMore().catch((err) => {
        console.error('Error while mapping query!', err)
        ui_state.loading = false
    })
}, { deep: true })
const updateSize = () => {
    if (view_container.value) {
        ui_state.computed_size.x = view_container.value?.clientWidth || 0
        ui_state.computed_size.y = view_container.value?.clientHeight || 0
    }
}
const loadMore = async () => {
    let query_id = ui_state.last_query_id + 1
    ui_state.last_query_id = query_id
    ui_state.loading = true
    const retrieved_stores = await mapper.value.runAndMap(query_string, ui_state.paging_offset)
    updateSize()
    const scalings = mapper.value.scalingFactors()
    // console.log('Mapped results!', mapped_stores, query_id, ui_state.last_query_id)
    if (query_id == ui_state.last_query_id) {
        ui_state.scale = scalings.scale
        ui_state.offset = scalings.offset
        ui_state.computed_size = scalings.size

        ui_state.paging_offset += retrieved_stores.instances.length
        mapped_stores.value.instances = mapped_stores.value.instances.concat(retrieved_stores.instances)
        if (retrieved_stores.instances.length == 0) {
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
    justify-content: start;
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
    margin-top: 10px;
}

.result_instance_element {
    max-width: 95%;
    max-height: 20%;
    height: 10%;
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
    margin-bottom: 12px;
}

.result_instance_overview_header {
    font-size: 2rem;
}
</style>
