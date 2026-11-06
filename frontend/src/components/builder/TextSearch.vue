<template>
    <!-- Search over the builder's documents; a hit opens its document. -->
    <div class="text_search">
        <form class="toolbar" @submit.prevent="search">
            <input v-model="q" class="text_input text_search_input" placeholder="Search the documents…" />
            <OnsetBtn size="small" :toggleable="false" icon="mdi-magnify" :active="!!q.trim()" @click="search" />
        </form>
        <p v-if="loading" class="message"><OnsetIcon icon="mdi-loading mdi-spin" /> Searching…</p>
        <p v-else-if="error" class="message text_search_error">{{ error }}</p>
        <p v-else-if="searched && hits.length == 0" class="message">Nothing found.</p>
        <div class="text_search_hits">
            <button v-for="(hit, i) in hits" :key="i" type="button" class="text_search_hit" @click="open(hit.doc_id)">
                <span class="text_search_title">{{ hit.title }}</span>
                <span><template v-for="(p, j) in highlight(hit.text)" :key="j"><mark v-if="p.hit">{{ p.text }}</mark><template v-else>{{ p.text }}</template></template></span>
            </button>
        </div>
        <div v-if="doc" class="text_search_backdrop" @click.self="doc = null">
            <article class="panel text_search_doc">
                <header class="panel_header">
                    <span class="panel_title text_search_doc_title">{{ doc.title }}</span>
                    <span class="toolbar_spacer"></span>
                    <OnsetBtn size="small" :toggleable="false" icon="mdi-close" @click="doc = null" />
                </header>
                <div class="panel_body text_search_doc_body">
                    <template v-for="(p, j) in highlight(doc.text)" :key="j"><mark v-if="p.hit">{{ p.text }}</mark><template v-else>{{ p.text }}</template></template>
                </div>
            </article>
        </div>
    </div>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import OnsetBtn from '@/components/ui/OnsetBtn.vue'
import OnsetIcon from '@/components/ui/OnsetIcon.vue'
import { getDocument, searchText, type BuilderDocument, type Snippet } from '@/utils/builder/api'

const { builderId } = defineProps<{ builderId: string }>()

const q = ref('')
const searched_q = ref('')
const hits = ref([] as Snippet[])
const searched = ref(false)
const loading = ref(false)
const error = ref('')
const doc = ref(null as BuilderDocument | null)

const search = async () => {
    if (!q.value.trim()) {
        return
    }
    loading.value = true
    error.value = ''
    try {
        hits.value = await searchText(builderId, q.value)
        searched_q.value = q.value
        searched.value = true
    } catch (e) {
        error.value = `Search failed: ${e}`
    } finally {
        loading.value = false
    }
}

const open = async (doc_id: string) => {
    try {
        doc.value = await getDocument(builderId, doc_id)
    } catch (e) {
        error.value = `Could not open the document: ${e}`
    }
}

// split text into parts, marking the (case-insensitive) occurrences of the searched words
const highlight = (text: string) => {
    const words = searched_q.value.split(/\s+/).filter((w) => w.length > 2).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
    if (!words.length) {
        return [{ text, hit: false }]
    }
    return text.split(new RegExp(`(${words.join('|')})`, 'i')).map((t, i) => ({ text: t, hit: i % 2 == 1 }))
}
</script>
<style scoped>
.text_search {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    height: 100%;
    min-height: 0;
}

.text_search_input {
    flex: 1 1 auto;
}

.text_search_error {
    color: #b3261e;
}

.text_search_hits {
    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
}

.text_search_hit {
    display: flex;
    flex-direction: column;
    gap: 2px;
    text-align: left;
    font: inherit;
    font-size: var(--fs-xs);
    color: inherit;
    padding: var(--space-1);
    border: 1px solid var(--c-border);
    border-radius: var(--radius);
    background: var(--c-surface);
    cursor: pointer;
}

.text_search_hit:hover {
    border-color: var(--c-accent);
    background: var(--c-hover);
}

.text_search_title {
    font-weight: 600;
}

mark {
    background: var(--c-accent-soft);
}

.text_search_backdrop {
    position: fixed;
    inset: 0;
    z-index: 100;
    background: rgba(0, 0, 0, 0.25);
    display: flex;
    align-items: center;
    justify-content: center;
}

.text_search_doc {
    width: min(48rem, 90vw);
    max-height: 80vh;
}

.text_search_doc_title {
    overflow: hidden;
    text-overflow: ellipsis;
}

.text_search_doc_body {
    padding: var(--space-2) var(--space-3);
    font-size: var(--fs-md);
    line-height: 1.5;
    white-space: pre-wrap;
}
</style>
