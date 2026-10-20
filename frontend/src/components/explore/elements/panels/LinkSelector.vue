<template>
    <g id="outlink_selector" @mouseout.capture="editPointHover($event, false)"
        @mouseenter.capture="editPointHover($event, true)" @mouseover="editPointHover($event, true)">
        <g :transform="`translate(${attachment_pt.x},${attachment_pt.y})`" v-if="display">
            <foreignObject :height="PANEL_HEIGHT" :width="panel_width">
                <div class="selection_div_container">
                    <div class="selection_defaults" v-if="selection_event.side == OpenEventType.PROP">
                        <OnsetBtn size="small" :toggleable="false" @click="addLabelConstraint()">Filter Label</OnsetBtn>
                        <OnsetBtn size="small" :toggleable="false" icon="mdi-tag" @click="addLabelProp()">Label</OnsetBtn>
                        <OnsetBtn size="small" :toggleable="false" @click="addInstanceConstraint()">Select Instance
                        </OnsetBtn>
                    </div>
                    <div class="selection_defaults" v-if="selection_event.side == OpenEventType.LINK">
                        <OnsetBtn size="small" :toggleable="false" @click="toggleGeneric()">{{
                            selection_event.link.allow_arbitrary ? "Disable" : "Allow" }} Any</OnsetBtn>
                    </div>
                    <input type="text" class="text_input selection_search" placeholder="Search..."
                        v-model="editor_data.q" />
                    <div class="selection_element_container">
                        <div class="selection_element_wrapper" v-for="subq of selected_options_filtered"
                            :key="subq.option.link?.property_id || subq.option.subject?.subject_id">
                            <div :class="sel_clses(subq)" @click="select_option(subq, $event)"
                                @mouseenter.capture="editor_data.hover_add = subq.option"
                                @mousemove.capture="editor_data.hover_add = subq.option"
                                @mouseleave.capture="editor_data.hover_add = null">
                                <svg :width="option_width(subq.option)" :height="NODE_HEIGHT + 12">
                                    <g transform="translate(0, 10)">
                                        <GraphView :store="subq.option.store" :display-mode="DisplayMode.SELECT">
                                        </GraphView>
                                    </g>
                                </svg>
                            </div>
                            <OnsetBtn v-if="selection_event.side == OpenEventType.PROP" size="small"
                                :toggleable="false" icon="mdi-tag" title="Show as property"
                                @click="selectProp(subq.option, $event)" :active="subq.validProp" />
                        </div>
                        <Loading v-if="editor_data.loading"></Loading>
                        <OnsetBtn size="small" @click="loadMore"
                            v-if="selection_options.length > 0 && !editor_data.reached_end" :toggleable="false">More
                        </OnsetBtn>
                    </div>
                </div>
            </foreignObject>

            <circle v-show="editor_data.show_editpoints" :cx="panel_width" :cy="0" :r="EDITPOINT_R"
                class="edit_point edit_point_delete" @click="closePanel()" />
        </g>
    </g>
</template>
<script setup lang="ts">
import { ref, watch, reactive, computed } from 'vue'
import { SubQuery, Link, SubjectNode, SubjectConstraint, QueryProp } from '@/utils/sparql/representation';
import { RELATION_TYPE, RETURN_TYPE } from '@/api/client.ts/Api';
import { DisplayMode, EDITPOINT_R, fitNode, LINK_WIDTH, LinkEditEvent, linkWidth, NODE_HEIGHT, OpenEventType, PANEL_WIDTH, SelectorOpenEvent } from '@/utils/sparql/helpers';
import Loading from '@/components/ui/Loading.vue';
import OnsetBtn from '@/components/ui/OnsetBtn.vue';
import { MixedResponse, type NodeLinkRepository } from '@/utils/sparql/store';
import GraphView from '../GraphView.vue';
import { jsonClone } from '@/utils/parsing';
import { debounce } from '@/utils/helpers';
import { api } from '@/utils/api'

