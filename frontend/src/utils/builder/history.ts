// Edit history of the ontology builder's ontology, the counterpart of the query history
// (utils/sparql/history.ts): one entry per change with a snapshot of the ontology, who made it
// (EditProvenance: the user, the agent with its tool calls, a revert, a load/import) and the
// operations it made. Saved with the builder session on the server (utils/historySync.ts).
//
// The time embedding curve (TimeEmbeddingsOverlay) embeds an entry by a hashed bag of features of
// its ontology: the classes, fields (with their types) and links (with their ends) and the words of
// their names and descriptions, the structural counterpart of the query history's sentence
// embedding of the readable query. The builder sessions have no embedding model.
import type { Vector2 } from 'three'
import { ManifoldAlg } from '@/api/client.ts/Api'
import type { EditOp, EditOpKind, EditProvenance } from '@/utils/sparql/provenance'
import { dimReduceEntries, type SearchableHistory, type TimelineChange, type TimelineEntry } from '@/utils/sparql/timeline'
import type { StoredHistoryEntry } from '@/utils/historySync'
import type { OntoClass, OntoLink, Ontology } from './api'

/** Consecutive edits of the user within this time are one entry (e.g. typing a description). */
export const COALESCE_MS = 2000
/** Entries kept (and saved) per session. */
export const MAX_ENTRIES = 300
const EMBEDDING_DIM = 256

interface IdDiff { added: string[], removed: string[], changed: string[] }

/**
 * The change of an ontology to the next. Class and link ids are those of the newer ontology
 * (removed ones: of the older one), fields are ``<class id>.<field name>``; a renamed class or
 * link (its id follows its name) is changed, with its old id in ``renamed``.
 */
export interface OntologyDiff {
    classes: IdDiff
    fields: IdDiff
    links: IdDiff
    /** new id -> old id of renamed classes, links and fields */
    renamed: Record<string, string>
}

export interface OntologyHistoryEntry extends TimelineEntry {
    ontology: Ontology
    /** the ontology of the previous entry (null for the first) and the change from it */
    previous: Ontology | null
    diff: OntologyDiff | null
    /** last time a coalesced edit changed the entry */
    updated: number
}

/** A finished tool call of the agent, for linking an agent entry to its tool calls in the chat. */
export interface AgentToolCall {
    call_id: string
    name: string
    /** ChatEntry.id of the call in the chat */
    entry_id?: string
}

const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x))

/** The ontology without its layout: moving a class is no history entry. */
export function semanticKey(ontology: Ontology): string {
    return JSON.stringify({
        prefix: ontology.prefix,
        classes: ontology.classes.map(({ x: _x, y: _y, ...rest }) => rest),
        links: ontology.links,
    })
}

const sameJSON = (a: unknown, b: unknown) => JSON.stringify(a) == JSON.stringify(b)

/** Pairs removed and added items that are one renamed item (by ``same``), the rest stays. */
function pairRenames<T>(removed: T[], added: T[], same: (old_item: T, new_item: T) => boolean): [T, T][] {
    const pairs: [T, T][] = []
    const free = [...removed]
    for (const item of added) {
        const i = free.findIndex((old_item) => same(old_item, item))
        if (i >= 0) {
            pairs.push([free[i], item])
            free.splice(i, 1)
        }
    }
    return pairs
}

/** Changes of keyed items: added, removed, changed (by ``sig``) and renamed (by ``same``). */
function diffItems<T>(
    before: T[], after: T[], key: (t: T) => string, sig: (t: T) => unknown, same: (a: T, b: T) => boolean,
) {
    const old_keys = new Map(before.map((t) => [key(t), t]))
    const new_keys = new Set(after.map(key))
    const removed = before.filter((t) => !new_keys.has(key(t)))
    const added = after.filter((t) => !old_keys.has(key(t)))
    const renames = pairRenames(removed, added, same)
    const renamed_old = new Set(renames.map(([a]) => a))
    const renamed_new = new Set(renames.map(([, b]) => b))
    return {
        added: added.filter((t) => !renamed_new.has(t)).map(key),
        removed: removed.filter((t) => !renamed_old.has(t)).map(key),
        changed: [
            ...after.filter((t) => old_keys.has(key(t)) && !sameJSON(sig(old_keys.get(key(t))!), sig(t))).map(key),
            ...renames.map(([, b]) => key(b)),
        ],
        renamed: Object.fromEntries(renames.map(([a, b]) => [key(b), key(a)])),
    }
}

