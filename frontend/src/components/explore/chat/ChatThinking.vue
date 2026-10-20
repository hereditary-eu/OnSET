<template>
    <!-- Collapsible reasoning of the model: open while it streams, folded when done. -->
    <div class="chat_thinking" :class="{ chat_thinking_open: entry.expanded }">
        <button type="button" class="chat_thinking_header" @click="toggle">
            <OnsetIcon :icon="entry.expanded ? 'mdi-chevron-down' : 'mdi-chevron-right'" />
            <OnsetIcon v-if="entry.streaming" icon="mdi-loading mdi-spin" />
            <span>{{ entry.streaming ? 'Thinking…' : 'Thought' }}</span>
            <span v-if="!entry.expanded" class="chat_thinking_preview">{{ preview }}</span>
        </button>
        <div v-if="entry.expanded" class="chat_thinking_body">{{ entry.content }}</div>
    </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import OnsetIcon from '@/components/ui/OnsetIcon.vue'
import type { ChatEntry } from '@/utils/agent/agentSession'

const { entry } = defineProps<{
    entry: Extract<ChatEntry, { kind: 'thinking' }>
}>()

const preview = computed(() => entry.content.replace(/\s+/g, ' ').trim())

const toggle = () => {
    entry.expanded = !entry.expanded
    entry.toggled = true
}
</script>
<style scoped>
.chat_thinking {
    font-size: var(--fs-xs);
    color: #666;
}

.chat_thinking_header {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    width: 100%;
    padding: 0;
    font: inherit;
    color: inherit;
    text-align: left;
    background: none;
    border: none;
    cursor: pointer;
}

.chat_thinking_preview {
    flex: 1 1 auto;
    min-width: 0;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
    opacity: 0.7;
}

.chat_thinking_body {
    margin: var(--space-1) 0 0 0.6rem;
    padding-left: var(--space-2);
    border-left: 2px solid var(--c-border);
    max-height: 12rem;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-word;
}
</style>
