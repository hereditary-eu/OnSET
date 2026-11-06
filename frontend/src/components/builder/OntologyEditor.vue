<template>
    <!-- Graph editor of a builder ontology: classes are cards listing their fields, links are labelled arrows.
         Edits mutate the ontology model in place; the builder view syncs it to the backend. -->
    <div class="onto_editor" :class="{ onto_editor_linking: linking }" @keydown.esc="linking = null" tabindex="-1">
        <div class="onto_scroll">
        <div class="onto_canvas" :style="{ width: `${extent.x}px`, height: `${extent.y}px` }"
            @pointerdown.self="selected = null">
            <svg class="onto_links" :width="extent.x" :height="extent.y">
                <defs>
                    <marker id="onto_arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8"
                        orient="auto-start-reverse">
                        <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--c-link-normal)" />
                    </marker>
                </defs>
                <g v-for="g in link_geometry" :key="g.link.id" class="onto_link"
                    :class="{ onto_link_selected: isSelected('link', g.link.id) }" @click="select('link', g.link.id)">
                    <path :d="g.d" class="onto_link_hit" />
                    <path :d="g.d" class="link_path" marker-end="url(#onto_arrow)" />
                    <text :x="g.label.x" :y="g.label.y - 4" class="link_text">{{ g.link.label }}</text>
                </g>
            </svg>
            <div v-for="cls in ontology.classes" :key="cls.id" class="onto_card"
                :class="{ onto_card_selected: isSelected('class', cls.id) }"
                :style="{ left: `${pos(cls).x}px`, top: `${pos(cls).y}px`, width: `${CARD_W}px` }"
                @pointerdown="clickCard(cls)">
                <div class="onto_card_header" @pointerdown="dragStart($event, cls)" :title="cls.description">
                    <span class="onto_card_title">{{ cls.label }}</span>
                    <button type="button" title="Query the instances of this class" @pointerdown.stop
                        @click="emit('query', cls.id)"><OnsetIcon icon="mdi-table-search" /></button>
                    <button type="button" title="Add a link from this class (then click the target class)"
                        @pointerdown.stop @click="linking = cls.id"><OnsetIcon icon="mdi-arrow-right-top" /></button>
                    <button type="button" title="Delete the class" @pointerdown.stop
                        @click="removeClass(cls)"><OnsetIcon icon="mdi-close" /></button>
                </div>
                <div v-for="f in cls.fields" :key="f.name" class="onto_card_row" :title="f.description">
                    <span>{{ f.name }}</span><span class="onto_card_type">{{ f.type }}</span>
                </div>
                <div v-if="cls.fields.length == 0" class="onto_card_row onto_card_type">no fields</div>
            </div>
        </div>
        </div>

        <!-- add a class / link mode hint -->
        <form class="toolbar onto_overlay onto_add" @submit.prevent="addClass">
            <template v-if="linking">
                <span class="message">Click the target class of the new link from {{ classOf(linking)?.label }}</span>
                <OnsetBtn size="small" :toggleable="false" icon="mdi-close" @click="linking = null">Cancel</OnsetBtn>
            </template>
            <template v-else>
                <input v-model="new_class" class="text_input" placeholder="New class, e.g. Person" />
                <OnsetBtn size="small" :toggleable="false" icon="mdi-plus" :active="!!toId(new_class)"
                    @click="addClass">Class</OnsetBtn>
            </template>
        </form>
        <p v-if="ontology.classes.length == 0" class="message onto_empty">
            The ontology is empty. Add a class above, import an ontology, or ask the agent to propose one.
        </p>

        <!-- inspector of the selected class or link -->
        <div v-if="selected_class" class="onto_overlay onto_inspector">
            <div class="onto_inspector_title">Class <code>{{ selected_class.id }}</code></div>
            <label>Name<input class="text_input" :value="drafts[`class:${selected_class.id}`] ?? selected_class.label"
                    @input="draft(`class:${selected_class.id}`, $event)"
                    @change="commit(`class:${selected_class.id}`, $event, (v) => renameClass(selected_class!, v))" /></label>
            <label>Description<textarea class="text_input" rows="2" v-model="selected_class.description" /></label>
            <div class="onto_inspector_title">Fields</div>
            <div v-for="f in selected_class.fields" :key="f.name" class="onto_field">
                <div class="toolbar">
                    <input class="text_input" :value="drafts[`field:${selected_class.id}:${f.name}`] ?? f.name"
                        @input="draft(`field:${selected_class.id}:${f.name}`, $event)"
                        @change="commit(`field:${selected_class.id}:${f.name}`, $event, (v) => renameField(selected_class!, f, v))" />
                    <select class="text_input" v-model="f.type">
                        <option v-for="t in FIELD_TYPES" :key="t" :value="t">{{ t }}</option>
                    </select>
                    <OnsetBtn size="small" :toggleable="false" icon="mdi-close" title="Remove the field"
                        @click="selected_class.fields.splice(selected_class.fields.indexOf(f), 1)" />
                </div>
                <label class="text_input onto_field_desc">
                    <span>Description</span>
                    <input v-model="f.description" placeholder="what the field holds" />
                </label>
            </div>
            <form class="toolbar" @submit.prevent="addField(selected_class)">
                <input class="text_input" v-model="new_field.name" placeholder="New field, e.g. birth date" />
                <select class="text_input" v-model="new_field.type">
                    <option v-for="t in FIELD_TYPES" :key="t" :value="t">{{ t }}</option>
                </select>
                <OnsetBtn size="small" :toggleable="false" icon="mdi-plus" title="Add the field"
                    :active="!!toId(new_field.name)" @click="addField(selected_class)" />
            </form>
        </div>
        <div v-else-if="selected_link" class="onto_overlay onto_inspector">
            <div class="onto_inspector_title">Link <code>{{ selected_link.id }}</code></div>
            <label>Name<input class="text_input" :value="drafts[`link:${selected_link.id}`] ?? selected_link.label"
                    @input="draft(`link:${selected_link.id}`, $event)"
                    @change="commit(`link:${selected_link.id}`, $event, (v) => renameLink(selected_link!, v))" /></label>
            <label>From<select class="text_input" v-model="selected_link.source">
                    <option v-for="c in ontology.classes" :key="c.id" :value="c.id">{{ c.label }}</option>
                </select></label>
            <label>To<select class="text_input" v-model="selected_link.target">
                    <option v-for="c in ontology.classes" :key="c.id" :value="c.id">{{ c.label }}</option>
                </select></label>
            <label>Description<textarea class="text_input" rows="2" v-model="selected_link.description" /></label>
            <OnsetBtn size="small" :toggleable="false" icon="mdi-delete-outline"
                @click="ontology.links.splice(ontology.links.indexOf(selected_link), 1)">Delete link</OnsetBtn>
        </div>
    </div>
