// Provenance of query history entries: who changed the query graph (the user, the agent, the
// progressive panel, a revert) and, for the agent, which operations its tool calls made.
// HistoryEntry (history.ts) keeps one EditProvenance; it is a plain object, so it survives
// stringifyJSON/parseJSON with the entry. The history views draw the icons below.
import type { AgentLink, GraphChange, SubQueryChange, ToolCallMessage } from '@/utils/agent/protocol'

export type EditSource = 'user' | 'agent' | 'progressive' | 'revert'

export type EditOpKind =
    | 'add_subject' | 'remove_subject'
    | 'add_link' | 'remove_link'
    | 'add_property' | 'remove_property'
    | 'add_filter' | 'remove_filter'
    | 'add_instance' | 'remove_instance'
    | 'add_sort' | 'remove_sort'
    | 'add_group' | 'remove_group'
    | 'add_aggregate' | 'remove_aggregate'
    | 'other'

/** One operation of an edit, e.g. a subject the agent added. */
export interface EditOp {
    kind: EditOpKind
    /** label of the element (subject/link label, property of a constraint) */
    label: string
    /** tool call that made the change (agent only) */
    call_id?: string
    tool?: string
    /** id of the tool call's chat entry (ChatEntry.id), for linking back to the chat */
    chat_entry_id?: string
}

export interface EditProvenance {
    source: EditSource
    ops: EditOp[]
    /** chat entry ids of the tool calls of this edit (agent only; valid in this browser session) */
    chat_entry_ids?: string[]
    /** revert: timestamp of the entry reverted to, and its provenance */
    reverted_to?: number
    reverted_from?: EditProvenance
}

/** A tool call whose graph change is part of an agent edit, with its chat entry. */
export interface AgentCallRef {
    call: ToolCallMessage
    entry_id: string
}

export interface OpStyle {
    icon: string
    label: string
    /** 'add' | 'remove' | 'change', for colouring */
    direction: 'add' | 'remove' | 'change'
}

export const OP_STYLES: Record<EditOpKind, OpStyle> = {
    add_subject: { icon: 'mdi-plus-circle-outline', label: 'Added subject', direction: 'add' },
    remove_subject: { icon: 'mdi-minus-circle-outline', label: 'Removed subject', direction: 'remove' },
    add_link: { icon: 'mdi-link-variant-plus', label: 'Added link', direction: 'add' },
    remove_link: { icon: 'mdi-link-variant-minus', label: 'Removed link', direction: 'remove' },
    add_property: { icon: 'mdi-table-column-plus-after', label: 'Added property', direction: 'add' },
    remove_property: { icon: 'mdi-table-column-remove', label: 'Removed property', direction: 'remove' },
    add_filter: { icon: 'mdi-filter-plus-outline', label: 'Added filter', direction: 'add' },
    remove_filter: { icon: 'mdi-filter-remove-outline', label: 'Removed filter', direction: 'remove' },
    add_instance: { icon: 'mdi-crosshairs-gps', label: 'Restricted to instance', direction: 'add' },
    remove_instance: { icon: 'mdi-crosshairs-off', label: 'Removed instance restriction', direction: 'remove' },
    add_sort: { icon: 'mdi-sort-variant', label: 'Added similarity sort', direction: 'add' },
    remove_sort: { icon: 'mdi-sort-variant-remove', label: 'Removed similarity sort', direction: 'remove' },
    add_group: { icon: 'mdi-group', label: 'Added grouping', direction: 'add' },
    remove_group: { icon: 'mdi-ungroup', label: 'Removed grouping', direction: 'remove' },
    add_aggregate: { icon: 'mdi-sigma', label: 'Added aggregate', direction: 'add' },
    remove_aggregate: { icon: 'mdi-sigma', label: 'Removed aggregate', direction: 'remove' },
    other: { icon: 'mdi-pencil-outline', label: 'Changed query', direction: 'change' },
}

export const SOURCE_STYLES: Record<EditSource, { icon: string, label: string }> = {
    user: { icon: 'mdi-account-outline', label: 'Edited by you' },
    agent: { icon: 'mdi-robot-outline', label: 'Edited by the agent' },
    progressive: { icon: 'mdi-chart-histogram', label: 'Applied from progressive discovery' },
    revert: { icon: 'mdi-backup-restore', label: 'Reverted' },
}

