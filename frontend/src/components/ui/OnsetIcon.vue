<script setup lang="ts">
// Lightweight replacement for <v-icon>: Vuetify is not registered as a plugin,
// so render the Material Design Icons webfont (imported in main.ts) directly.
defineProps({
    icon: {
        type: String,
        required: true
    }
})
</script>
<template>
    <i class="mdi onset_icon" :class="icon" aria-hidden="true"></i>
</template>
<style>
.onset_icon {
    display: inline-block;
    font-size: 1.15em;
    line-height: 1;
    vertical-align: middle;
}
</style>
