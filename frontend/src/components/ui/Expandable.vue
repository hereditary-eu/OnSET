<template>
    <div class="expandable_container">
        <div class="expandable_frame" v-show="expanded" @click.capture="expanded = false">
            <div class="expandable_window" @click="expanded = true">
                <div class="expandable_header">
                    <slot name="header">
                    </slot>
                </div>
                <div class="expandable_content">
                    <slot name="content">
                    </slot>
                </div>
            </div>
        </div>
        <div class="expandable_trigger" @click.capture="expanded = !expanded">
            <slot name="trigger"></slot>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, defineModel } from 'vue'
const expanded = defineModel<boolean>({ default: false })

</script>
<style lang="css">
.expandable_frame {
    cursor: pointer;
    background-color: rgba(187, 187, 187, 0.5);
    height: 100%;
    width: 100vw;
    position: absolute;
    top: -2rem;
    left: -2rem;
    z-index: 100;
    display: flex;
    align-items: center;
    justify-content: center;
}

.expandable_container {
    width: 100%;
    height: 100%;
}

.expandable_trigger {
    cursor: pointer;
    display: flex;
    justify-content: center;
    align-items: center;
    width: 100%;
    height: 100%;
}

.expandable_window {
    cursor: default;
    background-color: white;
    border-radius: 5px;
    padding: 10px;
    width: 80%;
    height: 80%;
    display: flex;
    flex-direction: column;
    justify-content: start;
    align-items: center;
}

.expandable_header {
    width: 100%;
    height: 10%;
    display: flex;
    justify-content: center;
    align-items: center;
    border-bottom: 1px solid rgb(192, 213, 191);
}

.expandable_content {
    width: 100%;
    height: 100%;
    margin: 10px;
}
</style>