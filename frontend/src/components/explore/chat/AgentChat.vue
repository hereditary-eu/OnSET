<template>
    <!-- Agent chat of the explore view's side panel: messages, thinking, tool calls and input. -->
    <div class="agent_chat">
        <div class="toolbar agent_chat_status">
            <span class="agent_chat_dot" :class="`agent_chat_dot_${session.state.status}`"></span>
            <span class="agent_chat_status_text">{{ status_text }}</span>
            <template v-if="session.state.busy">
                <OnsetIcon icon="mdi-loading mdi-spin" />
                <span class="agent_chat_status_text">working…</span>
            </template>
            <span class="toolbar_spacer"></span>
            <OnsetBtn size="small" :toggleable="false" icon="mdi-broom" title="Clear the chat and the agent's memory"
                :active="session.state.entries.length > 0" @click="session.clear()">Clear</OnsetBtn>
        </div>
        <div ref="list" class="agent_chat_list">
            <div v-if="session.state.entries.length == 0" class="message agent_chat_empty">
                Describe how the query should change, e.g.
                <span v-for="example in examples" :key="example" class="chip" @click="send(example)">{{ example }}</span>
            </div>
            <template v-for="entry in session.state.entries" :key="entry.id">
                <div v-if="entry.kind == 'user'" class="agent_chat_msg agent_chat_user">{{ entry.content }}</div>
                <div v-else-if="entry.kind == 'assistant'" class="agent_chat_msg agent_chat_assistant">
                    {{ entry.content }}<span v-if="entry.streaming" class="agent_chat_caret">▍</span>
                </div>
                <ChatThinking v-else-if="entry.kind == 'thinking'" :entry="entry"></ChatThinking>
                <ChatToolCall v-else-if="entry.kind == 'tool'" :call="entry.call"></ChatToolCall>
                <div v-else-if="entry.kind == 'notice'" class="agent_chat_notice"
                    :class="{ agent_chat_notice_error: entry.level == 'error' }">
                    <OnsetIcon :icon="entry.level == 'error' ? 'mdi-alert-circle-outline' : 'mdi-information-outline'" />
                    {{ entry.content }}
                </div>
            </template>
        </div>
        <ChatInput :busy="session.state.busy" :disabled="session.state.status != 'open'" @send="send"
            @cancel="session.cancel()"></ChatInput>
    </div>
</template>
<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import OnsetBtn from '@/components/ui/OnsetBtn.vue'
import OnsetIcon from '@/components/ui/OnsetIcon.vue'
import ChatInput from './ChatInput.vue'
import ChatThinking from './ChatThinking.vue'
import ChatToolCall from './ChatToolCall.vue'
import type { AgentSession } from '@/utils/agent/agentSession'

const { session } = defineProps<{
    session: AgentSession
}>()

const examples = [
    'Add a ship that has a homeport in a country.',
    'Find films directed by a person born in a city.',
]

const list = ref<HTMLElement | null>(null)

const status_text = computed(() => {
    switch (session.state.status) {
        case 'open':
            return 'Connected'
        case 'connecting':
            return 'Connecting…'
        case 'reconnecting':
            return 'Reconnecting…'
        default:
            return 'Offline'
    }
})

const send = (content: string) => {
    session.send(content)
}

// keep the newest message in view while the user is at the bottom of the list
const scrollToBottom = () => {
    const el = list.value
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 80) {
        nextTick(() => el.scrollTo({ top: el.scrollHeight }))
    }
}
watch(() => session.state.entries.map((e) => e.kind == 'assistant' || e.kind == 'thinking' ? e.content.length : e.id), scrollToBottom, { flush: 'pre' })
watch(() => session.state.entries.length, () => nextTick(() => list.value?.scrollTo({ top: list.value.scrollHeight })))
</script>
<style scoped>
.agent_chat {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    height: 100%;
    min-height: 0;
}

.agent_chat_status {
    flex: 0 0 auto;
    font-size: var(--fs-xs);
}

.agent_chat_status_text {
    opacity: 0.8;
}

.agent_chat_dot {
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 50%;
    background: var(--c-disabled);
}

.agent_chat_dot_open {
    background: var(--c-accent);
}

.agent_chat_dot_connecting,
.agent_chat_dot_reconnecting {
    background: #e6b84d;
}

.agent_chat_list {
    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    padding-right: 2px;
}

.agent_chat_empty {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-1);
}

.agent_chat_msg {
    font-size: var(--fs-sm);
    line-height: 1.4;
    white-space: pre-wrap;
    word-break: break-word;
    padding: var(--space-1) var(--space-2);
    border-radius: var(--radius);
}

.agent_chat_user {
    align-self: flex-end;
    max-width: 90%;
    background: var(--c-accent-soft);
    border: 1px solid var(--c-accent);
}

.agent_chat_assistant {
    align-self: flex-start;
    max-width: 100%;
    padding-left: 0;
    padding-right: 0;
}

.agent_chat_caret {
    animation: agent_chat_blink 1s steps(2) infinite;
}

@keyframes agent_chat_blink {
    50% {
        opacity: 0;
    }
}

.agent_chat_notice {
    font-size: var(--fs-xs);
    opacity: 0.8;
}

.agent_chat_notice_error {
    color: #b3261e;
    opacity: 1;
}
</style>