export function diffOntologies(before: Ontology, after: Ontology): OntologyDiff {
    // a class that kept its place or its fields was renamed (its id follows its name)
    const classes = diffItems(before.classes, after.classes, (c) => c.id, (c) => [c.label, c.description],
        (a, b) => (a.x != null && a.y != null && a.x == b.x && a.y == b.y)
            || (a.fields.length > 0 && sameJSON(a.fields, b.fields) && a.description == b.description))
    // links compared with their ends' new ids, so renaming a class does not change its links
    const new_class_id = Object.fromEntries(Object.entries(classes.renamed).map(([n, o]) => [o, n]))
    const ends = (l: OntoLink) => [new_class_id[l.source] ?? l.source, new_class_id[l.target] ?? l.target]
    const links = diffItems(before.links, after.links, (l) => l.id, (l) => [l.label, l.description, ...ends(l)],
        (a, b) => sameJSON(ends(a), [b.source, b.target]) && a.description == b.description)
    // fields of the classes in both ontologies
    const fields: IdDiff = { added: [], removed: [], changed: [] }
    const renamed: Record<string, string> = { ...classes.renamed, ...links.renamed }
    for (const cls of after.classes) {
        const old_cls = before.classes.find((c) => c.id == (classes.renamed[cls.id] ?? cls.id))
        if (!old_cls) {
            continue
        }
        const d = diffItems(old_cls.fields, cls.fields, (f) => f.name, (f) => [f.type, f.description],
            (a, b) => a.type == b.type && a.description == b.description)
        const qualify = (name: string) => `${cls.id}.${name}`
        fields.added.push(...d.added.map(qualify))
        fields.removed.push(...d.removed.map(qualify))
        fields.changed.push(...d.changed.map(qualify))
        for (const [n, o] of Object.entries(d.renamed)) {
            renamed[qualify(n)] = qualify(o)
        }
    }
    return { classes, fields, links, renamed }
}

export function isEmptyDiff(diff: OntologyDiff): boolean {
    return [diff.classes, diff.fields, diff.links].every((d) => !d.added.length && !d.removed.length && !d.changed.length)
}

/** The operations of a change, labelled with the names of the elements. */
export function diffOps(before: Ontology, after: Ontology, diff: OntologyDiff): EditOp[] {
    const label = (onto: Ontology, id: string) => onto.classes.find((c) => c.id == id)?.label ?? id
    const link_label = (onto: Ontology, id: string) => {
        const l = onto.links.find((x) => x.id == id)
        return l ? `${label(onto, l.source)} –${l.label || l.id}→ ${label(onto, l.target)}` : id
    }
    // field keys have the class id of the newer ontology
    const field_label = (key: string) => {
        const [cls, name] = key.split('.', 2)
        return `${after.classes.find((c) => c.id == cls)?.label ?? label(before, cls)}.${name}`
    }
    const renamed = (old_label: string, new_label: string) =>
        old_label == new_label ? new_label : `${old_label} → ${new_label}`
    const ops = (kind: EditOpKind, labels: string[]) => labels.map((l) => ({ kind, label: l }))
    const { classes, fields, links } = diff
    return [
        ...ops('remove_link', links.removed.map((id) => link_label(before, id))),
        ...ops('remove_field', fields.removed.map(field_label)),
        ...ops('remove_class', classes.removed.map((id) => label(before, id))),
        ...ops('add_class', classes.added.map((id) => label(after, id))),
        ...ops('change_class', classes.changed.map((id) =>
            renamed(label(before, diff.renamed[id] ?? id), label(after, id)))),
        ...ops('add_field', fields.added.map(field_label)),
        ...ops('change_field', fields.changed.map((k) => diff.renamed[k]
            ? `${field_label(diff.renamed[k])} → ${k.split('.')[1]}` : field_label(k))),
        ...ops('add_link', links.added.map((id) => link_label(after, id))),
        ...ops('change_link', links.changed.map((id) => link_label(after, id))),
    ]
}

/** FNV-1a hash of a string. */
function hash(s: string): number {
    let h = 0x811c9dc5
    for (let i = 0; i < s.length; i++) {
        h ^= s.charCodeAt(i)
        h = Math.imul(h, 0x01000193)
    }
    return h >>> 0
}

