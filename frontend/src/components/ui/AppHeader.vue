<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { listConfigs, type ConfigSummary } from '@/utils/api'
import OnsetIcon from './OnsetIcon.vue'

const route = useRoute()
const router = useRouter()
const configs = ref([] as ConfigSummary[])

const configId = computed(() => route.params.configId as string | undefined)

watch(configId, async (id) => {
    if (id && configs.value.length === 0) {
        configs.value = await listConfigs().catch(() => [])
    }
}, { immediate: true })

// Switch configuration while staying on the same kind of page
const switchConfig = (event: Event) => {
    const target = (event.target as HTMLSelectElement).value
    router.push({ name: route.name ?? 'explore', params: { configId: target } })
}
</script>

<template>
    <header class="app_header">
        <RouterLink v-if="configId" :to="{ name: 'configs' }" class="back" title="Back to the configurations">
            <OnsetIcon icon="mdi-arrow-left" />
        </RouterLink>
        <RouterLink :to="{ name: 'configs' }" class="brand">OnSET</RouterLink>
        <template v-if="configId">
            <span class="divider">/</span>
            <select class="config" :value="configId" @change="switchConfig" title="Loaded configuration">
                <option v-for="config in configs" :key="config.id" :value="config.id">{{ config.name }}</option>
                <option v-if="!configs.some(c => c.id === configId)" :value="configId">{{ configId }}</option>
            </select>
            <nav class="views">
                <RouterLink :to="{ name: 'explore', params: { configId } }">Explore</RouterLink>
                <RouterLink :to="{ name: 'circles', params: { configId } }">Class tree</RouterLink>
            </nav>
        </template>
        <a class="disclaimer" href="https://github.com/hereditary-eu/OnSET/blob/main/DISCLAIMER.md" target="_blank"
            rel="noopener">Research use only. Not a medical device.</a>
    </header>
</template>

<style scoped>
.app_header {
    position: sticky;
    top: 0;
    z-index: 10;
    display: flex;
    align-items: center;
    gap: var(--space-2);
    height: 2rem;
    padding: 0 var(--space-3);
    font-size: var(--fs-sm);
    border-bottom: 1px solid var(--color-border);
    background: var(--color-background);
}

.brand {
    font-weight: 700;
    color: var(--color-text);
}

.back {
    display: inline-flex;
    align-items: center;
    color: var(--color-text);
}

.divider {
    opacity: 0.4;
}

.config {
    font: inherit;
    padding: 0.1rem var(--space-1);
    border: 1px solid transparent;
    border-radius: var(--radius);
    background: transparent;
    cursor: pointer;
}

.config:hover,
.config:focus {
    border-color: var(--c-border-ctrl);
}

.views {
    display: flex;
    gap: 0.25rem;
    margin-left: auto;
}

.views a {
    padding: 0.1rem var(--space-2);
    border-radius: var(--radius);
    color: var(--color-text);
}

.disclaimer {
    margin-left: auto;
    font-size: var(--fs-xs);
    color: var(--color-text);
    opacity: 0.7;
}

.views ~ .disclaimer {
    margin-left: 1rem;
}

.views a.router-link-active {
    color: var(--color-link);
    background-color: hsla(160, 100%, 37%, 0.1);
}
</style>
