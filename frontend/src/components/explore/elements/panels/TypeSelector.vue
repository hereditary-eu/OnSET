<template>
    <g id="type_selector" @mouseout.capture="edit_point_hover($event, false)"
        @mouseenter.capture="edit_point_hover($event, true)" @mouseover="edit_point_hover($event, true)">
        <g :transform="`translate(${attachment_pt.x},${attachment_pt.y})`" v-if="display">
            <foreignObject :height="(NODE_HEIGHT) * 8 + 10" :width="NODE_WIDTH + LINK_WIDTH + 35">
                <div class="selection_div_container" :style="{ 'height': `${NODE_HEIGHT * 8 + 10}px` }">

                    <div class="selection_defaults">
                        <OnsetBtn @click="resetToHighest()" :btn_width="`${NODE_WIDTH + 35}px`" :toggleable="false">
                            Generalize
                        </OnsetBtn>
                    </div>
                    <div class="selection_search">
                        <input type="text" placeholder="Search..." v-model="editor_data.q" />
                    </div>
                    <div class="selection_element_container">
                        <div class="selection_element_wrapper" v-for="option of selection_options">
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
import { DisplayMode, LINK_WIDTH, NODE_HEIGHT, NODE_WIDTH, OpenEventType, SelectorOpenEvent } from '@/utils/sparql/helpers';
import Loading from '@/components/ui/Loading.vue';
import OnsetBtn from '@/components/ui/OnsetBtn.vue';
import { MixedResponse, type NodeLinkRepository } from '@/utils/sparql/store';
import GraphView from '../GraphView.vue';
import { jsonClone } from '@/utils/parsing';
import { debounce } from '@/utils/helpers';
import { de } from 'vuetify/locale';

const emit = defineEmits<{
    select: [value: MixedResponse]
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
        editor_data.select_width = NODE_WIDTH
        await loadMore()
    })().catch((e) => {
        console.error('Error fetching selection options', e)
        editor_data.loading = false
    })
}, 300, true)
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
    console.log('Loading more', selection_event, editor_data.q, editor_data.offset)
    const response = await api.classes.getClassSearchClassesSubclassesSearchPost({
        q: editor_data.q,
        from_id: selection_event.node.subject_id,
        type: RETURN_TYPE.Subject,
        limit: 25,
        skip: editor_data.offset,
        relation_type: RELATION_TYPE.Instance
    })
    if (query_id != editor_data.query_id) {
        return
    }
    editor_data.offset += response.data.results.length
    //TODO: topic ids - user context!
    let mapped_responses = response.data.results.map((result) => {
        const resp = new MixedResponse<SubjectNode>(result)
        resp.store.nodes[0].x = 0
        resp.store.nodes[0].y = 0

        return resp
    })
    if (mapped_responses.length == 0) {
        editor_data.reached_end = true
    }
    selection_options.value = selection_options.value.concat(mapped_responses)
    editor_data.loading = false
}
const attachment_pt = computed(() => {
    return {
        x: selection_event.node.x + selection_event.node.width / 2, y: selection_event.node.y
    }
})
const prepareTarget = (link: Link<SubjectNode>) => {
    let target = selection_event.side == OpenEventType.TO ? link.to_subject : link.from_subject
    if (selection_event.side == OpenEventType.TO) {
        target.x = selection_event.node.x + selection_event.node.width + LINK_WIDTH
    } else {
        target.x = selection_event.node.x - (target.width + LINK_WIDTH)
    }
    target.y = selection_event.node.y
    return target
}
const select_option = (selected_option: MixedResponse<SubjectNode>, event: MouseEvent) => {
    display.value = false
    setClass(selected_option.store.nodes[0])
    emit('select', selected_option)
}
const setClass = (selected: SubjectNode) => {

    let nd = store.node(selection_event.node)
    nd.subject_id = selected.subject_id
    nd.label = selected.label
}
const edit_point_hover = (event: MouseEvent, state: boolean) => {
    editor_data.show_editpoints = state
}
const resetToHighest = async () => {
    try {
        let in_ids = store.toLinks(selection_event.node).map((link) => {
            return link.property_id
        })
        let out_ids = store.fromLinks(selection_event.node).map((link) => {
            return link.property_id
        })
        out_ids.push(...selection_event.node.subqueries.map((subq) => {
            return subq.link.property_id
        }))
        const response = await api.classes.getMostGenericsClassesParentsMostGenericPost({

            cls: selection_event.node.subject_id,
            in_link_ids: in_ids,
            out_link_ids: out_ids,

        })
        setClass(response.data as SubjectNode)

    } catch (error) {
        console.error('Error resetting to highest', error)

    }

}
watch(editor_data, (editor_data) => {
}, { deep: true })
watch(display, (new_val) => {
    editor_data.reached_end = false
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