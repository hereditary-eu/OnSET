<template>
    <g id="outlink_selector" @mouseout.capture="edit_point_hover($event, false)"
        @mouseenter.capture="edit_point_hover($event, true)" @mouseover="edit_point_hover($event, true)">
        <g :transform="`translate(${attachment_pt.x},${attachment_pt.y})`" v-if="display">
            <foreignObject :height="PANEL_HEIGHT" :width="PANEL_WIDTH">
                <div class="selection_div_container">
                    <input type="text" class="text_input selection_search" placeholder="Search..."
                        v-model="editor_data.q" />
                    <div class="selection_element_container">
                        <div class="selection_element" v-for="instance of selection_options"
                            @click="select_option(instance, $event)" :key="instance.id">
                            {{ readableName(instance.id, instance.label) }}
                        </div>
                        <Loading v-if="editor_data.loading"></Loading>
                        <OnsetBtn size="small" @click="loadMore"
                            v-if="selection_options.length > 0 && !editor_data.reached_end" :toggleable="false">More
                        </OnsetBtn>
                    </div>
                </div>
            </foreignObject>

            <circle v-show="editor_data.show_editpoints" :cx="PANEL_WIDTH" :cy="0" :r="EDITPOINT_R"
                class="edit_point edit_point_delete" @click="display = false" />
        </g>
    </g>
</template>
<script setup lang="ts">
import { ref, watch, reactive, computed, onMounted } from 'vue'
import { type Instance } from '@/api/client.ts/Api';
import { CONSTRAINT_PADDING, EDITPOINT_R, InstanceSelectorOpenEvent, PANEL_WIDTH } from '@/utils/sparql/helpers';
import Loading from '@/components/ui/Loading.vue';
import OnsetBtn from '@/components/ui/OnsetBtn.vue';
import { readableName } from '@/utils/sparql/querymapper';
import { debounce } from "@/utils/helpers";
import { api } from '@/utils/api'
const PANEL_HEIGHT = 200
const emit = defineEmits<{
    select: [value: Instance]
}>()
const { selection_event } = defineProps({
    selection_event: {
        type: Object as () => InstanceSelectorOpenEvent,
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
}), 200, false)
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
