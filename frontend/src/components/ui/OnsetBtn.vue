<script setup lang="ts">
import { ref, watch, reactive, computed, onMounted, type ModelRef, defineEmits } from 'vue'

const model: ModelRef<boolean> = defineModel({})
const props = defineProps({
    btn_height: {
        type: String,
        default: '2.8rem'
    },
    btn_width: {
        type: String,
        default: '16rem'
    },
    toggleable: {
        type: Boolean,
        default: true
    },
    active: {
        type: Boolean,
        default: true
    }
})
const emit = defineEmits(['click'])
function update(evt) {
    evt.preventDefault()
    if (!props.active) {
        return
    }
    emit('click', evt)
    if (props.toggleable) {
        model.value = !model.value
    }
}
const clses = computed(() => {
    return {
        'clickable_container': true,
        'clickable_disabled': !props.active,
        'clickable_selected': model.value
    }
})
</script>
<template>
    <div class="wrapper_clickable">
        <button v-if="props.toggleable" :class="clses" @click="update">
            <slot></slot>
        </button>
        <div v-else @click="update">
            <input type="checkbox" id="btnControl" />
            <label :class="clses" for="btnControl">
                <slot></slot>
            </label>

        </div>
    </div>
</template>
<style scoped>
.clickable_container {
    cursor: pointer;
    padding: 0.5rem;
    border: 1px solid #b8b7b7;
    height: v-bind("props.btn_height");
    width: v-bind("props.btn_width");
    text-align: center;
    display: flex;
    align-items: center;
    justify-content: center;
    justify-items: center;
    background-color: white;
}

.clickable_disabled {
    cursor: not-allowed;
    border-color: #dcdcdc;
    background-color: #c1c1c1;
}

.clickable_container:hover {
    border-color: #8fa88f;
}

.clickable_container:active {
    border-color: #8fa88f;
}

.clickable_selected {
    background-color: #d5edde;
}

.wrapper_clickable {
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 2px;
}

#btnControl {
    display: none;
}
</style>