export function userProvenance(): EditProvenance {
    return { source: 'user', ops: [] }
}

/** Kind of a subquery (constraint) by its QueryGraph type. */
function subQueryOpKind(change: SubQueryChange): EditOpKind {
    const add = change.operation == 'add'
    const type = String((change.subquery as { type?: string }).type ?? '')
    switch (type) {
        case 'query_prop':
        case 'image_prop':
            return add ? 'add_property' : 'remove_property'
        case 'instance_prop':
        case 'string':
        case 'number':
        case 'boolean':
        case 'date':
            return add ? 'add_filter' : 'remove_filter'
        case 'subject':
            return add ? 'add_instance' : 'remove_instance'
        case 'vector_sort':
            return add ? 'add_sort' : 'remove_sort'
    }
    return 'other'
}

function subQueryLabel(change: SubQueryChange): string {
    const sq = change.subquery as unknown as Record<string, unknown>
    const parts = [sq.property_label ?? sq.property_id ?? sq.instance_label ?? sq.type]
    if (sq.operator != null && sq.value != null) {
        parts.push(`${sq.operator} ${sq.value}`)
    } else if (sq.value != null && typeof sq.value != 'object') {
        parts.push(String(sq.value))
    }
    return parts.filter((p) => p != null && p !== '').join(' ')
}

type Aggregatable = { group_by?: boolean | null, aggregate?: string | null }

/** Grouping/aggregate op of a subject or subquery as it is after a flag change. */
function aggregationOpKind(after: Aggregatable, before?: Aggregatable): EditOpKind | null {
    if (!!after.group_by != !!before?.group_by) {
        return after.group_by ? 'add_group' : 'remove_group'
    }
    if ((after.aggregate ?? null) != (before?.aggregate ?? null)) {
        return after.aggregate ? 'add_aggregate' : 'remove_aggregate'
    }
    return null
}

function aggregationSuffix(x: Aggregatable): string {
    return x.group_by ? ' (group by)' : x.aggregate ? ` (${x.aggregate})` : ''
}

/**
 * Kinds of subquery changes; a remove and add of the same subquery id that differ only in
 * grouping/aggregate (how the protocol encodes a flag change) collapse to one group/aggregate op.
 */
function subQueryOps(changes: SubQueryChange[]): { kind: EditOpKind, change: SubQueryChange }[] {
    const key = (c: SubQueryChange) => `${c.subject_id}|${(c.subquery as { id?: unknown }).id}`
    const strip = (sq: object) => JSON.stringify({ ...sq, group_by: undefined, aggregate: undefined })
    const removed = new Map(changes.filter((c) => c.operation == 'remove').map((c) => [key(c), c]))
    const paired = new Set<SubQueryChange>()
    const ops: { kind: EditOpKind, change: SubQueryChange }[] = []
    for (const c of changes) {
        if (c.operation != 'add') continue
        const before = removed.get(key(c))
        if (!before || strip(before.subquery) != strip(c.subquery)) continue
        const kind = aggregationOpKind(c.subquery as Aggregatable, before.subquery as Aggregatable)
        if (kind) {
            paired.add(c).add(before)
            ops.push({ kind, change: c })
        }
    }
    return [...changes.filter((c) => !paired.has(c)).map((c) => ({ kind: subQueryOpKind(c), change: c })), ...ops]
}

