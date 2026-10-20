<template>
    <!-- Message input: Enter sends, Shift+Enter inserts a newline; Stop cancels a running turn. -->
    <form class="chat_input" @submit.prevent="submit">
        <textarea ref="textarea" v-model="text" class="text_input chat_input_text" rows="1"
            :placeholder="placeholder" :disabled="disabled" @keydown="keydown" @input="resize"></textarea>
        <OnsetBtn v-if="busy" :toggleable="false" icon="mdi-stop" title="Stop the agent" @click="emit('cancel')" />
        <OnsetBtn v-else :toggleable="false" icon="mdi-send" title="Send (Enter)" :active="!disabled && !!text.trim()"
            @click="submit" />
    </form>
</template>
<script setup lang="ts">
import { nextTick, ref } from 'vue'
import OnsetBtn from '@/components/ui/OnsetBtn.vue'

const { busy = false, disabled = false, placeholder = 'Ask the agent to change the query…' } = defineProps<{
    busy?: boolean
    disabled?: boolean
    placeholder?: string
}>()
const emit = defineEmits<{
    send: [content: string]
    cancel: []
}>()

const text = ref('')
const textarea = ref<HTMLTextAreaElement | null>(null)

const resize = () => {
    const el = textarea.value
    if (!el) {
        return
    }
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
}

const submit = () => {
    if (disabled || busy || !text.value.trim()) {
        return
    }
    emit('send', text.value)
    text.value = ''
    nextTick(resize)
}

const keydown = (evt: KeyboardEvent) => {
    if (evt.key == 'Enter' && !evt.shiftKey && !evt.isComposing) {
        evt.preventDefault()
        submit()
    }
}
</script>
<style scoped>
.chat_input {
    display: flex;
    align-items: flex-end;
    gap: var(--space-1);
}

.chat_input_text {
    flex: 1 1 auto;
    height: auto;
    min-height: var(--control-h);
    padding: 0.2rem var(--space-2);
    line-height: 1.35;
    resize: none;
    font-family: inherit;
}
</style>