/** Lower-case words of a name or text, camel case split ("birthDate" -> birth, date). */
function words(text: string | null | undefined): string[] {
    return (text ?? '').replace(/([a-z0-9])([A-Z])/g, '$1 $2').toLowerCase().split(/[^a-z0-9]+/).filter((w) => w.length > 1)
}

/** Weighted features of an ontology (see the top of the file). */
function ontologyFeatures(ontology: Ontology): [string, number][] {
    const features: [string, number][] = [['ontology', 0.1]]
    const text = (t: string | null | undefined, weight: number) => words(t).forEach((w) => features.push([`w:${w}`, weight]))
    for (const cls of ontology.classes) {
        features.push([`c:${cls.id}`, 1])
        text(cls.label, 0.5)
        text(cls.description, 0.15)
        for (const f of cls.fields) {
            features.push([`f:${cls.id}.${f.name}`, 1], [`t:${cls.id}.${f.name}:${f.type}`, 0.5])
            text(f.name, 0.5)
            text(f.description, 0.15)
        }
    }
    for (const l of ontology.links) {
        features.push([`l:${l.source}>${l.id}>${l.target}`, 1], [`p:${l.id}`, 0.5])
        text(l.label, 0.5)
        text(l.description, 0.15)
    }
    return features
}

/** Normalised hashed feature vector (signed hashing). */
function hashedEmbedding(features: [string, number][]): number[] {
    const v = new Array<number>(EMBEDDING_DIM).fill(0)
    for (const [feature, weight] of features) {
        const h = hash(feature)
        v[h % EMBEDDING_DIM] += (h & 0x80000000 ? -1 : 1) * weight
    }
    const norm = Math.hypot(...v) || 1
    return v.map((x) => x / norm)
}

export function ontologyEmbedding(ontology: Ontology): number[] {
    return hashedEmbedding(ontologyFeatures(ontology))
}

/** Annotates the ops of an agent edit with the tool calls that (by their tool name) made them. */
function attributeOps(ops: EditOp[], calls: AgentToolCall[]): EditOp[] {
    const free = [...calls]
    return ops.map((op) => {
        const i = free.findIndex((c) => c.name == op.kind)
        if (i < 0) {
            return op
        }
        const [call] = free.splice(i, 1)
        return { ...op, call_id: call.call_id, tool: call.name, chat_entry_id: call.entry_id }
    })
}

export class OntologyHistory implements SearchableHistory<OntologyHistoryEntry> {
    entries: OntologyHistoryEntry[] = []

    constructor(entries: OntologyHistoryEntry[] = []) {
        this.entries = entries
    }

    get length(): number { return this.entries.length }
    get reverse_entries(): OntologyHistoryEntry[] { return [...this.entries].reverse() }
    get last(): OntologyHistoryEntry | undefined { return this.entries[this.entries.length - 1] }

    /**
     * Adds an entry for ``ontology`` if it differs (not only in its layout) from the last one.
     * ``provenance``: who changed it (its ops are computed from the change); ``calls``: the agent's
     * tool calls of the change. A user edit shortly after another user edit replaces that entry.
     * A change of the layout only goes into the last entry. Returns the added or updated entry.
     */
    record(ontology: Ontology, provenance: Omit<EditProvenance, 'ops'>, calls: AgentToolCall[] = [],
        now = Date.now()): OntologyHistoryEntry | null {
        const last = this.last
        if (last && semanticKey(last.ontology) == semanticKey(ontology)) {
            last.ontology = clone(ontology)
            return null
        }
        const coalesce = !!last && this.entries.length > 1 && provenance.source == 'user'
            && last.provenance.source == 'user' && now - last.updated < COALESCE_MS
        if (coalesce) {
            this.entries.pop()
            const before = this.last!
            if (semanticKey(before.ontology) == semanticKey(ontology)) {
                // the edits undid themselves
                before.ontology = clone(ontology)
                return null
            }
        }
        const previous = this.last?.ontology ?? null
        const diff = previous ? diffOntologies(previous, ontology) : null
        let ops = previous && diff ? diffOps(previous, ontology, diff) : []
        if (provenance.source == 'agent') {
            ops = attributeOps(ops, calls)
        }
        const entry: OntologyHistoryEntry = {
            ontology: clone(ontology),
            previous: previous ? clone(previous) : null,
            diff,
            // the timestamp identifies the entry in the saved history: unique
            timestamp: coalesce ? last!.timestamp : Math.max(now, (this.last?.timestamp ?? 0) + 1),
            updated: now,
            provenance: {
                ...clone(provenance),
                ops,
                ...(provenance.source == 'agent'
                    ? { chat_entry_ids: [...new Set(calls.map((c) => c.entry_id).filter((id): id is string => !!id))] }
                    : {}),
            },
            embedding: ontologyEmbedding(ontology),
        }
        this.entries.push(entry)
        if (this.entries.length > MAX_ENTRIES) {
            this.entries.splice(0, this.entries.length - MAX_ENTRIES)
            this.entries[0].previous = null
            this.entries[0].diff = null
        }
        return entry
    }

