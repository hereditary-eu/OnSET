// Conversion between the editor's query graph (NodeLinkRepository of SubjectNode/Link,
// src/utils/sparql) and the backend's canonical QueryGraph (AgentQueryGraph).
//
// Identity mapping:
// - subject: AgentSubject.id  <-> SubjectNode.internal_id
//            AgentSubject.uri <-> SubjectNode.subject_id (n3 form, e.g. <http://...> or dbo:Ship)
// - link:    AgentLink.id     <-> Link.agent_id, or `link_<link_id>` for links created in the editor
//            (Link.link_id is a client-side counter, so ids the agent assigned are kept in agent_id)
//            AgentLink.uri    <-> Link.property_id
//            from/to_subject_id <-> Link.from/to_internal_id
// - subqueries are sent to the agent as read-only context (the subquery models of
//   assistant_model.py); the agent cannot create them, so they are never converted back.
//
// The agent's graph changes are applied as a diff (added/removed by id) to the editor
// store, so concurrent edits and everything the QueryGraph does not carry (positions,
// subqueries, quantifiers) are kept.
import type { Subject, SubjectLink } from '@/api/client.ts/Api'
import { fitNode, LINK_WIDTH, NODE_HEIGHT } from '@/utils/sparql/helpers'
import { NodeLinkRepository } from '@/utils/sparql/store'
import { Link, SubjectNode } from '@/utils/sparql/representation'
import {
    BooleanConstraint, DateConstraint, NumberConstraint, QueryProp, StringConstraint,
    SubjectConstraint, SubQueryType, VectorSort, type SubQuery,
} from '@/utils/sparql/representation/subqueries'
import type {
    AgentLink, AgentQueryGraph, AgentSubject, AgentSubQuery, GraphChange, GraphDetails,
} from './protocol'

// horizontal gap between a node and the node it is linked to
const LINK_GAP = LINK_WIDTH * 1.5
// vertical distance between nodes stacked at the same anchor
const ROW_GAP = NODE_HEIGHT * 2.5

/** Graph id of an editor link. */
export function linkGraphId(link: Link): string {
    return link.agent_id ?? `link_${link.link_id}`
}

/** Subquery as the backend models it, null for kinds it has no model for (instance/image props). */
function toAgentSubQuery(subquery: SubQuery): AgentSubQuery | null {
    const base = { id: subquery.id != null ? String(subquery.id) : null, property_id: subquery.link?.property_id ?? null }
    switch (subquery.constraint_type) {
        case SubQueryType.QUERY_PROP:
            return base.property_id ? { ...base, type: 'query_prop', property_id: (subquery as QueryProp).link.property_id } : null
        case SubQueryType.SUBJECT: {
            const instance = (subquery as SubjectConstraint).instance
            return { ...base, type: 'subject', instance_id: instance?.id ?? null, instance_label: instance?.label ?? null }
        }
        case SubQueryType.STRING: {
            const constraint = subquery as StringConstraint
            return { ...base, type: 'string', value: constraint.value ?? '', operator: constraint.type }
        }
        case SubQueryType.NUMBER: {
            const constraint = subquery as NumberConstraint
            const value = Number(constraint.value)
            return { ...base, type: 'number', value: Number.isFinite(value) ? value : 0, operator: constraint.type }
        }
        case SubQueryType.BOOLEAN:
            return { ...base, type: 'boolean', value: !!(subquery as BooleanConstraint).value }
        case SubQueryType.DATE: {
            const constraint = subquery as DateConstraint
            const date = constraint.value ? new Date(constraint.value) : null
            if (!date || isNaN(date.getTime())) {
                return null
            }
            return { ...base, type: 'date', value: date.toISOString(), operator: constraint.type }
        }
        case SubQueryType.VECTOR_SORT: {
            const sort = subquery as VectorSort
            return { ...base, type: 'vector_sort', modality: sort.modality, direction: sort.direction, distance: sort.distance }
        }
        default:
            return null
    }
}

export function toAgentSubject(node: SubjectNode): AgentSubject {
    return {
        id: node.internal_id,
        uri: node.subject_id,
        label: node.label || node.subject_id,
        subqueries: (node.subqueries || [])
            .filter((sq) => sq != null)
            .map(toAgentSubQuery)
            .filter((sq): sq is AgentSubQuery => sq !== null),
    }
}