</template>
<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import OnsetBtn from '@/components/ui/OnsetBtn.vue'
import OnsetIcon from '@/components/ui/OnsetIcon.vue'
import { FIELD_TYPES, toId, uniqueId, type FieldType, type OntoClass, type OntoField, type OntoLink, type Ontology } from '@/utils/builder/api'
import { linkGeometry, parallelIndex, pointerDrag } from '@/utils/graph-layout'

const CARD_W = 190
// must match the card CSS below (header, rows, padding)
const HEADER_H = 24
const ROW_H = 18
const PAD = 4

const ontology = defineModel<Ontology>({ required: true })
const emit = defineEmits<{ query: [class_id: string] }>()

const selected = ref(null as { kind: 'class' | 'link', id: string } | null)
const linking = ref(null as string | null)
const new_class = ref('')
const new_field = reactive({ name: '', type: 'string' as FieldType })

// uncommitted text of the rename inputs (committed on change); kept here so a re-render from a
// server update does not reset what is being typed
const drafts = reactive<Record<string, string>>({})
const inputValue = (e: Event) => (e.target as HTMLInputElement).value
const draft = (key: string, e: Event) => drafts[key] = inputValue(e)
const commit = (key: string, e: Event, apply: (value: string) => void) => {
    delete drafts[key]
    apply(inputValue(e))
}

