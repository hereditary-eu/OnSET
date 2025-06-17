<template>
    <g id="outlink_selector" @mouseout.capture="editPointHover($event, false)"
        @mouseenter.capture="editPointHover($event, true)" @mouseover="editPointHover($event, true)">
        <g :transform="`translate(${attachment_pt.x},${attachment_pt.y})`" v-if="display">
            <foreignObject :height="(NODE_HEIGHT) * NODE_LINK_COUNT + 10" :width="NODE_WIDTH + LINK_WIDTH + 35">
                <div class="selection_div_container" :style="{ 'height': `${NODE_HEIGHT * NODE_LINK_COUNT + 10}px` }">
                    <div class="selection_defaults" v-if="selection_event.side == OpenEventType.PROP">
                        <OnsetBtn @click="addLabelConstraint()" btn_width="100%">Filter Label</OnsetBtn>
                        <OnsetBtn @click="addLabelProp()" btn_width="100%"><v-icon icon="mdi-tag"></v-icon> Label
                        </OnsetBtn>
                        <OnsetBtn @click="addInstanceConstraint()" btn_width="100%">Select Instance</OnsetBtn>
                    </div>
                    <div class="selection_defaults" v-if="selection_event.side == OpenEventType.LINK">
                        <OnsetBtn @click="toggleGeneric()" btn_width="100%">{{
                            selection_event.link.allow_arbitrary ? "Disable" : "Allow" }} Any</OnsetBtn>
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
                            <div v-if="selection_event.side == OpenEventType.PROP">
                                <OnsetBtn :btn_width="'1.5rem'" :toggleable="false" @click="selectProp(option, $event)">
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
                    class="edit_point edit_point_delete" @click="closePanel()"></circle>
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
import { DisplayMode, LINK_WIDTH, LinkEditEvent, NODE_HEIGHT, NODE_WIDTH, OpenEventType, SelectorOpenEvent } from '@/utils/sparql/helpers';
import Loading from '@/components/ui/Loading.vue';
import OnsetBtn from '@/components/ui/OnsetBtn.vue';
import { MixedResponse, type NodeLinkRepository } from '@/utils/sparql/store';
import GraphView from '../GraphView.vue';
import { jsonClone } from '@/utils/parsing';
import { debounce } from '@/utils/helpers';