/** The editor graph as QueryGraph; links that are not configured yet (no property) are left out. */
export function toAgentGraph(store: NodeLinkRepository | null | undefined): AgentQueryGraph {
    if (!store) {
        return { subjects: [], links: [] }
    }
    const subjects = store.nodes.map(toAgentSubject)
    const by_id = new Map(subjects.map((s) => [s.id, s]))
    const links: AgentLink[] = []
    for (const link of store.links) {
        const from = by_id.get(link.from_internal_id)
        const to = by_id.get(link.to_internal_id)
        if (!from || !to || !link.property_id) {
            continue
        }
        links.push({
            id: linkGraphId(link),
            uri: link.property_id,
            label: link.label || link.property_id,
            from_subject_id: from.id,
            to_subject_id: to.id,
            from_subject_label: from.label,
            from_subject_uri: from.uri,
            to_subject_label: to.label,
            to_subject_uri: to.uri,
        })
    }
    return { subjects, links }
}

function canonicalSubQuery(subquery: AgentSubQuery) {
    // only the fields both sides fill, so a backend round trip (defaults added) compares equal
    const { input_state: _input_state, vector: _vector, ...rest } = subquery
    return Object.keys(rest).sort()
        .filter((key) => rest[key] !== null && rest[key] !== undefined)
        .map((key) => [key, rest[key]])
}

/** Order-independent comparison key of a graph. */
export function graphKey(graph: AgentQueryGraph): string {
    const subjects = [...graph.subjects]
        .sort((a, b) => a.id.localeCompare(b.id))
        .map((s) => [s.id, s.uri, s.label, (s.subqueries || []).map(canonicalSubQuery)])
    const links = [...graph.links]
        .sort((a, b) => a.id.localeCompare(b.id))
        .map((l) => [l.id, l.uri, l.from_subject_id, l.to_subject_id])
    return JSON.stringify([subjects, links])
}

/** Subjects/links only in `after` (added) or only in `before` (removed), by id. */
export function diffAgentGraphs(before: AgentQueryGraph, after: AgentQueryGraph): GraphChange {
    const before_subjects = new Set(before.subjects.map((s) => s.id))
    const after_subjects = new Set(after.subjects.map((s) => s.id))
    const before_links = new Set(before.links.map((l) => l.id))
    const after_links = new Set(after.links.map((l) => l.id))
    return {
        added: {
            subjects: after.subjects.filter((s) => !before_subjects.has(s.id)),
            links: after.links.filter((l) => !before_links.has(l.id)),
        },
        removed: {
            subjects: before.subjects.filter((s) => !after_subjects.has(s.id)),
            links: before.links.filter((l) => !after_links.has(l.id)),
        },
        context: [],
    }
}

export function isEmptyChange(change: GraphChange): boolean {
    return change.added.subjects.length == 0 && change.added.links.length == 0
        && change.removed.subjects.length == 0 && change.removed.links.length == 0
}

export function subjectNodeFor(subject: AgentSubject, details?: Subject | null): SubjectNode {
    const node = new SubjectNode(details ?? { subject_id: subject.uri, label: subject.label })
    node.internal_id = subject.id
    node.subject_id = details?.subject_id ?? subject.uri
    node.label = subject.label || node.label
    fitNode(node)
    return node
}

export function linkFor(link: AgentLink, from: SubjectNode, to: SubjectNode, details?: SubjectLink | null): Link {
    const editor_link = new Link({
        link_id: 0,
        link_type: 'relation',
        to_proptype: null,
        instance_count: 0,
        // domain/range of the property, like links chosen in the link selector
        from_id: from.subject_id,
        to_id: to.subject_id,
        ...(details ?? {}),
        label: link.label,
        property_id: details?.property_id ?? link.uri,
        from_subject: from,
        to_subject: to,
    } as SubjectLink)
    editor_link.from_internal_id = from.internal_id
    editor_link.to_internal_id = to.internal_id
    editor_link.agent_id = link.id
    return editor_link
}

/** Positions new nodes next to the nodes they are linked to, unlinked ones below the graph. */
function placeNodes(placed: SubjectNode[], fresh: SubjectNode[], links: { from: string, to: string }[]) {
    const positioned = new Map(placed.map((n) => [n.internal_id, n]))
    const stacked = new Map<string, number>()
    // last node of the row of unlinked new nodes
    let row_end: SubjectNode | null = null
    let pending = [...fresh]
    while (pending.length > 0) {
        const remaining: SubjectNode[] = []
        for (const node of pending) {
            let anchor: SubjectNode | undefined
            let outgoing = true
            for (const link of links) {
                if (link.to == node.internal_id && positioned.has(link.from)) {
                    anchor = positioned.get(link.from)
                    break
                }
                if (link.from == node.internal_id && positioned.has(link.to)) {
                    anchor = positioned.get(link.to)
                    outgoing = false
                    break
                }
            }
            if (!anchor) {
                remaining.push(node)
                continue
            }
            const slot = `${anchor.internal_id}:${outgoing}`
            const row = stacked.get(slot) ?? 0
            stacked.set(slot, row + 1)
            node.x = outgoing ? anchor.x + anchor.width + LINK_GAP : anchor.x - node.width - LINK_GAP
            node.y = anchor.y + row * ROW_GAP
            positioned.set(node.internal_id, node)
        }
        if (remaining.length == pending.length) {
            // nothing links them to placed nodes: start a row below the graph with the first one
            const first = remaining.shift()!
            if (row_end) {
                first.x = row_end.x + row_end.width + 2 * LINK_GAP
                first.y = row_end.y
            } else {
                const nodes = [...positioned.values()]
                first.x = nodes.length ? Math.min(...nodes.map((n) => n.x)) : 40
                first.y = nodes.length ? Math.max(...nodes.map((n) => n.y + n.height)) + ROW_GAP : 60
            }
            row_end = first
            positioned.set(first.internal_id, first)
        }
        pending = remaining
    }
}