const classOf = (id: string) => ontology.value.classes.find((c) => c.id == id)
const isSelected = (kind: 'class' | 'link', id: string) => selected.value?.kind == kind && selected.value.id == id
const select = (kind: 'class' | 'link', id: string) => selected.value = { kind, id }
const selected_class = computed(() => selected.value?.kind == 'class' ? classOf(selected.value.id) : undefined)
const selected_link = computed(() => selected.value?.kind == 'link'
    ? ontology.value.links.find((l) => l.id == selected.value!.id) : undefined)

// classes without a position (e.g. added by the agent) are laid out on a grid
const gridPos = (i: number) => ({ x: 20 + (i % 3) * (CARD_W + 120), y: 60 + Math.floor(i / 3) * 170 })
const pos = (cls: OntoClass) => cls.x != null && cls.y != null ? { x: cls.x, y: cls.y }
    : gridPos(ontology.value.classes.indexOf(cls))
const rect = (cls: OntoClass) => ({ ...pos(cls), w: CARD_W, h: HEADER_H + Math.max(1, cls.fields.length) * ROW_H + PAD })

const extent = computed(() => ontology.value.classes.map(rect).reduce(
    (e, r) => ({ x: Math.max(e.x, r.x + r.w + 60), y: Math.max(e.y, r.y + r.h + 60) }), { x: 0, y: 0 }))

// links between the facing sides of the two cards; parallel links bend apart
const link_geometry = computed(() => {
    const ends = (l: OntoLink): [string, string] => [l.source, l.target]
    return ontology.value.links.flatMap((link) => {
        const s = classOf(link.source), t = classOf(link.target)
        if (!s || !t) {
            return []
        }
        const k = parallelIndex(ontology.value.links, link, ends)
        return [{ link, ...linkGeometry(rect(s), rect(t), k, s == t) }]
    })
})

const addClass = () => {
    const label = new_class.value.trim()
    const id = toId(label, true)
    if (!id) {
        return
    }
    const classes = ontology.value.classes
    classes.push({
        id: uniqueId(id, classes.map((c) => c.id)), label, description: '', fields: [],
        ...gridPos(classes.length),
    })
    new_class.value = ''
    select('class', classes[classes.length - 1].id)
}

const removeClass = (cls: OntoClass) => {
    const onto = ontology.value
    onto.links = onto.links.filter((l) => l.source != cls.id && l.target != cls.id)
    onto.classes.splice(onto.classes.indexOf(cls), 1)
}

const renameClass = (cls: OntoClass, label: string) => {
    const id = toId(label, true)
    if (!id) {
        return
    }
    const new_id = id == cls.id ? id : uniqueId(id, ontology.value.classes.map((c) => c.id))
    for (const link of ontology.value.links) {
        link.source = link.source == cls.id ? new_id : link.source
        link.target = link.target == cls.id ? new_id : link.target
    }
    cls.label = label.trim()
    cls.id = new_id
    select('class', new_id)
}

const addField = (cls: OntoClass) => {
    const id = toId(new_field.name)
    if (!id) {
        return
    }
    cls.fields.push({ name: uniqueId(id, cls.fields.map((f) => f.name)), type: new_field.type, description: '' })
    new_field.name = ''
}

const renameField = (cls: OntoClass, field: OntoField, name: string) => {
    const id = toId(name)
    if (id && id != field.name) {
        field.name = uniqueId(id, cls.fields.map((f) => f.name))
    }
}

const renameLink = (link: OntoLink, label: string) => {
    const id = toId(label)
    if (!id) {
        return
    }
    link.label = label.trim()
    if (id != link.id) {
        link.id = uniqueId(id, ontology.value.links.map((l) => l.id))
    }
    select('link', link.id)
}

// link mode: the next clicked card is the target
const clickCard = (cls: OntoClass) => {
    if (!linking.value) {
        select('class', cls.id)
        return
    }
    const source = classOf(linking.value)!
    linking.value = null
    const label = `has ${cls.label}`
    const links = ontology.value.links
    links.push({ id: uniqueId(toId(label), links.map((l) => l.id)), label, source: source.id, target: cls.id, description: '' })
    select('link', links[links.length - 1].id)
}

