<template>
    <g id="outlink_selector" @mouseout.capture="edit_point_hover($event, false)"
        @mouseenter.capture="edit_point_hover($event, true)" @mouseover="edit_point_hover($event, true)">
        <g :transform="`translate(${attachment_pt.x},${attachment_pt.y})`" v-if="display">
            <foreignObject :height="(NODE_HEIGHT + 10) * 5" :width="NODE_WIDTH + LINK_WIDTH + 35">
                <div class="selection_div_container" :style="{ 'height': `${NODE_HEIGHT * 5 + 10}px` }">

                    <div class="selection_search">
                        <input type="text" placeholder="Search..." v-model="editor_data.q" />
                    </div>
                    <div class="selection_element_container">
                        <div class="selection_element" v-for="instance of selection_options"
                            @click="select_option(instance, $event)" :key="instance.id">
                            {{ readableName(instance.id, instance.label) }}
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
import { Constraint, Link, StringConstraint } from '@/utils/sparql/representation';
import LinkComp from './Link.vue';
import NodeComp from './Node.vue';
import { BACKEND_URL } from '@/utils/config';
import { Api, RELATION_TYPE, RETURN_TYPE, type Instance } from '@/api/client.ts/Api';
import { CONSTRAINT_PADDING, InstanceSelectorOpenEvent, LINK_WIDTH, NODE_HEIGHT, NODE_WIDTH, NodeSide, OutlinkSelectorOpenEvent } from '@/utils/sparql/helpers';
import Loading from '@/components/ui/Loading.vue';
import OnsetBtn from '@/components/ui/OnsetBtn.vue';
import { readableName } from '@/utils/sparql/querymapper';
import { debounce } from "@/utils/helpers";
const emit = defineEmits<{
    select: [value: Instance]
}>()
const api = new Api({
    baseURL: BACKEND_URL

})
const { selection_event } = defineProps({
    selection_event: {
        type: Object as () => InstanceSelectorOpenEvent,
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
    page_size: 20
})
const display = defineModel<boolean>()
const selection_options = ref([] as Instance[])

const debounced_search = debounce(() => (async () => {
    selection_options.value = []
    editor_data.offset = 0
    await loadMore()
})().catch(e => {
    console.error('Error fetching selection options', e)
    editor_data.loading = false
}), 200, true)
const update_selection_options = async () => {
    if (display) {
        debounced_search()
    } else {
        selection_options.value = []
    }
}
const subject_id = computed(() => {
    if (!selection_event) {
        return null
    }
    return selection_event.node.subject_id
})
// watch(() => display, update_selection_options, { deep: false })
watch(() => { selection_event ? selection_event.node : selection_event }, () => {
    console.log('subject_id event changed!', subject_id)
    editor_data.q = ''
    update_selection_options()
}, { deep: false })
watch(() => editor_data.q, () => {
    console.log('Query changed!', editor_data.q)
    update_selection_options()
}, { deep: false })
const attachment_pt = computed(() => {
    if (!selection_event) {
        return { x: 0, y: 0 }
    }
    let computed_constraints = selection_event.node.computeConstraintOffsets(CONSTRAINT_PADDING)
    let current_prop = computed_constraints.find((constr) => constr.constraint == selection_event.constraint)
    if (current_prop) {
        return { x: selection_event.node.x + selection_event.node.width / 2, y: selection_event.node.y + current_prop.y + current_prop.constraint.height + CONSTRAINT_PADDING }
    }
    display.value = false
    return { x: selection_event.node.x + selection_event.node.width / 2, y: selection_event.node.y + selection_event.node.height }
})
const select_option = (selected_option: Instance, event: MouseEvent) => {
    display.value = false
    selection_event.constraint.instance = selected_option
    emit('select', selected_option)
}

const edit_point_hover = (event: MouseEvent, state: boolean) => {
    editor_data.show_editpoints = state
}
const loadMore = async () => {
    if (display.value == false) {
        return
    }
    editor_data.loading = true
    let query_id = ++editor_data.query_id
    console.log('Loading more!', query_id, editor_data.q, editor_data.offset)
    const response = await api.classes.getNamedInstanceSearchClassesInstancesSearchGet({
        cls: selection_event.node.subject_id,
        q: editor_data.q,
        skip: editor_data.offset,
        limit: editor_data.page_size
    })
    if (query_id != editor_data.query_id) {
        return
    }
    if (response.data.length < editor_data.page_size) {
        editor_data.reached_end = true
    }
    editor_data.offset += response.data.length
    editor_data.loading = false
    selection_options.value = selection_options.value.concat(response.data)
}
onMounted(() => {
    loadMore()
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
    width: 100%;
}

.selection_element {
    padding: 2px;
    cursor: pointer;
    display: flex;
    justify-items: center;
    align-items: center;
    width: 100%;
    border: 1px solid rgb(214, 214, 214);
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