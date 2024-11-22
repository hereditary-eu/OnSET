<script setup lang="ts">
import { ref, watch, reactive, computed, onMounted, type ModelRef, defineEmits } from 'vue'

const model: ModelRef<boolean> = defineModel({})
const props = defineProps({
    btn_height: {
        type: String,
        default: '4rem'
    }
})
const emit = defineEmits(['click'])
function update(evt) {
    emit('click', evt)
    model.value = !model.value
}
</script>
<template>
    <div class="wrapper_clickable">
        <button class="clickable_container" @click="update" :class="model ? 'clickable_selected' : null">
            <slot></slot>
        </button>
    </div>
</template>
<style scoped>
.clickable_container {
    cursor: pointer;
    width: 16rem;
    padding: 0.5rem;
    border: 1px solid #e0e0e0;
    height: v-bind("props.btn_height");
    text-align: center;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0.5rem;
    justify-items: center;
}

.clickable_container:hover {
    border-color: #8fa88f;
}

.clickable_selected {
    background-color: #d5edde;
}

.wrapper_clickable {
    display: flex;
    justify-content: center;
    align-items: center;
}
</style>