// drag a card by its header; the position is stored in the class
const dragStart = (evt: PointerEvent, cls: OntoClass) => {
    if (linking.value) {
        return
    }
    pointerDrag(evt, pos(cls), (x, y) => {
        cls.x = Math.max(0, Math.round(x))
        cls.y = Math.max(0, Math.round(y))
    })
}
</script>
<style scoped>
.onto_editor {
    position: relative;
    width: 100%;
    height: 100%;
    overflow: hidden;
    outline: none;
}

.onto_scroll {
    position: absolute;
    inset: 0;
    overflow: auto;
}

.onto_canvas {
    position: relative;
    min-width: 100%;
    min-height: 100%;
}

.onto_links {
    position: absolute;
    left: 0;
    top: 0;
    overflow: visible;
}

.onto_link {
    cursor: pointer;
}

.onto_link_hit {
    fill: none;
    stroke: transparent;
    stroke-width: 10px;
}

.onto_link text {
    paint-order: stroke;
    stroke: var(--c-surface);
    stroke-width: 3px;
}

.onto_link_selected .link_path {
    stroke: var(--c-accent);
    stroke-width: 2px;
}

.onto_card {
    position: absolute;
    background: var(--c-surface);
    border: 1px solid #000;
    border-radius: var(--radius);
    font-size: var(--fs-xs);
    padding-bottom: 4px;
    box-sizing: border-box;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
}

.onto_card_selected {
    outline: 2px solid var(--c-accent);
}

.onto_editor_linking .onto_card {
    cursor: crosshair;
}

.onto_card_header {
    display: flex;
    align-items: center;
    gap: 2px;
    height: 24px;
    box-sizing: border-box;
    padding: 0 2px 0 var(--space-1);
    background: var(--c-node-normal);
    border-bottom: 1px solid #000;
    cursor: grab;
    touch-action: none;
}

.onto_card_title {
    flex: 1 1 auto;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 600;
    font-size: var(--fs-sm);
}

.onto_card_header button {
    border: none;
    background: none;
    padding: 0 1px;
    cursor: pointer;
    opacity: 0.6;
}

.onto_card_header button:hover {
    opacity: 1;
}

.onto_card_row {
    display: flex;
    justify-content: space-between;
    gap: var(--space-1);
    height: 18px;
    line-height: 18px;
    padding: 0 var(--space-1);
    white-space: nowrap;
    overflow: hidden;
}

.onto_card_type {
    opacity: 0.6;
}

.onto_overlay {
    position: absolute;
    z-index: 5;
    background: var(--c-surface);
    border: 1px solid var(--c-border);
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
    padding: var(--space-1);
}

.onto_add {
    top: var(--space-1);
    left: var(--space-1);
}

.onto_add .text_input {
    width: 13rem;
}

.onto_empty {
    position: absolute;
    top: 3rem;
    left: var(--space-2);
}

.onto_inspector {
    top: var(--space-1);
    right: var(--space-1);
    width: 17rem;
    max-height: calc(100% - 2 * var(--space-1));
    overflow: auto;
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    font-size: var(--fs-xs);
    box-sizing: border-box;
}

.onto_inspector label {
    display: flex;
    flex-direction: column;
    gap: 2px;
}

.onto_inspector textarea {
    height: auto;
    padding: var(--space-1) var(--space-2);
    resize: vertical;
}

.onto_inspector_title {
    font-weight: 600;
    margin-top: var(--space-1);
}

.onto_field {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding-bottom: var(--space-1);
    border-bottom: 1px solid var(--c-hover);
}

.onto_field .toolbar .text_input,
.onto_inspector form .text_input {
    flex: 1 1 auto;
    width: 0;
}

/* description box of a field: the label sits inside the box, above the input */
.onto_inspector label.onto_field_desc {
    height: auto;
    gap: 0;
    padding: 2px var(--space-2);
    cursor: text;
}

.onto_field_desc span {
    font-size: 0.7rem;
    opacity: 0.75;
}

.onto_field_desc input {
    width: 100%;
    border: none;
    outline: none;
    padding: 0;
    font: inherit;
    font-size: var(--fs-sm);
    background: transparent;
    color: inherit;
}

.onto_field_desc:focus-within {
    outline: 1px solid var(--c-accent);
}

.onto_field .toolbar select,
.onto_inspector form select {
    flex: 0 0 5rem;
}
</style>