/**
 * Applies the agent's change to the editor store in place: removes, then adds subjects
 * (laid out next to their linked nodes) and links. Elements that are already present
 * (added) or already gone (removed) are skipped, so concurrent editor changes survive.
 */
export function applyGraphChange(store: NodeLinkRepository, change: GraphChange, details: GraphDetails) {
    for (const link of change.removed.links) {
        const editor_link = store.links.find((l) => linkGraphId(l) == link.id)
        if (editor_link) {
            store.links = store.links.filter((l) => l !== editor_link)
        }
    }
    for (const subject of change.removed.subjects) {
        const node = store.nodes.find((n) => n.internal_id == subject.id)
        if (node) {
            store.removeNode(node)
        }
    }

    const fresh = change.added.subjects
        .filter((s) => !store.nodes.some((n) => n.internal_id == s.id))
        .map((s) => subjectNodeFor(s, details.subjects[s.id]))
    placeNodes(store.nodes, fresh, change.added.links.map((l) => ({ from: l.from_subject_id, to: l.to_subject_id })))
    store.nodes.push(...fresh)

    for (const link of change.added.links) {
        if (store.links.some((l) => linkGraphId(l) == link.id)) {
            continue
        }
        const from = store.nodes.find((n) => n.internal_id == link.from_subject_id)
        const to = store.nodes.find((n) => n.internal_id == link.to_subject_id)
        if (!from || !to) {
            console.warn('Agent link without subjects in the editor', link)
            continue
        }
        store.links.push(linkFor(link, from, to, details.links[link.id]))
    }
}

/**
 * Two small stores showing a tool call's change (context + removed, context + added),
 * laid out together, for rendering as a mini graph with diff highlighting.
 */
export function changeRepositories(change: GraphChange, details?: GraphDetails | null) {
    const subject_details = details?.subjects ?? {}
    const link_details = details?.links ?? {}
    const all_subjects = [...change.context, ...change.removed.subjects, ...change.added.subjects]
    const nodes = new Map<string, SubjectNode>()
    for (const subject of all_subjects) {
        if (!nodes.has(subject.id)) {
            nodes.set(subject.id, subjectNodeFor(subject, subject_details[subject.id]))
        }
    }
    // links may reference subjects that are neither changed nor context (e.g. removed with them)
    for (const link of [...change.removed.links, ...change.added.links]) {
        for (const [id, label, uri] of [
            [link.from_subject_id, link.from_subject_label, link.from_subject_uri],
            [link.to_subject_id, link.to_subject_label, link.to_subject_uri],
        ]) {
            if (!nodes.has(id)) {
                nodes.set(id, subjectNodeFor({ id, label: label || id, uri: uri || id }))
            }
        }
    }
    const all_links = [...change.removed.links, ...change.added.links]
    const ordered = [...nodes.values()]
    if (ordered.length) {
        ordered[0].x = 0
        ordered[0].y = 0
        placeNodes([ordered[0]], ordered.slice(1), all_links.map((l) => ({ from: l.from_subject_id, to: l.to_subject_id })))
    }

    const build = (subjects: AgentSubject[], links: AgentLink[]) => {
        const ids = new Set([...change.context, ...subjects].map((s) => s.id))
        for (const link of links) {
            ids.add(link.from_subject_id)
            ids.add(link.to_subject_id)
        }
        const repo = new NodeLinkRepository<SubjectNode, Link>([...ids].map((id) => nodes.get(id)).filter((n): n is SubjectNode => !!n))
        for (const link of links) {
            repo.links.push(linkFor(link, nodes.get(link.from_subject_id), nodes.get(link.to_subject_id), link_details[link.id]))
        }
        return repo
    }
    return {
        before: build(change.removed.subjects, change.removed.links),
        after: build(change.added.subjects, change.added.links),
    }
}
