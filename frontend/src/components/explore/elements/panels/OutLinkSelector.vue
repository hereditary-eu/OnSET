<template>
    <g id="outlink_selector" @mouseout.capture="edit_point_hover($event, false)"
        @mouseenter.capture="edit_point_hover($event, true)" @mouseover="edit_point_hover($event, true)">
        <g :transform="`translate(${attachment_pt.x},${attachment_pt.y})`" v-if="display">
            <foreignObject :height="(NODE_HEIGHT) * 8 + 10" :width="NODE_WIDTH + LINK_WIDTH + 35">
                <div class="selection_div_container" :style="{ 'height': `${NODE_HEIGHT * 8 + 10}px` }">
                    <div class="selection_defaults" v-if="selection_event.side == NodeSide.PROP">
                        <OnsetBtn @click="addLabelConstraint()" btn_width="100%">Filter Label</OnsetBtn>
                        <OnsetBtn @click="addInstanceConstraint()" btn_width="100%">Select Instance</OnsetBtn>
                    </div>
                    <div class="selection_search">
                        <input type="text" placeholder="Search..." v-model="editor_data.q" />
                    </div>
                    <div class="selection_element_container">
                        <div class="selection_element_wrapper" v-for="option of selected_options_filtered">
                            <div class="selection_element" @click="select_option(option, $event)" @mouseenter.capture="editor_data.hover_add =
                                option" @mousemove.capture="editor_data.hover_add = option"
                                @mouseleave.capture="editor_data.hover_add = null"
                                :key="option.link?.property_id || option.subject?.subject_id">
                                <svg :width="editor_data.select_width" :height="NODE_HEIGHT + 15">
                                    <g @click="">
                                        <GraphView :store="option.store" :display-mode="DisplayMode.SELECT"></GraphView>
                                    </g>
                                </svg>

                            </div>
                            <div v-if="selection_event.side == NodeSide.PROP">
                                <OnsetBtn :btn_width="'1.5rem'" :toggleable="false"
                                    @click="select_prop(option, $event)">
                                    <v-icon icon="mdi-tag"></v-icon>
                                </OnsetBtn>
                            </div>
                        </div>
                        <Loading v-if="editor_data.loading"></Loading>
                        <OnsetBtn @click="loadMore" btn_width="100%"
                            v-if="selection_options.length > 0 && !editor_data.reached_end" :toggleable="false">More
                        </OnsetBtn>
                    </div>
                </div>
            </foreignObject>

            <g v-show="editor_data.show_editpoints">
                <circle :cx="NODE_WIDTH + LINK_WIDTH + 35" :cy="0" :r="editor_data.editpoint_r"
                    class="edit_point edit_point_delete" @click="display = false"></circle>
            </g>
        </g>
    </g>
</template>
<script setup lang="ts">
import { ref, watch, reactive, computed, onMounted } from 'vue'
import { SubQuery, Link, SubjectNode, StringConstraint, SubjectConstraint, QueryProp } from '@/utils/sparql/representation';
import LinkComp from '../Link.vue';
import NodeComp from '../Node.vue';
import { BACKEND_URL } from '@/utils/config';
import { Api, RELATION_TYPE, RETURN_TYPE } from '@/api/client.ts/Api';
import { DisplayMode, LINK_WIDTH, NODE_HEIGHT, NODE_WIDTH, NodeSide, OutlinkSelectorOpenEvent } from '@/utils/sparql/helpers';
import Loading from '@/components/ui/Loading.vue';
import OnsetBtn from '@/components/ui/OnsetBtn.vue';
import { MixedResponse, type NodeLinkRepository } from '@/utils/sparql/store';
import GraphView from '../GraphView.vue';
import { jsonClone } from '@/utils/parsing';

const emit = defineEmits<{
    select: [value: MixedResponse],
    hover_option: [value: Link | null]
}>()
const api = new Api({
    baseURL: BACKEND_URL

})
const { selection_event, store } = defineProps({
    selection_event: {
        type: Object as () => OutlinkSelectorOpenEvent,
        required: true
    },
    store: {
        type: Object as () => NodeLinkRepository,
        required: true
    }
})