    async dimReduceEmbeddings(n_out: number = 2, alg: ManifoldAlg = ManifoldAlg.TSNE): Promise<{ v: Vector2, entry: OntologyHistoryEntry }[]> {
        return dimReduceEntries(this.entries, n_out, alg)
    }

    entrySize(entry: OntologyHistoryEntry): number {
        return entry.ontology.classes.length
    }

    entryChange(entry: OntologyHistoryEntry): TimelineChange | null {
        const diff = entry.diff
        if (!diff) {
            return null
        }
        const parts = [diff.classes, diff.fields, diff.links]
        return {
            size: parts.reduce((n, d) => n + d.added.length + d.removed.length + d.changed.length, 0) || 1,
            added: parts.some((d) => d.added.length > 0),
            changed: parts.some((d) => d.changed.length > 0),
        }
    }

    /** Entries by the words of the query in their ontology (hashed features as the embedding). */
    async searchSimilarEntries(query: string, n_results: number = 5): Promise<{ entry: OntologyHistoryEntry, distance: number }[]> {
        const q = hashedEmbedding(words(query).map((w) => [`w:${w}`, 1]))
        return this.entries
            .map((entry) => ({ entry, score: entry.embedding?.reduce((s, x, i) => s + x * q[i], 0) ?? 0 }))
            .filter((r) => r.score > 0)
            .sort((a, b) => b.score - a.score)
            .slice(0, n_results)
            .map((r) => ({ entry: r.entry, distance: 1 - r.score }))
    }

    /** The entries without their embeddings and previous ontologies (recomputed on load), to save. */
    toStored(): StoredHistoryEntry<OntologyHistoryEntry>[] {
        return this.entries.map((e) => ({ timestamp: e.timestamp, entry: { ...e, embedding: null, previous: null } }))
    }

    static fromStored(stored: StoredHistoryEntry[]): OntologyHistory {
        const entries = stored.map((s) => s.entry as OntologyHistoryEntry)
        entries.forEach((e, i) => {
            e.embedding = ontologyEmbedding(e.ontology)
            e.previous = e.diff && i > 0 ? entries[i - 1].ontology : null
        })
        return new OntologyHistory(entries)
    }

    /** A history kept in the browser before the sessions saved it (null if there is none). */
    static parseLegacy(json: string | null): OntologyHistory | null {
        if (!json) {
            return null
        }
        try {
            const entries = JSON.parse(json) as OntologyHistoryEntry[]
            return OntologyHistory.fromStored(entries.map((entry) => ({ timestamp: entry.timestamp, entry })))
        } catch (e) {
            console.warn('Ignoring the stored ontology history', e)
            return null
        }
    }
}

/** Elements of an ontology by their state in a history entry, for the miniatures. */
export function elementStates(entry: OntologyHistoryEntry) {
    const d = entry.diff
    const state = (diff: IdDiff | undefined, id: string) =>
        diff?.added.includes(id) ? 'add' : diff?.changed.includes(id) ? 'change' : null
    return {
        cls: (c: OntoClass) => state(d?.classes, c.id) ?? (d?.fields.added.some((k) => k.startsWith(`${c.id}.`))
            || d?.fields.changed.some((k) => k.startsWith(`${c.id}.`))
            || d?.fields.removed.some((k) => k.startsWith(`${c.id}.`)) ? 'change' : null),
        link: (l: OntoLink) => state(d?.links, l.id),
        /** classes and links of the previous ontology that the change removed */
        removed_classes: entry.previous?.classes.filter((c) => d?.classes.removed.includes(c.id)) ?? [],
        removed_links: entry.previous?.links.filter((l) => d?.links.removed.includes(l.id)) ?? [],
    }
}
