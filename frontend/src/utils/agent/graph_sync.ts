// Agent side of the conversion between the editor's query graph (NodeLinkRepository of
// SubjectNode/Link, src/utils/sparql) and the backend's canonical QueryGraph (AgentQueryGraph).
// The conversion itself, and its identity mapping, is utils/sparql/querygraph.ts; the agent
// gets the full graph except for the vector payloads of vector sorts.
//
// The agent's graph changes are applied as a diff (added/removed by id) to the editor
// store, so concurrent edits and everything the agent does not change (positions, link
// options, untouched subqueries) are kept. Changes may also carry subquery
// additions/removals of single subjects (GraphChange.subqueries: the constraints the agent
// adds with its constraint tools, or those of the progressive panel), which are applied to
// those subjects' nodes the same way.
import { NodeLinkRepository } from '@/utils/sparql/store'
import { type Link, type SubjectNode } from '@/utils/sparql/representation'
import {
    fromGraphSubQuery, linkFor, linkGraphId, placeNodes, subjectNodeFor, toGraphSubject, toQueryGraph,
} from '@/utils/sparql/querygraph'
import type {
    AgentLink, AgentQueryGraph, AgentSubject, AgentSubQuery, GraphChange, GraphDetails, SubQueryChange,
} from './protocol'

export { linkFor, linkGraphId, subjectNodeFor }

export function toAgentSubject(node: SubjectNode): AgentSubject {
    return toGraphSubject(node, { payloads: false })
}

/** The editor graph as QueryGraph, without vector payloads; unconfigured links are left out. */
export function toAgentGraph(store: NodeLinkRepository | null | undefined): AgentQueryGraph {
    return toQueryGraph(store, { payloads: false })
}

function canonicalSubQuery(subquery: AgentSubQuery) {
    // only the fields both sides fill, so a backend round trip (defaults added) compares equal
    const { input_state: _input_state, vector: _vector, ...rest } = subquery as unknown as Record<string, unknown>
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
        .map((l) => [l.id, l.uri, l.from_subject_id, l.to_subject_id,
            l.allow_arbitrary ?? null, l.quantifier ?? null, l.semantic_link_type ?? null])
    return JSON.stringify([subjects, links])
}

/**
 * Subquery changes of one subject, by subquery id: only in `after` (add) or only in
 * `before` (remove). Subqueries with the same id are kept as they are in the editor (the
 * agent only adds and removes them). Without `before` (an added subject) all its
 * subqueries are added.
 */
function diffSubQueries(before: AgentSubject | undefined, after: AgentSubject): SubQueryChange[] {
    const old = new Set((before?.subqueries || []).map((sq) => String(sq.id)))
    const now = new Set((after.subqueries || []).map((sq) => String(sq.id)))
    return [
        ...(before?.subqueries || []).filter((sq) => !now.has(String(sq.id)))
            .map((subquery) => ({ operation: 'remove' as const, subject_id: after.id, subquery })),
        ...(after.subqueries || []).filter((sq) => !old.has(String(sq.id)))
            .map((subquery) => ({ operation: 'add' as const, subject_id: after.id, subquery })),
    ]
}

/**
 * Subjects/links only in `after` (added) or only in `before` (removed), by id, and the
 * subquery changes of the subjects (added subjects' nodes get theirs this way).
 */
export function diffAgentGraphs(before: AgentQueryGraph, after: AgentQueryGraph): GraphChange {
    const before_by_id = new Map(before.subjects.map((s) => [s.id, s]))
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
        subqueries: after.subjects.flatMap((s) => diffSubQueries(before_by_id.get(s.id), s)),
    }
}

export function isEmptyChange(change: GraphChange): boolean {
    return change.added.subjects.length == 0 && change.added.links.length == 0
        && change.removed.subjects.length == 0 && change.removed.links.length == 0
        && !change.subqueries?.length
}

/** Applies subquery changes to a node in place; already present (added) or gone (removed) ones are skipped. */
function applySubQueryChanges(node: SubjectNode, changes: SubQueryChange[]) {
    for (const { operation, subquery } of changes) {
        const present = (node.subqueries || []).some((sq) => subquery.id != null && String(sq.id) == String(subquery.id))
        if (operation == 'remove') {
            node.subqueries = (node.subqueries || []).filter((sq) => String(sq.id) != String(subquery.id))
        } else if (!present) {
            node.subqueries = [...(node.subqueries || []), fromGraphSubQuery(subquery, node)]
        }
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

    for (const subquery of change.subqueries ?? []) {
        const node = store.nodes.find((n) => n.internal_id == subquery.subject_id)
        if (!node) {
            console.warn('Subquery change without its subject in the editor', subquery)
            continue
        }
        applySubQueryChanges(node, [subquery])
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

    // subjects with subquery changes: a copy per side, before with the removed subqueries,
    // after with the added ones (Node.vue highlights them by the diff of the two)
    const subquery_changes = change.subqueries ?? []
    const side = (operation: SubQueryChange['operation']) => {
        const copies = new Map<string, SubjectNode>()
        for (const id of new Set(subquery_changes.map((c) => c.subject_id))) {
            const node = nodes.get(id)
            if (!node) {
                continue
            }
            const subject = all_subjects.find((s) => s.id == id)!
            const copy = subjectNodeFor(subject, subject_details[id])
            copy.x = node.x
            copy.y = node.y
            applySubQueryChanges(copy, subquery_changes
                .filter((c) => c.subject_id == id && c.operation == operation)
                .map((c) => ({ ...c, operation: 'add' })))
            copies.set(id, copy)
        }
        return copies
    }
    const sides = { before: side('remove'), after: side('add') }

    const build = (subjects: AgentSubject[], links: AgentLink[], copies: Map<string, SubjectNode>) => {
        const ids = new Set([...change.context, ...subjects].map((s) => s.id))
        for (const link of links) {
            ids.add(link.from_subject_id)
            ids.add(link.to_subject_id)
        }
        const node = (id: string) => copies.get(id) ?? nodes.get(id)
        const repo = new NodeLinkRepository<SubjectNode, Link>([...ids].map(node).filter((n): n is SubjectNode => !!n))
        for (const link of links) {
            repo.links.push(linkFor(link, node(link.from_subject_id)!, node(link.to_subject_id)!, link_details[link.id]))
        }
        return repo
    }
    return {
        before: build(change.removed.subjects, change.removed.links, sides.before),
        after: build(change.added.subjects, change.added.links, sides.after),
    }
}
