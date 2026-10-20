<template>
    <!-- One tool call of the agent: name, arguments, result and the graph change it made. -->
    <div class="chat_tool" :class="`chat_tool_${call.status}`">
        <button type="button" class="chat_tool_header" @click="expanded = !expanded"
            :title="expanded ? 'Hide arguments and result' : 'Show arguments and result'">
            <OnsetIcon :icon="status_icon" class="chat_tool_status" />
            <span class="chat_tool_name">{{ call.name }}</span>
            <span class="chat_tool_args">{{ args_summary }}</span>
            <span v-if="change_summary" class="chat_tool_changes">{{ change_summary }}</span>
            <OnsetIcon :icon="expanded ? 'mdi-chevron-up' : 'mdi-chevron-down'" />
        </button>
        <div v-if="expanded" class="chat_tool_body">
            <div class="chat_tool_label">Arguments</div>
            <pre>{{ pretty(call.arguments) }}</pre>
            <template v-if="call.status != 'running'">
                <div class="chat_tool_label">{{ call.error ? 'Error' : 'Result' }}</div>
                <pre>{{ call.error ?? pretty(call.result) }}</pre>
            </template>
        </div>
        <ChatGraphPreview v-if="call.changes" :change="call.changes" :details="call.details"></ChatGraphPreview>
    </div>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import OnsetIcon from '@/components/ui/OnsetIcon.vue'
import ChatGraphPreview from './ChatGraphPreview.vue'
import type { ToolCallMessage } from '@/utils/agent/protocol'

const { call } = defineProps<{
    call: ToolCallMessage
}>()

const expanded = ref(false)

const status_icon = computed(() => {
    switch (call.status) {
        case 'running':
            return 'mdi-loading mdi-spin'
        case 'error':
            return 'mdi-alert-circle-outline'
        default:
            return 'mdi-check'
    }
})

const args_summary = computed(() => Object.values(call.arguments || {})
    .filter((v) => v !== null && v !== undefined)
    .map((v) => typeof v == 'string' ? v : JSON.stringify(v))
    .join(', '))

const count = (n: number, word: string) => n ? `${n} ${word}${n > 1 ? 's' : ''}` : ''
const change_summary = computed(() => {
    const change = call.changes
    if (!change) {
        return ''
    }
    const added = [count(change.added.subjects.length, 'subject'), count(change.added.links.length, 'link')].filter((s) => s)
    const removed = [count(change.removed.subjects.length, 'subject'), count(change.removed.links.length, 'link')].filter((s) => s)
    return [added.length ? `+${added.join(', ')}` : '', removed.length ? `−${removed.join(', ')}` : ''].filter((s) => s).join(' ')
})

const pretty = (value: unknown) => JSON.stringify(value, null, 1)
</script>
<style scoped>
.chat_tool {
    border: 1px solid var(--c-border);
    border-radius: var(--radius);
    background: var(--c-surface);
    font-size: var(--fs-xs);
    overflow: hidden;
}

.chat_tool_error {
    border-color: var(--c-node-removed);
}

.chat_tool_header {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    width: 100%;
    padding: 0.15rem var(--space-1);
    font: inherit;
    color: inherit;
    text-align: left;
    background: none;
    border: none;
    cursor: pointer;
}

.chat_tool_header:hover {
    background: var(--c-hover);
}

.chat_tool_status {
    color: var(--c-accent);
}

.chat_tool_error .chat_tool_status {
    color: var(--c-node-removed);
}

.chat_tool_name {
    font-family: var(--font-mono);
    font-weight: 600;
    white-space: nowrap;
}

.chat_tool_args {
    flex: 1 1 auto;
    min-width: 0;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
    opacity: 0.75;
}

.chat_tool_changes {
    white-space: nowrap;
    color: var(--c-accent);
    font-weight: 600;
}

.chat_tool_body {
    padding: 0 var(--space-1) var(--space-1);
}

.chat_tool_label {
    font-weight: 600;
    margin-top: var(--space-1);
}

.chat_tool_body pre {
    margin: 0;
    max-height: 10rem;
    overflow: auto;
    font-family: var(--font-mono);
    font-size: var(--fs-xs);
    white-space: pre-wrap;
    word-break: break-word;
    background: var(--c-hover);
    padding: var(--space-1);
    border-radius: var(--radius);
}
</style>
