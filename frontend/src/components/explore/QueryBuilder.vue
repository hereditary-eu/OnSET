<template>
    <div class="query_builder">
        <svg class="query_build_wrapper">
            <GraphView :store="store" :display-mode="DisplayMode.EDIT" @edit-point-clicked="clicked_outlink($event)" :diff="diff"
                @instance-search-clicked="clicked_instance($event)"></GraphView>
            <OutLinkSelector :selection_event="ui_state.outlink_event" v-model="ui_state.outlink_display"
                :store="store" @hover_option="preview_link($event)">
            </OutLinkSelector>
            <InstanceSelector :selection_event="ui_state.instance_event" v-model="ui_state.instance_display">
            </InstanceSelector>
            <use xlink:href="#outlink_selector"></use>
            <use xlink:href="#instance_selector"></use>
        </svg>
        <!-- <div id="threed_minimap">
            <Loading v-if="ui_state.loading"></Loading>
            <div id="threed_graph"></div>
        </div> -->
    </div>
</template>
<script setup lang="ts">
import { ref, watch, reactive, computed, onMounted, defineProps, onBeforeMount } from 'vue'
import { SubjectNode, Link } from '@/utils/sparql/representation';
import NodeComp from './elements/Node.vue';
import OutLinkSelector from './elements/panels/OutLinkSelector.vue';
import { DisplayMode, InstanceSelectorOpenEvent, type NodeSide, type OutlinkSelectorOpenEvent } from '@/utils/sparql/helpers';
import InstanceSelector from './elements/panels/InstanceSelector.vue';
import type { MixedResponse, NodeLinkRepository } from '@/utils/sparql/store';
import GraphView from './elements/GraphView.vue';
import { OverviewCircles } from '@/utils/three-man/OverviewCircles';
import { fa } from 'vuetify/locale';
import { Api } from '@/api/client.ts/Api';
import { BACKEND_URL } from '@/utils/config';
import type { SubjectInCircle } from '@/utils/d3-man/CircleMan';
import Loading from '../ui/Loading.vue';
import type { NodeLinkRepositoryDiff } from '@/utils/sparql/diff';

const api = new Api({
    baseURL: BACKEND_URL
})
const { store } = defineProps({
    store: {
        type: Object as () => NodeLinkRepository,
        required: true
    },
    diff: {
        type: Object as () => NodeLinkRepositoryDiff | null,
        default: null
    }
})
const ui_state = reactive({
    outlink_display: false,
    outlink_event: null as OutlinkSelectorOpenEvent,
    instance_display: false,
    instance_event: null as InstanceSelectorOpenEvent,
    loading: false,
    query_string: ''
})

const overviewBox = new OverviewCircles('#threed_graph')

const clicked_outlink = (evt: OutlinkSelectorOpenEvent) => {
    ui_state.outlink_display = true
    ui_state.outlink_event = evt
}
const clicked_instance = (evt: InstanceSelectorOpenEvent) => {
    ui_state.instance_display = true
    ui_state.instance_event = evt
}
const root_subject = ref(null as SubjectNode | null)
watch(() => store, () => {
    // console.log('Store changed!', store)
    if (!store) {
        return
    }
    let query_string = store.generateQuery()
    // console.log('Query string', query_string)
    if (query_string != ui_state.query_string) {
        ui_state.query_string = query_string
    }
}, { deep: true })
watch(() => ui_state.query_string, (new_val) => {
    if (overviewBox.nodes.length == 0 && overviewBox.renderer) {
        return
    }
    overviewBox.updateLinks(store)
}, { deep: false })

onMounted(() => {
    // circleman.clicked_node = (node: NodeType) => {
    //     console.log('clicked_node', node)
    //     api.classes.getLinksClassesLinksGet({
    //         subject_id: node.subject_id
    //     }).then(resp => {
    //         console.log('resp', resp)
    //         circleman.removeLinks()
    //         const links = resp.data
    //         for (const out of links.targets) {
    //             circleman.addLink(links.source.subject_id, out.target.subject_id, out.count)
    //         }
    //     }).catch(console.error)
    // }
    (async () => {
        ui_state.loading = true
        const resp_classes = await api.classes.getFullClassesClassesFullGet()
        ui_state.loading = false
        overviewBox.nodes = resp_classes.data as SubjectInCircle[]
        overviewBox.initPackedCircles()
        if (store && store.nodes.length > 0) {
            overviewBox.updateLinks(store)
        }
    })().catch((e) => {
        console.error(e)
        ui_state.loading = false
    })

    // .style('background-color', 'red')
})
const preview_link = (l: Link | null) => {
    // console.log('Preview link', l)
    if(l){
        overviewBox.previewLink(l)
    } else {
        overviewBox.hidePreview()
    }
}
</script>
<style lang="scss" scoped>
.query_builder {
    width: 80%;
    height: 95%;
}

.query_build_wrapper {
    width: 100%;
    height: 100%;
}

.node {
    cursor: pointer;
    fill: #ccc;
    stroke: #000;
    stroke-width: 1.5px;

}

.node_text {
    font-size: 10px;
    text-anchor: middle;
}


#threed_graph {
    width: 100%;
    height: 100%;
}

#threed_minimap {
    aspect-ratio: 1;
    height: 20vw;
    width: 20vw;
    position: relative;
    left: calc(100% - 20vw - 20px);
    bottom: calc(5vw + 20px);
    // translate: calc(100%) calc(80%);
    z-index: 20;
    background-color: #ffffff;
    border: 1px solid #8fa88f;
    padding: 4px;
    margin: 5px;
}
</style>