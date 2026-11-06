<template>
    <!-- A corpus document in a dialog, with the (case-insensitive) occurrences of ``terms`` marked;
         opens scrolled to the first one. Teleported, so it is above other dialogs (e.g. an expanded result). -->
    <Teleport to="body">
        <div class="document_viewer_backdrop" @click.self="emit('close')">
            <article class="panel document_viewer">
                <header class="panel_header">
                    <span class="panel_title document_viewer_title" :title="doc.title">{{ doc.title }}</span>
                    <span class="toolbar_spacer"></span>
                    <span v-if="terms.length" class="message">{{ hits }} match{{ hits == 1 ? '' : 'es' }}</span>
                    <OnsetBtn size="small" :toggleable="false" icon="mdi-close" @click="emit('close')" />
                </header>
                <p class="message document_viewer_path" :title="doc.id">{{ doc.path || doc.id }}<template v-if="doc.path && doc.path != doc.id"> · {{ doc.id }}</template></p>
                <div ref="body" class="panel_body document_viewer_body">
                    <template v-for="(p, j) in parts" :key="j"><mark v-if="p.hit">{{ p.text }}</mark><template v-else>{{ p.text }}</template></template>
                </div>
            </article>
        </div>
    </Teleport>
</template>
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import OnsetBtn from '@/components/ui/OnsetBtn.vue'
import type { BuilderDocument } from '@/utils/builder/api'

const { doc, terms = [] } = defineProps<{
    doc: BuilderDocument
    // marked in the text (words of a search, the names of an instance)
    terms?: string[]
}>()
const emit = defineEmits<{ close: [] }>()
const body = ref<HTMLElement | null>(null)

// longer terms first, so a name wins over a word of it; any whitespace between words matches
const pattern = computed(() => {
    const escaped = [...new Set(terms.map((t) => t.trim()).filter((t) => t.length > 1))]
        .sort((a, b) => b.length - a.length)
        .map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+'))
    return escaped.length ? new RegExp(`(${escaped.join('|')})`, 'i') : null
})
const parts = computed(() => pattern.value
    ? doc.text.split(pattern.value).map((text, i) => ({ text, hit: i % 2 == 1 }))
    : [{ text: doc.text, hit: false }])
const hits = computed(() => parts.value.filter((p) => p.hit).length)

const onKey = (evt: KeyboardEvent) => {
    if (evt.key == 'Escape') {
        emit('close')
    }
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

watch(() => doc, async () => {
    await nextTick()
    body.value?.scrollTo({ top: 0 })
    body.value?.querySelector('mark')?.scrollIntoView({ block: 'center' })
}, { immediate: true })
</script>
<style scoped>
.document_viewer_backdrop {
    position: fixed;
    inset: 0;
    z-index: 300;
    background: rgba(0, 0, 0, 0.25);
    display: flex;
    align-items: center;
    justify-content: center;
}

.document_viewer {
    width: min(48rem, 90vw);
    max-height: 80vh;
}

.document_viewer_title {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.document_viewer_path {
    margin: 0;
    padding: 0 var(--space-3);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.document_viewer_body {
    padding: var(--space-2) var(--space-3);
    font-size: var(--fs-md);
    line-height: 1.5;
    white-space: pre-wrap;
}

mark {
    background: var(--c-accent-soft);
}
</style>
