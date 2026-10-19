<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { listConfigs, type ConfigSummary } from '@/utils/api'

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
            <v-icon icon="mdi-arrow-left" size="small"></v-icon>
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
    </header>
</template>

<style scoped>
.app_header {
    position: sticky;
    top: 0;
    z-index: 10;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    height: 2.75rem;
    padding: 0 1rem;
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
    padding: 0.15rem 0.4rem;
    border: 1px solid transparent;
    border-radius: 4px;
    background: transparent;
    cursor: pointer;
}

.config:hover,
.config:focus {
    border-color: #b8b7b7;
}

.views {
    display: flex;
    gap: 0.25rem;
    margin-left: auto;
}

.views a {
    padding: 0.2rem 0.6rem;
    border-radius: 4px;
    color: var(--color-text);
}

.views a.router-link-active {
    color: var(--color-link);
    background-color: hsla(160, 100%, 37%, 0.1);
}
</style>
