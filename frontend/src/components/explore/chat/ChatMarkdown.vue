<template>
    <!-- Markdown of an agent message (GitHub flavoured, line breaks kept), sanitised before rendering. -->
    <div class="chat_markdown" v-html="html"></div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const { content } = defineProps<{ content: string }>()

// links leave the app in a new tab
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
    if (node.tagName == 'A' && node.getAttribute('href')) {
        node.setAttribute('target', '_blank')
        node.setAttribute('rel', 'noopener noreferrer')
    }
})

// re-rendered on every streamed chunk, so an unclosed block shows as it is completed
const html = computed(() => DOMPurify.sanitize(marked.parse(content, { gfm: true, breaks: true, async: false })))
</script>
<style scoped>
.chat_markdown {
    white-space: normal;
}

/* the global reset sets every element to normal weight */
.chat_markdown :deep(strong),
.chat_markdown :deep(b),
.chat_markdown :deep(th) {
    font-weight: 600;
}

.chat_markdown :deep(> :first-child) {
    margin-top: 0;
}

.chat_markdown :deep(> :last-child) {
    margin-bottom: 0;
}

.chat_markdown :deep(p),
.chat_markdown :deep(ul),
.chat_markdown :deep(ol),
.chat_markdown :deep(pre),
.chat_markdown :deep(blockquote),
.chat_markdown :deep(table) {
    margin: 0 0 var(--space-1);
}

.chat_markdown :deep(h1),
.chat_markdown :deep(h2),
.chat_markdown :deep(h3),
.chat_markdown :deep(h4) {
    margin: var(--space-2) 0 var(--space-1);
    font-size: var(--fs-sm);
    font-weight: 600;
}

.chat_markdown :deep(ul),
.chat_markdown :deep(ol) {
    padding-left: 1.5rem;
    list-style-position: outside;
}

.chat_markdown :deep(code) {
    font-size: 0.92em;
    padding: 0 2px;
    border-radius: 2px;
    background: var(--c-accent-soft);
}

.chat_markdown :deep(pre) {
    padding: var(--space-1);
    overflow-x: auto;
    border: 1px solid var(--c-border);
    border-radius: var(--radius);
}

.chat_markdown :deep(pre code) {
    padding: 0;
    color: var(--color-text);
    background: none;
    white-space: pre;
}

.chat_markdown :deep(blockquote) {
    padding-left: var(--space-2);
    border-left: 2px solid var(--c-border);
    opacity: 0.85;
}

.chat_markdown :deep(table) {
    border-collapse: collapse;
    font-size: var(--fs-xs);
}

.chat_markdown :deep(th),
.chat_markdown :deep(td) {
    padding: 2px var(--space-1);
    border: 1px solid var(--c-border);
    text-align: left;
}

.chat_markdown :deep(a) {
    padding: 0;
    color: var(--color-link);
    text-decoration: underline;
}
</style>
