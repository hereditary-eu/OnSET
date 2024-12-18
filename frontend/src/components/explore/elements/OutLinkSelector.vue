<template>
    <g id="outlink_selector" @mouseout.capture="edit_point_hover($event, false)"
        @mouseenter.capture="edit_point_hover($event, true)" @mouseover="edit_point_hover($event, true)">
        <g :transform="`translate(${attachment_pt.x},${attachment_pt.y})`" v-if="display">
            <foreignObject :height="(NODE_HEIGHT + 10) * 5" :width="NODE_WIDTH + LINK_WIDTH + 35">
                <div class="selection_div_container" :style="{ 'height': `${NODE_HEIGHT * 5 + 10}px` }">
                    <div class="selection_search">
                        <input type="text" placeholder="Search..." v-model="editor_data.q" />
                    </div>
                    <Loading v-if="editor_data.loading"></Loading>
                    <div class="selection_element_container">
                        <div class="selection_element" v-for="option of selected_options_filtered"
                            @click="select_option(option, $event)"
                            :key="option.link?.property_id || option.subject?.subject_id">
                            <svg :width="NODE_WIDTH + LINK_WIDTH" :height="NODE_HEIGHT + 15">
                                <g @click="">
                                    <LinkComp :link="option.link"></LinkComp>
                                    <NodeComp :subject="option.link.from_subject" :editable="false"
                                        v-if="selection_event.side == NodeSide.FROM || selection_event.side == NodeSide.PROP">
                                    </NodeComp>
                                    <NodeComp :subject="option.link.to_subject" :editable="false"
                                        v-if="selection_event.side == NodeSide.TO"> </NodeComp>
                                </g>
                            </svg>
                        </div>
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
import { Constraint, MixedResponse } from '@/utils/sparql/representation';
import LinkComp from './Link.vue';
import NodeComp from './Node.vue';
import { BACKEND_URL } from '@/utils/config';
import { Api, RELATION_TYPE, RETURN_TYPE } from '@/api/client.ts/Api';
import { LINK_WIDTH, NODE_HEIGHT, NODE_WIDTH, NodeSide, OutlinkSelectorOpenEvent } from '@/utils/sparql/explorer';
import Loading from '@/components/ui/Loading.vue';

const emit = defineEmits<{
    select: [value: MixedResponse]
}>()
const api = new Api({
    baseURL: BACKEND_URL
    
})
const { selection_event } = defineProps({
    selection_event: {
        type: Object as () => OutlinkSelectorOpenEvent,
        required: true
    }
})

const editor_data = reactive({
    show_editpoints: false,
    editpoint_r: 7,
    loading: false,
    q: '',
    query_id: 0
})
const display = defineModel<boolean>()
const selection_options = ref([] as MixedResponse[])
const update_selection_options = async () => {
    console.log('Node changed!', selection_event, display)
    if (display) {
        (async () => {
            selection_options.value = []
            editor_data.loading = true
            let query_id = ++editor_data.query_id
            const response = await api.classes.searchClassesClassesSearchPost({
                q: editor_data.q,
                from_id: selection_event.side == NodeSide.TO || selection_event.side == NodeSide.PROP ? selection_event.node.subject_id : undefined,
                to_id: selection_event.side == NodeSide.FROM ? selection_event.node.subject_id : undefined,
                type: RETURN_TYPE.Link,
                limit: 10,
                relation_type: selection_event.side == NodeSide.PROP ? RELATION_TYPE.Property : RELATION_TYPE.Instance

            })
            if (query_id != editor_data.query_id) {
                return
            }
            editor_data.loading = false
            //TODO: topic ids - user context!
            selection_options.value = response.data.results.map((result) => {
                const resp = new MixedResponse(result)
                const other_subject = selection_event.side == NodeSide.FROM || selection_event.side == NodeSide.PROP ? resp.link.to_subject : resp.link.from_subject

                if (selection_event.side == NodeSide.TO) {
                    resp.link.to_subject.x = LINK_WIDTH
                    resp.link.from_subject.x = -NODE_WIDTH
                } else if (selection_event.side == NodeSide.PROP) {
                    resp.link.to_subject.x = LINK_WIDTH * 2
                    resp.link.from_subject.x = -NODE_WIDTH
                } else {
                    resp.link.to_subject.x = LINK_WIDTH + NODE_WIDTH
                }
                return resp
            })
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

const select_option = (selected_option: MixedResponse, event: MouseEvent) => {
    display.value = false

    switch (selection_event.side) {
        case NodeSide.TO:
            selected_option.link.from_subject = selection_event.node
            selected_option.link.to_subject.x = selection_event.node.x + selection_event.node.width + LINK_WIDTH
            selection_event.node.to_links.push(selected_option.link)
            break
        case NodeSide.FROM:
            selected_option.link.to_subject = selection_event.node
            selected_option.link.from_subject.x = selection_event.node.x - (NODE_WIDTH + LINK_WIDTH)
            selection_event.node.from_links.push(selected_option.link)
            break
        case NodeSide.PROP:
            let constraint = Constraint.construct(selected_option.link)
            if (!selection_event.node.property_constraints) {
                selection_event.node.property_constraints = []
            }
            // if (!selection_event.node.property_constraints[selected_option.link.property_id]) {
            //     selection_event.node.property_constraints[selected_option.link.property_id] = []
            // }
            selection_event.node.property_constraints.push(constraint)
            //TODO: property constraints
            // selection_event.node.property_constraints.push(option.link)
            break
    }
    emit('select', selected_option)
}
const selected_options_filtered = computed(() => {
    if (selection_event.side == NodeSide.PROP) {
        return selection_options.value.filter((option) => {
            return Constraint.construct(option.link) != null
        })
    }
    return selection_options.value
})

const edit_point_hover = (event: MouseEvent, state: boolean) => {
    editor_data.show_editpoints = state
}
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
    border-radius: 5px;
    padding: 5px;
}

.selection_element_container {
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    align-items: center;
    overflow-y: auto;
}

.selection_element {
    padding: 2px;
    cursor: pointer;
    display: flex;
    justify-items: center;
    align-items: center;
}

.selection_element:hover {
    background-color: #f0f0f0;
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