class MappedSelection {
    constructor(public option: MixedResponse<SubjectNode>, public validProp: boolean = true, public validFilter: boolean = true) { }
}

// panel height: room for about 12 options
const PANEL_HEIGHT = (NODE_HEIGHT + 14) * 12
const emit = defineEmits<{
    // select: [value: MixedResponse],
    hover_option: [value: Link | null]
    finished: [value: LinkEditEvent]
}>()
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
    loading: false,
    q: '',
    query_id: 0,
    offset: 0,
    reached_end: false,
    hover_add: null as MixedResponse<SubjectNode> | null,
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
        let from = fitNode(resp.store.from(resp.link))
        let to = fitNode(resp.store.to(resp.link))
        // only the link and the new end are visible: the known end is shifted out of view
        const link_w = linkWidth(resp.link.label)
        if (selection_event.side == OpenEventType.TO) {
            from.x = -from.width
            to.x = link_w
        } else if (selection_event.side == OpenEventType.PROP) {
            from.x = -from.width
            to.x = link_w
        } else {
            from.x = 0
            to.x = from.width + link_w
        }
        return resp
    })
    if (mapped_responses.length == 0) {
        editor_data.reached_end = true
    }
    selection_options.value = selection_options.value.concat(mapped_responses)
    editor_data.loading = false
}
// visible width of an option preview (see the placement in loadMore)
const option_width = (option: MixedResponse<SubjectNode>) => {
    const link_w = linkWidth(option.link?.label)
    switch (selection_event.side) {
        case OpenEventType.TO:
            return link_w + (option.store.to(option.link)?.width ?? 0)
        case OpenEventType.PROP:
            return link_w
        default:
            return (option.store.from(option.link)?.width ?? 0) + link_w
    }
}
const panel_width = computed(() => {
    const widest = selection_options.value.reduce((acc, option) => Math.max(acc, option_width(option)), 0)
    const extra = selection_event.side == OpenEventType.PROP ? 32 : 12
    return Math.min(2 * PANEL_WIDTH, Math.max(PANEL_WIDTH, widest + extra))
})
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
const select_option = (sub_selection: MappedSelection, event: MouseEvent) => {
    if (!sub_selection.option.link || !sub_selection.validFilter) {
        console.warn('No link in selected option / not a valid filter', sub_selection)
        return
    }
    display.value = false
    const selected_option = sub_selection.option
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
            let constraint = SubQuery.constructFilter(selected_option.link)
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
    const constraint = QueryProp.constructProp(link)
    if (!selection_event.node.subqueries) {
        selection_event.node.subqueries = []
    }
    selection_event.node.subqueries.push(constraint)
    display.value = false
}
const selectProp = (option: MixedResponse<SubjectNode>, event: MouseEvent) => {
    display.value = false
    option.link.from_internal_id = selection_event.node.internal_id
    console.log('Adding property constraint', option.link, selection_event.node)
    let query_prop = QueryProp.constructProp(option.link)
    if (selection_event.node.subqueries) {
        selection_event.node.subqueries.push(query_prop)
    } else {
        selection_event.node.subqueries = [query_prop]
    }
}
const selected_options_filtered = computed(() => {
    if (selection_event.side == OpenEventType.PROP) {
        return selection_options.value.map((option) => {
            const validProp = QueryProp.validProp(option.link.to_proptype)
            const validFilter = SubQuery.validFilter(option.link.to_proptype)
            return new MappedSelection(option, validProp, validFilter)
        }).filter((entry) => entry.validProp || entry.validFilter)
    }
    return selection_options.value.map((option) => {
        return new MappedSelection(option)
    })
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
    const constraint = SubQuery.constructFilter(link)
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
const sel_clses = (sub_selection: MappedSelection) => {
    return {
        'selection_element': true,
        'selection_element_valid': sub_selection.validFilter,
        'selection_element_invalid': !sub_selection.validFilter
    }
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