const NODE_LINK_COUNT = 16
const emit = defineEmits<{
    // select: [value: MixedResponse],
    hover_option: [value: Link | null]
    finished: [value: LinkEditEvent]
}>()
const api = new Api({
    baseURL: BACKEND_URL

})
const { selection_event, store } = defineProps({
    selection_event: {
        type: Object as () => SelectorOpenEvent,
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
const debounced_search = debounce(() => {
    (async () => {
        selection_options.value = []
        editor_data.offset = 0
        editor_data.reached_end = false
        console.log('fetching selection options', selection_event, 'offset', editor_data.offset)
        if (!selection_event) {
            console.warn('No selection event provided, cannot fetch options')
            return;
        }
        switch (selection_event.side) {
            case OpenEventType.PROP:
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
}, 300, false)
const update_selection_options = async () => {
    console.log('Node changed!', selection_event, display)
    if (display) {
        debounced_search()
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
    let from_id = null
    let to_id = null
    if (selection_event.side == OpenEventType.PROP) {
        from_id = selection_event.node.subject_id
    } else if (selection_event.side == OpenEventType.LINK) {
        from_id = selection_event.link.from_id
        to_id = selection_event.link.to_id
    } else if (selection_event.side == OpenEventType.TO) {
        from_id = selection_event.link.from_id
    } else if (selection_event.side == OpenEventType.FROM) {
        to_id = selection_event.link.to_id
    }
    const response = await api.classes.searchClassesClassesSearchPost({
        q: editor_data.q,
        from_id: from_id,
        to_id: to_id,
        type: RETURN_TYPE.Link,
        limit: 10,
        skip: editor_data.offset,
        relation_type: selection_event.side == OpenEventType.PROP ? RELATION_TYPE.Property : RELATION_TYPE.Instance
    })
    if (query_id != editor_data.query_id) {
        return
    }
    editor_data.offset += response.data.results.length
    //TODO: topic ids - user context!
    let mapped_responses = response.data.results.map((result) => {
        const resp = new MixedResponse<SubjectNode>(result)
        const other_subject = selection_event.side == OpenEventType.FROM || selection_event.side == OpenEventType.PROP ? resp.store.to(resp.link) : resp.store.from(resp.link)
        let from = resp.store.from(resp.link)
        let to = resp.store.to(resp.link)
        if (selection_event.side == OpenEventType.TO) {
            to.x = LINK_WIDTH
            from.x = -NODE_WIDTH
        } else if (selection_event.side == OpenEventType.PROP) {
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
        case OpenEventType.PROP:
            return { x: selection_event.node.x + selection_event.node.width / 2, y: selection_event.node.y + selection_event.node.height }
        case OpenEventType.TO:
        case OpenEventType.FROM:
        case OpenEventType.LINK:
            let attach_pt = store.textAttachPoint(selection_event.link)
            return {
                x: attach_pt.x,
                y: attach_pt.y + 10
            }
    }
})
const prepareTarget = (link: Link<SubjectNode>) => {
    let target = selection_event.side == OpenEventType.TO ? link.to_subject : link.from_subject
    if (!target) {
        target = new SubjectNode()
        target.internal_id = selection_event.side == OpenEventType.TO ? link.to_internal_id : link.from_internal_id
        target.subject_id = selection_event.side == OpenEventType.TO ? link.to_id : link.from_id
        target.label = selection_event.side == OpenEventType.TO ? link.to_id : link.from_id
    }
    if (selection_event.side == OpenEventType.TO) {
        target.x = selection_event.node ? selection_event.node.x + selection_event.node.width + LINK_WIDTH : 0
    } else {
        target.x = selection_event.node ? selection_event.node.x - (target.width + LINK_WIDTH) : 0
    }
    target.y = selection_event.node ? selection_event.node.y : 0
    return target
}
const select_option = (selected_option: MixedResponse<SubjectNode>, event: MouseEvent) => {
    display.value = false
    console.log('Selected option', selected_option, selection_event)
    switch (selection_event.side) {
        case OpenEventType.TO:
        case OpenEventType.FROM:
            let node_id_new = selection_event.side == OpenEventType.TO ? selection_event.link.to_internal_id : selection_event.link.from_internal_id
            let node_new = store.nodes.find((n) => n.internal_id == node_id_new)
            if (node_new) {
                let target = selection_event.side == OpenEventType.TO ? selected_option.store.to(selected_option.link) : selected_option.store.from(selected_option.link)
                node_new.subject_id = target.subject_id
                node_new.label = target.label
            } else {
                console.warn('Node not found for link selection', node_id_new, store.nodes)
            }
        case OpenEventType.LINK:
            let link = store.links.find((l) => selection_event.link.id == l.id)

            if (link) {
                if (selection_event.side == OpenEventType.FROM) {
                    link.from_id = selected_option.link.from_id
                } else {
                    link.to_id = selected_option.link.to_id
                }
                link.label = selected_option.link.label
                link.link_type = selected_option.link.link_type
                link.property_id = selected_option.link.property_id
                link.instance_count = selected_option.link.instance_count
                link.initialized = true
            }
            console.log('Link configured', link, selection_event, selected_option)
            break
        case OpenEventType.PROP:
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
    emit('finished', {
        success: true,
        link: selected_option.link,
        node: selection_event.node,
        side: selection_event.side
    })
}
const addLabelProp = () => {
    const link = new Link()
    link.from_id = selection_event.node.subject_id
    link.from_internal_id = selection_event.node.internal_id
    link.from_subject = selection_event.node
    link.property_id = 'rdfs:label'
    link.to_proptype = 'xsd:string'
    link.label = selection_event.node.label
    const constraint = QueryProp.construct(link)
    if (!selection_event.node.subqueries) {
        selection_event.node.subqueries = []
    }
    selection_event.node.subqueries.push(constraint)
    display.value = false
}
const selectProp = (option: MixedResponse<SubjectNode>, event: MouseEvent) => {
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
    if (selection_event.side == OpenEventType.PROP) {
        return selection_options.value.filter((option) => {
            return SubQuery.construct(option.link) != null
        })
    }
    return selection_options.value
})

const editPointHover = (event: MouseEvent, state: boolean) => {
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
const toggleGeneric = () => {
    selection_event.link.allow_arbitrary = !selection_event.link.allow_arbitrary
    display.value = false
}
const closePanel = () => {
    display.value = false
    let success = selection_event.side == OpenEventType.PROP || selection_event.side == OpenEventType.LINK
    if (selection_event.side == OpenEventType.LINK) {

        let link = store.links.find((l) => selection_event.link.id == l.id)
        success = link.initialized
    }
    console.log('Closing panel', selection_event, success)
    emit('finished', {
        success: success,
        link: selection_event.link,
        node: selection_event.node,
        side: selection_event.side
    })
}

watch(editor_data, (editor_data) => {
    if (selection_event && selection_event.side != OpenEventType.PROP) {
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
    editor_data.reached_end = false
    if (!new_val) {
        console.log('Clearing hover')
        editor_data.hover_add = null
    }
})
</script>
<style lang="scss" scoped>
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
    justify-content: center;
    flex-direction: row;
    flex-wrap: wrap;
    width: 100%;
    padding: 3px;
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