<template>
    <div class="expandable_container">
        <div class="expandable_frame" v-if="expanded" @click.self="expanded = false">
            <div class="expandable_window">
                <div class="expandable_header">
                    <slot name="header"></slot>
                </div>
                <div class="expandable_content">
                    <slot name="content"></slot>
                </div>
            </div>
        </div>
        <div class="expandable_trigger" @click.capture="expanded = !expanded">
            <slot name="trigger"></slot>
        </div>
    </div>
</template>

<script setup lang="ts">
const expanded = defineModel<boolean>({ default: false })
</script>
<style>
.expandable_container {
    width: 100%;
    height: 100%;
}

/* full-viewport modal, independent of the positioned ancestors */
.expandable_frame {
    position: fixed;
    inset: 0;
    z-index: 100;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    background-color: rgba(187, 187, 187, 0.5);
}

.expandable_window {
    display: flex;
    flex-direction: column;
    width: 80%;
    height: 80%;
    padding: var(--space-2);
    border-radius: var(--radius);
    background-color: var(--c-surface);
    cursor: default;
}

.expandable_header {
    flex: 0 0 auto;
    padding-bottom: var(--space-1);
    border-bottom: 1px solid var(--c-border);
    font-size: var(--fs-lg);
    font-weight: 600;
    text-align: center;
}

.expandable_content {
    flex: 1 1 auto;
    min-height: 0;
}

.expandable_trigger {
    display: flex;
    justify-content: center;
    align-items: center;
    width: 100%;
    height: 100%;
    cursor: pointer;
}
</style>
