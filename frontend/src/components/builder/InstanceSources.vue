<template>
    <!-- Provenance of an instance of the KG: the documents it was extracted from (all of them for a merged
         instance); a document opens with the instance's names marked. Teleported, so it stays above an
         expanded result. -->
    <Teleport to="body">
        <aside v-if="iri" class="panel instance_sources">
            <header class="panel_header">
                <OnsetIcon icon="mdi-file-document-multiple-outline" />
                <span class="panel_title instance_sources_title" :title="iri">{{ provenance?.label ?? localName(iri) }}</span>
                <span class="toolbar_spacer"></span>
                <OnsetBtn size="small" :toggleable="false" icon="mdi-refresh" title="Reload (the KG is still growing)" @click="load" />
                <OnsetBtn size="small" :toggleable="false" icon="mdi-close" @click="iri = null" />
            </header>
            <div class="panel_body instance_sources_body">
                <p v-if="provenance?.aliases.length" class="message">Also extracted as {{ provenance.aliases.join(', ') }}</p>
                <p v-if="loading" class="message"><OnsetIcon icon="mdi-loading mdi-spin" /> Loading…</p>
                <p v-else-if="error" class="message instance_sources_error">{{ error }}</p>
                <template v-else-if="provenance">
                    <p class="message">
                        {{ provenance.documents.length ? `Extracted from ${provenance.documents.length} document${provenance.documents.length == 1 ? '' : 's'}:` : 'No source documents recorded.' }}
                    </p>
                    <button v-for="d in provenance.documents" :key="d.iri" type="button" class="instance_sources_doc"
                        :disabled="!d.doc_id" :title="d.doc_id ?? `${d.iri} (not in this corpus)`" @click="open(d.doc_id)">
                        <span class="instance_sources_doc_title">{{ d.title }}</span>
                        <span class="instance_sources_doc_id">{{ d.doc_id ?? d.iri }}</span>
                    </button>
                </template>
            </div>
        </aside>
        <DocumentViewer v-if="doc" :doc="doc" :terms="names" @close="doc = null" />
    </Teleport>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import OnsetBtn from '@/components/ui/OnsetBtn.vue'
import OnsetIcon from '@/components/ui/OnsetIcon.vue'
import DocumentViewer from '@/components/builder/DocumentViewer.vue'
import { getDocument, type BuilderDocument, type BuilderSessionApi, type InstanceProvenance } from '@/utils/builder/api'

const { builderId, sessionApi } = defineProps<{ builderId: string, sessionApi: BuilderSessionApi }>()
// the inspected instance, null: closed
const iri = defineModel<string | null>('iri', { default: null })

const provenance = ref<InstanceProvenance | null>(null)
const loading = ref(false)
const error = ref('')
const doc = ref<BuilderDocument | null>(null)
const names = computed(() => provenance.value ? [provenance.value.label ?? '', ...provenance.value.aliases] : [])

const localName = (value: string) => value.split(/[/#]/).pop() || value

let request = 0
const load = async () => {
    const current = ++request
    if (!iri.value) {
        provenance.value = null
        return
    }
    loading.value = true
    error.value = ''
    try {
        const out = await sessionApi.provenance(iri.value)
        if (current == request) {
            provenance.value = out
        }
    } catch (e) {
        if (current == request) {
            error.value = `Could not load the sources: ${e}`
        }
    } finally {
        if (current == request) {
            loading.value = false
        }
    }
}
watch(iri, () => {
    provenance.value = null
    load()
}, { immediate: true })

const open = async (doc_id: string | null) => {
    if (!doc_id) {
        return
    }
    try {
        doc.value = await getDocument(builderId, doc_id)
    } catch (e) {
        error.value = `Could not open the document: ${e}`
    }
}
</script>
<style scoped>
.instance_sources {
    position: fixed;
    top: 4rem;
    right: var(--space-3);
    z-index: 250;
    width: min(22rem, calc(100vw - 2 * var(--space-3)));
    max-height: calc(100vh - 6rem);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
}

.instance_sources_title {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.instance_sources_body {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    padding: var(--space-1) var(--space-2);
}

.instance_sources_error {
    color: #b3261e;
}

.instance_sources_doc {
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

.instance_sources_doc:hover:not(:disabled) {
    border-color: var(--c-accent);
    background: var(--c-hover);
}

.instance_sources_doc:disabled {
    cursor: default;
    opacity: 0.6;
}

.instance_sources_doc_title {
    font-weight: 600;
    color: var(--c-accent);
    text-decoration: underline;
}

.instance_sources_doc_id {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    opacity: 0.7;
}
</style>
