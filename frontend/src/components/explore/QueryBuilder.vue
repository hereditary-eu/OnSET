<template>
    <div class="query_builder">
        <svg class="query_build_wrapper">
            <GraphView :store="store" :display-mode="DisplayMode.EDIT" :diff="diff"
                @link-point-clicked="clickedOutlink($event)" @instance-search-clicked="clickedInstance($event)"
                @type-point-clicked="clickedType($event)" @link-edit-clicked="clickedEditLink($event)"></GraphView>
            <LinkComposer :store="store" :evt="ui_state.attaching_event" @selection-complete="linkEditDone($event)">
            </LinkComposer>
            <OutLinkSelector :selection_event="ui_state.sublink_event" v-model="ui_state.sublink_display" :store="store"
                @hover_option="previewLink($event)" @finished="linkSelectDone($event)">
            </OutLinkSelector>
            <InstanceSelector :selection_event="ui_state.instance_event" v-model="ui_state.instance_display">
            </InstanceSelector>
            <TypeSelector :selection_event="ui_state.type_event" v-model="ui_state.type_display" :store="store">
            </TypeSelector>
            <use xlink:href="#outlink_selector"></use>
            <use xlink:href="#instance_selector"></use>
            <use xlink:href="#type_selector"></use>
        </svg>
        <div id="threed_minimap">
            <Loading v-if="ui_state.loading"></Loading>
            <div id="threed_graph"></div>
        </div>
    </div>
</template>
<script setup lang="ts">
import { ref, watch, reactive, computed, onMounted, defineProps, onBeforeMount } from 'vue'
import { SubjectNode, Link } from '@/utils/sparql/representation';
import NodeComp from './elements/Node.vue';
import OutLinkSelector from './elements/panels/LinkSelector.vue';
import { DisplayMode, InstanceSelectorOpenEvent, LinkEditEvent, OpenEventType, type SelectorOpenEvent } from '@/utils/sparql/helpers';
import InstanceSelector from './elements/panels/InstanceSelector.vue';
import type { MixedResponse, NodeLinkRepository } from '@/utils/sparql/store';
import GraphView from './elements/GraphView.vue';
import { OverviewCircles } from '@/utils/three-man/OverviewCircles';
import { fa } from 'vuetify/locale';
import { Api } from '@/api/client.ts/Api';
import { BACKEND_URL } from '@/utils/config';
// import type { SubjectInCircle } from '@/utils/d3-man/CircleMan';
import Loading from '../ui/Loading.vue';
import type { NodeLinkRepositoryDiff } from '@/utils/sparql/diff';
import TypeSelector from './elements/panels/TypeSelector.vue';
import type { PropertiesOpenEvent } from '@/utils/sparql/querymapper';
import LinkComposer from './elements/LinkComposer.vue';
import type { SubjectInCircle } from '@/utils/three-man/CircleMan3D';

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
enum EditorMode {
    EDIT = 'edit',
    CREATE_LINK = 'create_link',
}
const ui_state = reactive({
    sublink_display: false,
    sublink_event: null as SelectorOpenEvent,
    attaching_display: false,
    attaching_event: null as SelectorOpenEvent,
    instance_display: false,
    instance_event: null as InstanceSelectorOpenEvent,
    type_display: false,
    type_event: null as SelectorOpenEvent,
    loading: false,
    query_string: '',
    editor_mode: EditorMode.EDIT,
})

const overviewBox = new OverviewCircles('#threed_graph')

const clickedOutlink = (evt: SelectorOpenEvent) => {
    if (evt.side == OpenEventType.PROP) {
        ui_state.sublink_display = true
        ui_state.sublink_event = evt

        ui_state.attaching_display = false
        ui_state.attaching_event = null
    } else {
        ui_state.editor_mode = EditorMode.CREATE_LINK
        ui_state.attaching_display = true
        ui_state.attaching_event = evt

        ui_state.sublink_display = false
        ui_state.sublink_event = null
    }
}
const clickedEditLink = (evt: SelectorOpenEvent) => {
    console.log('clickedEditLink', evt)
    ui_state.editor_mode = EditorMode.EDIT
    ui_state.sublink_display = true
    ui_state.sublink_event = evt
}
const clickedInstance = (evt: InstanceSelectorOpenEvent) => {
    ui_state.instance_display = true
    ui_state.instance_event = evt
}
const clickedType = (evt: SelectorOpenEvent) => {
    ui_state.type_display = true
    ui_state.type_event = evt
}
const linkEditDone = (evt: SelectorOpenEvent) => {
    ui_state.sublink_display = true
    ui_state.sublink_event = evt
}

const linkSelectDone = (evt: LinkEditEvent) => {
    ui_state.sublink_display = false
    ui_state.sublink_event = null
    ui_state.attaching_display = false
    ui_state.attaching_event = null
    if (evt.success) {
        ui_state.editor_mode = EditorMode.EDIT
        regenerateQuery()
    } else {
        store.removeLink(evt.link)
        if (evt.side != OpenEventType.LINK) {
            store.removeNode(evt.node)
        }
    }
}

const regenerateQuery = () => {
    // console.log('Store changed!', store)
    if (!store) {
        return
    }
    let query_string = store.generateQuery()
    // console.log('Query string', query_string)
    if (query_string != ui_state.query_string) {
        ui_state.query_string = query_string
    }
}

watch(() => ui_state.editor_mode, (new_val) => {
    if (ui_state.editor_mode == EditorMode.EDIT) {
        regenerateQuery()
    }
}, { deep: true })
watch(() => store, () => {
    regenerateQuery()
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
        // overviewBox.dimensions.width = 1000
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


const previewLink = (l: Link | null) => {
    // console.log('Preview link', l)
    if (l) {
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
    height: 10vw;
    width: 10vw;
    position: relative;
    left: calc(100% - 10vw - 20px);
    bottom: calc(10vw + 20px);
    // translate: calc(100%) calc(80%);
    z-index: 20;
    background-color: #ffffff;
    border: 1px solid #8fa88f;
    padding: 4px;
    margin: 5px;
}
</style>