// Agent side of the conversion between the editor's query graph (NodeLinkRepository of
// SubjectNode/Link, src/utils/sparql) and the backend's canonical QueryGraph (AgentQueryGraph).
// The conversion itself, and its identity mapping, is utils/sparql/querygraph.ts; the agent
// gets the full graph except for the vector payloads of vector sorts.
//
// Subqueries are sent to the agent as read-only context; the agent cannot create them, so
// they are never converted back. The agent's graph changes are applied as a diff
// (added/removed by id) to the editor store, so concurrent edits and everything the agent
// does not change (positions, subqueries, link options) are kept.
import { NodeLinkRepository } from '@/utils/sparql/store'
import { type Link, type SubjectNode } from '@/utils/sparql/representation'
import {
    linkFor, linkGraphId, placeNodes, subjectNodeFor, toGraphSubject, toQueryGraph,
} from '@/utils/sparql/querygraph'
import type {
    AgentLink, AgentQueryGraph, AgentSubject, AgentSubQuery, GraphChange, GraphDetails,
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
