<template>
    <g id="propview" @mouseout.capture="edit_point_hover($event, false)"
        @mouseenter.capture="edit_point_hover($event, true)" @mouseover="edit_point_hover($event, true)">
        <g :transform="`translate(${attachment_pt.x},${attachment_pt.y})`" v-if="display">
            <foreignObject :height="dimensions.height" :width="dimensions.width">
                <div class="prop_div_container" :style="{ 'height': `100%` }">
                    <Loading v-if="editor_data.loading"></Loading>
                    <div v-else class="prop_element_container">
                        <div class="prop_element" v-for="(prop, key) of props" :key="key">
                            <div class="prop_key">{{ prop.label }}</div>
                            <div class="prop_values">
                                <div class="prop_value" v-for="v of prop.values">
                                    {{ v.label }}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </foreignObject>

            <g v-show="editor_data.show_editpoints">
                <circle :cx="dimensions.width" :cy="0" :r="editor_data.editpoint_r"
                    class="edit_point edit_point_delete" @click="display = false"></circle>
            </g>
        </g>
    </g>
</template>
<script setup lang="ts">
import { ref, watch, reactive, computed, onMounted } from 'vue'
import { SubQuery } from '@/utils/sparql/representation';
import { BACKEND_URL } from '@/utils/config';
import { Api, RELATION_TYPE, RETURN_TYPE, type Property } from '@/api/client.ts/Api';
import { LINK_WIDTH, NODE_HEIGHT, NODE_WIDTH, NodeSide, SelectorOpenEvent } from '@/utils/sparql/helpers';
import Loading from '@/components/ui/Loading.vue';
import { readableName, type PropertiesOpenEvent } from '@/utils/sparql/querymapper';
import type { MixedResponse } from '@/utils/sparql/store';
const dimensions = reactive({
    width: 350,
    height: 600
})
const emit = defineEmits<{
    select: [value: MixedResponse]
}>()
const api = new Api({
    baseURL: BACKEND_URL
})
const { selection_event } = defineProps({
    selection_event: {
        type: Object as () => PropertiesOpenEvent,
        required: true
    }
})

const editor_data = reactive({
    show_editpoints: false,
    editpoint_r: 7,
    loading: false,
})
type PropResponse = Record<string, Property>

const props = ref<PropResponse>({})
const display = defineModel<boolean>({ default: false })
const update_props = async () => {
    console.log('fetching selection options', selection_event)
    if (display) {
        (async () => {
            editor_data.loading = true
            const options = await api.classes.getNamedInstancePropertiesClassesInstancesPropertiesGet({
                instance_id: selection_event.node.instance_id,
            })
            for (const key in options.data) {
                const prop = options.data[key]
                prop.label = readableName(prop.property, prop.label)
                for (const value of prop.values) {
                    value.label = readableName(value.value, value.label)
                }
            }
            props.value = options.data
            editor_data.loading = false

        })().catch((e) => {
            console.error('Error fetching selection options', e)
            editor_data.loading = false
        })
    } else {
    }
}
// watch(() => display, update_selection_options, { deep: false })
watch(() => selection_event, () => {
    update_props()
}, { deep: false })
onMounted(() => {
    update_props()
})
// watch(() => editor_data.q, update_selection_options, { deep: false })
const attachment_pt = computed(() => {
    if (!selection_event) {
        return { x: 0, y: 0 }
    }
    return { x: selection_event.node.x + selection_event.node.width / 2, y: selection_event.node.y + selection_event.node.height }

})

const edit_point_hover = (event: MouseEvent, state: boolean) => {
    editor_data.show_editpoints = state
}
</script>

<style lang="scss">
.prop_div_container {
    display: flex;
    flex-direction: column;
    // justify-content: ;
    align-items: center;
    background-color: white;
    border: 1px solid rgb(197, 196, 168);
    // border-radius: 5px;
    padding: 5px;
}

.prop_element_container {
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    align-items: center;
    overflow-y: auto;
}

.prop_element {
    padding: 2px;
    display: flex;
    justify-items: center;
    align-items: center;
}
.prop_element{
    display: flex;
    flex-direction: row;
    justify-content: space-between;
    align-items: center;
    width: 100%;
    padding: 5px;
    border-bottom: 1px solid rgb(197, 196, 168);
}
.prop_key{
    font-weight: bold;
    width: 50%;
}
.prop_values{
    width: 50%;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    align-items: flex-start;
}
</style>