/** Operations of a graph change (the agent's or the progressive panel's). */
export function opsFromGraphChange(change: GraphChange, ref?: Partial<EditOp>): EditOp[] {
    const subject_label = (id: string) =>
        [...change.added.subjects, ...change.removed.subjects, ...change.context].find((s) => s.id == id)?.label ?? id
    const link_label = (l: AgentLink) =>
        `${l.from_subject_label ?? subject_label(l.from_subject_id)} –${l.label || l.uri}→ ${l.to_subject_label ?? subject_label(l.to_subject_id)}`
    return [
        ...change.removed.links.map((l) => ({ kind: 'remove_link' as const, label: link_label(l) })),
        ...change.removed.subjects.map((s) => ({ kind: 'remove_subject' as const, label: s.label ?? s.uri ?? s.id })),
        ...change.added.subjects.map((s) => ({ kind: 'add_subject' as const, label: s.label ?? s.uri ?? s.id })),
        ...change.added.links.map((l) => ({ kind: 'add_link' as const, label: link_label(l) })),
        ...subQueryOps(change.subqueries ?? []).map(({ kind, change: c }) => ({
            kind,
            label: `${subject_label(c.subject_id)}: ${subQueryLabel(c)}${aggregationSuffix(c.subquery)}`,
        })),
        ...(change.updated ?? []).map((s) => ({
            kind: aggregationOpKind(s) ?? ('other' as const),
            label: `${s.label ?? s.uri ?? s.id}${aggregationSuffix(s)}`,
        })),
    ].map((op) => ({ ...op, ...ref }))
}

/**
 * Provenance of an agent edit: the ops of the tool calls that changed the graph (with their
 * call and chat entry ids), or those of the applied change if no call carries changes.
 */
export function agentProvenance(change: GraphChange, calls: AgentCallRef[] = []): EditProvenance {
    const with_changes = calls.filter((c) => c.call.changes)
    const ops = with_changes.length
        ? with_changes.flatMap(({ call, entry_id }) =>
            opsFromGraphChange(call.changes!, { call_id: call.call_id, tool: call.name, chat_entry_id: entry_id }))
        : opsFromGraphChange(change)
    return {
        source: 'agent',
        ops: ops.length ? ops : [{ kind: 'other', label: '' }],
        chat_entry_ids: with_changes.map((c) => c.entry_id),
    }
}

export function progressiveProvenance(change: GraphChange): EditProvenance {
    return { source: 'progressive', ops: opsFromGraphChange(change) }
}

/** Ops grouped by kind (in first-occurrence order), for compact icon stacks. */
export function groupedOps(provenance: EditProvenance | null | undefined) {
    const groups = new Map<EditOpKind, EditOp[]>()
    for (const op of provenance?.ops ?? []) {
        groups.set(op.kind, [...(groups.get(op.kind) ?? []), op])
    }
    return [...groups.entries()].map(([kind, ops]) => ({ kind, ops, style: OP_STYLES[kind] ?? OP_STYLES.other }))
}

/** Multi-line summary of an edit, for tooltips. */
export function provenanceSummary(provenance: EditProvenance | null | undefined): string {
    const p = provenance ?? userProvenance()
    const lines = [SOURCE_STYLES[p.source]?.label ?? p.source]
    if (p.source == 'revert' && p.reverted_to) {
        lines[0] += ` to ${new Date(p.reverted_to).toLocaleTimeString()}`
        if (p.reverted_from && p.reverted_from.source != 'user') {
            lines[0] += ` (${SOURCE_STYLES[p.reverted_from.source]?.label.toLowerCase()})`
        }
    }
    for (const op of p.ops) {
        const style = OP_STYLES[op.kind] ?? OP_STYLES.other
        const tool = op.tool ? ` [${op.tool}]` : ''
        lines.push(`${style.label}${op.label ? `: ${op.label}` : ''}${tool}`)
    }
    return lines.join('\n')
}

const glyph_cache = new Map<string, string>()

/**
 * The character of an mdi icon class (e.g. 'mdi-robot-outline') in the "Material Design
 * Icons" font, read from the webfont's CSS, for drawing icons as SVG text.
 */
export function mdiGlyph(icon: string): string {
    const cached = glyph_cache.get(icon)
    if (cached !== undefined) {
        return cached
    }
    let glyph = ''
    if (typeof document != 'undefined') {
        const el = document.createElement('i')
        el.className = `mdi ${icon}`
        el.style.position = 'absolute'
        el.style.visibility = 'hidden'
        document.body.appendChild(el)
        const content = getComputedStyle(el, '::before').content
        el.remove()
        if (content && content != 'none' && content != 'normal') {
            glyph = content.replace(/^["']|["']$/g, '')
        }
    }
    glyph_cache.set(icon, glyph)
    return glyph
}

export const MDI_FONT_FAMILY = '"Material Design Icons"'
