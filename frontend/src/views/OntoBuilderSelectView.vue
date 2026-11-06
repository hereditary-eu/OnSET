<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listBuilders, type BuilderSummary } from '@/utils/builder/api'
import OnsetIcon from '@/components/ui/OnsetIcon.vue'

const builders = ref([] as BuilderSummary[])
const loading = ref(true)
const error = ref('')

onMounted(async () => {
    try {
        builders.value = await listBuilders()
    } catch (e) {
        console.error(e)
        error.value = 'The backend is not reachable, so no ontology builders could be loaded.'
    } finally {
        loading.value = false
    }
})
</script>

<template>
    <main class="builder_select">
        <h2>Ontology builder</h2>
        <p class="intro">
            Design an ontology for a collection of text documents. A small language model reads the documents and
            fills a knowledge graph with what it finds, restarting whenever the ontology changes. Pick a document
            collection.
        </p>
        <p v-if="loading" class="intro">Loading…</p>
        <p v-else-if="error" class="notice">{{ error }}</p>
        <RouterLink v-for="b in builders" :key="b.id" class="builder_card"
            :to="{ name: 'onto-builder-session', params: { builderId: b.id } }">
            <span class="builder_name"><OnsetIcon icon="mdi-file-document-multiple-outline" /> {{ b.name }}</span>
            <span class="builder_desc">{{ b.description || 'No description.' }}</span>
        </RouterLink>
    </main>
</template>

<style scoped>
.builder_select {
    max-width: 40rem;
    margin: 3rem auto;
    padding: 0 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
}

h2 {
    font-weight: 500;
}

.intro {
    opacity: 0.8;
}

.builder_card {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    padding: 0.5rem 1rem;
    border: 1px solid #b8b7b7;
    border-radius: 4px;
    color: var(--color-text);
}

.builder_card:hover {
    border-color: var(--color-link);
}

.builder_name {
    color: var(--color-link);
}

.builder_desc {
    font-size: 0.85rem;
    opacity: 0.8;
}

.notice {
    padding: 0.5rem 0.75rem;
    border-left: 3px solid #c0392b;
    background: #fdf2f1;
}
</style>
