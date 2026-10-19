<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { listConfigs, type ConfigSummary } from '@/utils/api'

const route = useRoute()
const configs = ref([] as ConfigSummary[])
const selected = ref('')
const loading = ref(true)
const error = ref('')

const selectedConfig = computed(() => configs.value.find(c => c.id === selected.value))
const routeNotice = computed(() => {
    if (route.query.unknown) {
        return `There is no configuration called '${route.query.unknown}'.`
    }
    if (route.query.failed) {
        return `The configuration '${route.query.failed}' could not be loaded.`
    }
    return ''
})

const loadConfigs = async () => {
    loading.value = true
    error.value = ''
    try {
        configs.value = await listConfigs()
        selected.value = (configs.value.find(c => c.default) ?? configs.value[0])?.id ?? ''
    } catch (e) {
        console.error(e)
        error.value = 'The backend is not reachable, so no configurations could be loaded.'
    } finally {
        loading.value = false
    }
}
onMounted(loadConfigs)
// the backend may have come back after a failed navigation
watch(() => route.query.failed, (failed) => {
    if (failed && error.value) {
        loadConfigs()
    }
})
</script>

<template>
    <main class="config_select">
        <h2>Ontology and Semantic data Exploration Tool</h2>
        <p class="intro">
            OnSET lets you explore ontologies and the semantic data attached to them, and build queries over them
            visually. Pick the knowledge graph configuration to work with.
        </p>

        <p v-if="routeNotice" class="notice">{{ routeNotice }}</p>

        <p v-if="loading" class="muted">Loading configurations…</p>
        <div v-else-if="error" class="notice">
            {{ error }}
            <button class="retry" @click="loadConfigs">Retry</button>
        </div>
        <div v-else class="picker">
            <label for="config_select">Configuration</label>
            <select id="config_select" v-model="selected">
                <option v-for="config in configs" :key="config.id" :value="config.id">
                    {{ config.name }}
                </option>
            </select>
            <p v-if="selectedConfig" class="description">
                {{ selectedConfig.description || 'No description.' }}
                <span v-if="selectedConfig.multimodal" class="tag">multimodal</span>
            </p>
            <div v-if="selectedConfig" class="actions">
                <RouterLink class="action primary" :to="{ name: 'explore', params: { configId: selectedConfig.id } }">
                    <v-icon icon="mdi-graph-outline" size="small"></v-icon> Explore
                </RouterLink>
                <RouterLink class="action" :to="{ name: 'circles', params: { configId: selectedConfig.id } }">
                    <v-icon icon="mdi-chart-bubble" size="small"></v-icon> Class tree
                </RouterLink>
            </div>
        </div>
    </main>
</template>

<style scoped>
.config_select {
    max-width: 40rem;
    margin: 3rem auto;
    padding: 0 1rem;
}

h2 {
    font-weight: 500;
    margin-bottom: 0.5rem;
}

.intro,
.muted {
    color: var(--color-text);
    opacity: 0.8;
}

.picker {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-top: 2rem;
}

label {
    font-size: 0.85rem;
    opacity: 0.7;
}

select {
    font: inherit;
    padding: 0.5rem;
    border: 1px solid #b8b7b7;
    border-radius: 4px;
    background: white;
}

.description {
    min-height: 3rem;
}

.tag {
    font-size: 0.75rem;
    border: 1px solid #b8b7b7;
    border-radius: 3px;
    padding: 0 0.3rem;
    margin-left: 0.3rem;
}

.actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
}

.action {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.5rem 1rem;
    border: 1px solid #b8b7b7;
    border-radius: 4px;
    color: var(--color-text);
}

.action.primary {
    border-color: var(--color-link);
    color: var(--color-link);
}

.notice {
    padding: 0.5rem 0.75rem;
    border-left: 3px solid #c0392b;
    background: #fdf2f1;
}

.retry {
    font: inherit;
    margin-left: 0.5rem;
    cursor: pointer;
    text-decoration: underline;
    background: none;
    border: none;
}
</style>