const editor_data = reactive({
    show_editpoints: false,
    editpoint_r: 7,
    loading: false,
    q: '',
    query_id: 0,
    offset: 0,
    reached_end: false,
    hover_add: null as MixedResponse<SubjectNode> | null,
    select_width: LINK_WIDTH + NODE_WIDTH

})
const display = defineModel<boolean>()
const selection_options = ref([] as MixedResponse<SubjectNode>[])
const update_selection_options = async () => {
    console.log('Node changed!', selection_event, display)
    if (display) {
        (async () => {
            selection_options.value = []
            editor_data.offset = 0
            console.log('fetching selection options', selection_event, 'offset', editor_data.offset)
            switch (selection_event.side) {
                case NodeSide.PROP:
                    editor_data.select_width = NODE_WIDTH
                    break
                default:
                    editor_data.select_width = LINK_WIDTH + NODE_WIDTH
                    break
            }
            await loadMore()
        })().catch((e) => {
            console.error('Error fetching selection options', e)
            editor_data.loading = false
        })
    } else {
        selection_options.value = []
    }
}
// watch(() => display, update_selection_options, { deep: false })
watch(() => selection_event, () => {
    editor_data.q = ''
    update_selection_options()

}, { deep: false })
watch(() => editor_data.q, update_selection_options, { deep: false })

const loadMore = async () => {
    editor_data.loading = true
    let query_id = ++editor_data.query_id
    const response = await api.classes.searchClassesClassesSearchPost({
        q: editor_data.q,
        from_id: selection_event.side == NodeSide.TO || selection_event.side == NodeSide.PROP ? selection_event.node.subject_id : undefined,
        to_id: selection_event.side == NodeSide.FROM ? selection_event.node.subject_id : undefined,
        type: RETURN_TYPE.Link,
        limit: 10,
        skip: editor_data.offset,
        relation_type: selection_event.side == NodeSide.PROP ? RELATION_TYPE.Property : RELATION_TYPE.Instance
    })
    if (query_id != editor_data.query_id) {
        return
    }
    editor_data.offset += response.data.results.length
    //TODO: topic ids - user context!
    let mapped_responses = response.data.results.map((result) => {
        const resp = new MixedResponse<SubjectNode>(result)
        const other_subject = selection_event.side == NodeSide.FROM || selection_event.side == NodeSide.PROP ? resp.store.to(resp.link) : resp.store.from(resp.link)
        let from = resp.store.from(resp.link)
        let to = resp.store.to(resp.link)
        if (selection_event.side == NodeSide.TO) {
            to.x = LINK_WIDTH
            from.x = -NODE_WIDTH
        } else if (selection_event.side == NodeSide.PROP) {
            to.x = NODE_WIDTH
            from.x = -from.width
        } else {
            to.x = LINK_WIDTH + NODE_WIDTH
        }
        return resp
    })
    if (mapped_responses.length == 0) {
        editor_data.reached_end = true
    }
    selection_options.value = selection_options.value.concat(mapped_responses)
    editor_data.loading = false
}
const attachment_pt = computed(() => {
    if (!selection_event) {
        return { x: 0, y: 0 }
    }
    switch (selection_event.side) {
        case NodeSide.TO:
            return { x: selection_event.node.x + selection_event.node.width, y: selection_event.node.y + selection_event.node.height / 2 }
        case NodeSide.FROM:
            return { x: selection_event.node.x - (NODE_WIDTH + LINK_WIDTH + 20), y: selection_event.node.y + selection_event.node.height / 2 }
        case NodeSide.PROP:
            return { x: selection_event.node.x + selection_event.node.width / 2, y: selection_event.node.y + selection_event.node.height }
    }
})
const prepareTarget = (link: Link<SubjectNode>) => {
    let target = selection_event.side == NodeSide.TO ? link.to_subject : link.from_subject
    if (selection_event.side == NodeSide.TO) {
        target.x = selection_event.node.x + selection_event.node.width + LINK_WIDTH
    } else {
        target.x = selection_event.node.x - (target.width + LINK_WIDTH)
    }
    target.y = selection_event.node.y
    return target
}
const select_option = (selected_option: MixedResponse<SubjectNode>, event: MouseEvent) => {
    display.value = false
    switch (selection_event.side) {
        case NodeSide.TO:
        case NodeSide.FROM:
            let target = prepareTarget(selected_option.link)
            store.addOutlink(selected_option.link, selection_event.node, target, selection_event.side)
            break
        case NodeSide.PROP:
            selected_option.link.from_internal_id = selection_event.node.internal_id
            let constraint = SubQuery.construct(selected_option.link)
            if (!selection_event.node.subqueries) {
                selection_event.node.subqueries = []
            }
            // if (!selection_event.node.property_constraints[selected_option.link.property_id]) {
            //     selection_event.node.property_constraints[selected_option.link.property_id] = []
            // }
            selection_event.node.subqueries.push(constraint)
            //TODO: property constraints
            // selection_event.node.property_constraints.push(option.link)
            break
    }
    emit('select', selected_option)
}
const select_prop = (option: MixedResponse<SubjectNode>, event: MouseEvent) => {
    display.value = false
    option.link.from_internal_id = selection_event.node.internal_id
    let query_prop = QueryProp.construct(option.link)
    if (selection_event.node.subqueries) {
        selection_event.node.subqueries.push(query_prop)
    } else {
        selection_event.node.subqueries = [query_prop]
    }
}
const selected_options_filtered = computed(() => {
    if (selection_event.side == NodeSide.PROP) {
        return selection_options.value.filter((option) => {
            return SubQuery.construct(option.link) != null
        })
    }
    return selection_options.value
})

