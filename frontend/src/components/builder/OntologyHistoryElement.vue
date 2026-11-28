<template>
    <!-- An ontology history entry: who changed it and a miniature of its ontology, with the classes
         and links the change added (green), changed (purple) and removed (red, dashed). -->
    <div class="onto_history_element" @mouseover.capture="hover = true" @mouseleave.capture="hover = false">
        <div class="toolbar onto_history_btns" v-show="hover">
            <OnsetBtn @click="emit('revert', entry)" size="small" :toggleable="false" icon="mdi-undo"
                title="Restore this ontology (the knowledge graph is extracted again)">Restore</OnsetBtn>
        </div>
        <div class="onto_history_corner">
            <HistoryProvenance :provenance="entry.provenance" @show-in-chat="emit('showInChat', $event)" />
            <span class="onto_history_time">{{ new Date(entry.timestamp).toLocaleTimeString() }}</span>
        </div>
        <svg class="fill_svg" :viewBox="view_box" preserveAspectRatio="xMidYMid meet">
            <g v-for="g in links" :key="g.key" :class="g.state && `onto_history_${g.state}`">
                <title>{{ g.title }}</title>
                <path :d="g.d" class="onto_history_link" />
            </g>
            <g v-for="b in boxes" :key="b.key" :class="b.state && `onto_history_${b.state}`">
                <title>{{ b.title }}</title>
                <rect :x="b.x" :y="b.y" :width="b.w" :height="b.h" class="onto_history_class" />
                <text :x="b.x + 8" :y="b.y + 17" class="onto_history_label">{{ b.label }}</text>
            </g>
        </svg>
    </div>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import OnsetBtn from '@/components/ui/OnsetBtn.vue'
import HistoryProvenance from '@/components/explore/history/HistoryProvenance.vue'
import type { OntoClass, OntoLink, Ontology } from '@/utils/builder/api'
import { elementStates, type OntologyHistoryEntry } from '@/utils/builder/history'
import { classRect } from '@/utils/builder/layout'
import { linkGeometry, parallelIndex } from '@/utils/graph-layout'

const props = defineProps<{ entry: OntologyHistoryEntry }>()
const emit = defineEmits<{
    revert: [OntologyHistoryEntry],
    showInChat: [string[]],
}>()
const hover = ref(false)

type State = 'add' | 'change' | 'remove' | null

const drawn = computed(() => {
    const entry = props.entry
    const states = elementStates(entry)
    const onto = entry.ontology
    // removed classes at their place in the previous ontology
    const classes: { onto: Ontology, cls: OntoClass, state: State }[] = [
        ...onto.classes.map((cls) => ({ onto, cls, state: states.cls(cls) as State })),
        ...states.removed_classes.map((cls) => ({ onto: entry.previous!, cls, state: 'remove' as State })),
    ]
    const boxes = classes.map(({ onto, cls, state }) => ({
        key: `${state == 'remove' ? '-' : ''}${cls.id}`, state, label: cls.label || cls.id,
        title: `${cls.label} (${cls.id})${cls.fields.length ? `\n${cls.fields.map((f) => `${f.name}: ${f.type}`).join('\n')}` : ''}`,
        ...classRect(onto, cls),
    }))
    const box = (id: string, removed: boolean) =>
        boxes.find((b) => b.key == `-${id}` && removed) ?? boxes.find((b) => b.key == id)
    const all_links: { link: OntoLink, state: State }[] = [
        ...onto.links.map((link) => ({ link, state: states.link(link) as State })),
        ...states.removed_links.map((link) => ({ link, state: 'remove' as State })),
    ]
    const ends = (l: OntoLink): [string, string] => [l.source, l.target]
    const links = all_links.flatMap(({ link, state }) => {
        const s = box(link.source, state == 'remove'), t = box(link.target, state == 'remove')
        if (!s || !t) {
            return []
        }
        const k = parallelIndex(all_links.map((x) => x.link), link, ends)
        return [{
            key: `${state == 'remove' ? '-' : ''}${link.id}`, state, title: `${s.label} –${link.label || link.id}→ ${t.label}`,
            ...linkGeometry(s, t, k, link.source == link.target),
        }]
    })
    return { boxes, links }
})
const boxes = computed(() => drawn.value.boxes)
const links = computed(() => drawn.value.links)

const view_box = computed(() => {
    const bs = boxes.value
    if (!bs.length) {
        return '0 0 100 40'
    }
    const MARGIN = 40
    const x0 = Math.min(...bs.map((b) => b.x)) - MARGIN, y0 = Math.min(...bs.map((b) => b.y)) - MARGIN
    const x1 = Math.max(...bs.map((b) => b.x + b.w)) + MARGIN, y1 = Math.max(...bs.map((b) => b.y + b.h)) + MARGIN
    return `${x0} ${y0} ${x1 - x0} ${y1 - y0}`
})
</script>
<style scoped>
.onto_history_element {
    position: relative;
    flex: 0 0 auto;
    width: 100%;
    height: 7rem;
    padding: var(--space-1);
    border-bottom: 1px solid var(--c-border);
    cursor: pointer;
}

.onto_history_corner {
    position: absolute;
    top: var(--space-1);
    left: var(--space-1);
    z-index: 1;
    display: flex;
    align-items: center;
    gap: var(--space-1);
}

.onto_history_time {
    font-size: var(--fs-xs);
    opacity: 0.6;
}

.onto_history_btns {
    position: absolute;
    top: var(--space-1);
    right: var(--space-1);
    z-index: 1;
}

.onto_history_class {
    fill: var(--c-surface);
    stroke: var(--c-link-normal);
    stroke-width: 2;
}

.onto_history_label {
    font-size: 16px;
}

.onto_history_link {
    fill: none;
    stroke: var(--c-link-normal);
    stroke-width: 3;
}

.onto_history_add .onto_history_class,
.onto_history_add .onto_history_link {
    stroke: var(--c-link-added);
    stroke-width: 5;
}

.onto_history_change .onto_history_class,
.onto_history_change .onto_history_link {
    stroke: var(--c-constraint);
    stroke-width: 5;
}

.onto_history_remove .onto_history_class,
.onto_history_remove .onto_history_link {
    stroke: var(--c-link-removed);
    stroke-width: 4;
    stroke-dasharray: 10 6;
}

.onto_history_remove {
    opacity: 0.7;
}
</style>