const edit_point_hover = (event: MouseEvent, state: boolean) => {
    editor_data.show_editpoints = state
}
const addLabelConstraint = () => {
    const link = new Link()
    link.from_id = selection_event.node.subject_id
    link.from_internal_id = selection_event.node.internal_id
    link.from_subject = selection_event.node
    link.property_id = 'rdfs:label'
    link.to_proptype = 'xsd:string'
    link.label = 'Label'
    const constraint = SubQuery.construct(link)
    if (!selection_event.node.subqueries) {
        selection_event.node.subqueries = []
    }
    selection_event.node.subqueries.push(constraint)
    display.value = false
}
const addInstanceConstraint = () => {
    const link = new Link()
    link.from_id = selection_event.node.subject_id
    link.from_internal_id = selection_event.node.internal_id
    link.from_subject = selection_event.node
    link.to_proptype = 'owl:Thing'

    const constraint = new SubjectConstraint()
    constraint.link = link
    if (!selection_event.node.subqueries) {
        selection_event.node.subqueries = []
    }
    selection_event.node.subqueries.push(constraint)
    display.value = false
}
watch(editor_data, (editor_data) => {
    if (selection_event.side != NodeSide.PROP) {
        if (editor_data.hover_add) {
            let hover_target = jsonClone(editor_data.hover_add)
            let target = prepareTarget(hover_target.link)
            let link = store.prepareLink(hover_target.link, selection_event.node, target, selection_event.side)
            emit('hover_option', link)
        }

    }
    if (!editor_data.hover_add) {
        emit('hover_option', null)
    }
}, { deep: true })
watch(display, (new_val) => {
    if (!new_val) {
        console.log('Clearing hover')
        editor_data.hover_add = null
    }
})
</script>
<style lang="scss">
.selection_search {
    padding: 5px;

    input {
        padding: 0 5px 0 5px;
        border: 1px solid rgb(197, 196, 168);
    }
}

.selection_div_container {
    display: flex;
    flex-direction: column;
    // justify-content: ;
    align-items: center;
    background-color: white;
    border: 1px solid rgb(197, 196, 168);
    // border-radius: 5px;
    padding: 5px;
}

.selection_element_container {
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    align-items: center;
    overflow-y: auto;
}

.selection_element_wrapper {
    padding: 2px;
    display: flex;
    flex-direction: row;
    justify-items: center;
    align-items: center;

    // width: v-bind("editor_data.select_width")px;
}

.selection_element {
    cursor: pointer;
    margin: 5px;

}

.selection_element:hover {
    background-color: #f0f0f0;
}

.selection_defaults {
    display: flex;
    justify-content: space-around;
    flex-direction: column;
    width: 100%;
    padding: 4px;
}

.edit_point {
    fill: #a0c2a9;
    cursor: pointer;
    fill-opacity: 0.4;
}

.edit_point:hover {
    stroke: #888888;
    display: block;
    fill-opacity: 1;
}

.edit_point_delete {
    fill: #ea694f;
}
</style>