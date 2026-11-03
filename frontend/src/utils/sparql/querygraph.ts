// Conversion between the editor's query graph (NodeLinkRepository of SubjectNode/Link)
// and the backend's QueryGraph (backend/src/assistant/assistant_model.py), which carries
// everything generateQuery() reads, but not the layout.
//
// Identity mapping:
// - subject:  AssistantSubject.id  <-> SubjectNode.internal_id
//             AssistantSubject.uri <-> SubjectNode.subject_id (n3 form, e.g. <http://...> or dbo:Ship)
// - link:     AssistantLink.id     <-> Link.agent_id, or `link_<link_id>` for links created in the editor
//             (Link.link_id is a client-side counter, so restored/agent ids are kept in agent_id)
//             AssistantLink.uri    <-> Link.property_id ('' for an arbitrary link without property)
//             from/to_subject_id   <-> Link.from/to_internal_id
//             property_type, allow_arbitrary, quantifier, semantic_link_type <-> the Link fields,
//             left out (None) when they have the editor default
// - subquery: one per SubQuery of a node, `type` <-> constraint_type, `id` <-> SubQuery.id;
//             its link (the property of the node it constrains) is flattened into
//             property_id/property_label/property_type <-> Link.property_id/label/to_proptype.
//             QueryProp is always sent as query_prop (also for image ranges); image_prop is
//             accepted and restored as a QueryProp.
import type {
    AssistantLink, AssistantSubject, Instance, QueryGraph, Subject, SubjectLink, VectorSortSubQuery,
} from '@/api/client.ts/Api'
import { fitNode, LINK_WIDTH, NODE_HEIGHT } from './helpers'
import { NodeLinkRepository } from './store'
import {
    InstanceQueryProp, Link, LinkQuantifier, LinkQuantifierType, LinkType, reserveInternalIds, SubjectNode,
} from './representation/graph'
import {
    BooleanConstraint, DateConstraint, NumberConstraint, NumberConstraintType, QueryProp, StringConstraint,
    StringConstraintType, SubjectConstraint, SubQuery, SubQueryType, VectorSort, VectorSortDirection,
    VectorSortDistance, VectorSortModality,
} from './representation/subqueries'

export type GraphSubQuery = NonNullable<AssistantSubject['subqueries']>[number]
/** Subject/link/graph with the ids the editor always assigns. */
export type GraphSubject = AssistantSubject & { id: string, subqueries: GraphSubQuery[] }
export type GraphLink = AssistantLink & { id: string, from_subject_id: string, to_subject_id: string }
export interface EditorQueryGraph extends QueryGraph {
    subjects: GraphSubject[]
    links: GraphLink[]
}

/** Ontology data of subjects/links (e.g. from the agent), keyed by graph id. */
export interface QueryGraphDetails {
    subjects?: Record<string, Subject>
    links?: Record<string, SubjectLink>
}

export interface QueryGraphOptions {
    /** include the (large) vector and input image/text of vector sorts (default true) */
    payloads?: boolean
}

// horizontal gap between a node and the node it is linked to
const LINK_GAP = LINK_WIDTH * 1.5
// vertical distance between nodes stacked at the same anchor
const ROW_GAP = NODE_HEIGHT * 2.5

/** Graph id of an editor link. */
export function linkGraphId(link: Link): string {
    return link.agent_id ?? `link_${link.link_id}`
}

/** Subquery as the backend models it, null for kinds it has no model for (or invalid dates). */
export function toGraphSubQuery(subquery: SubQuery, options: QueryGraphOptions = {}): GraphSubQuery | null {
    const link = subquery.link
    const base = {
        id: subquery.id != null ? String(subquery.id) : null,
        property_id: link?.property_id ?? null,
        property_label: link?.label ?? null,
        property_type: link?.to_proptype ?? null,
    }
    switch (subquery.constraint_type) {
        case SubQueryType.QUERY_PROP:
            return base.property_id ? { ...base, type: 'query_prop', property_id: base.property_id } : null
        case SubQueryType.INSTANCE_PROP: {
            const prop = subquery as InstanceQueryProp
            return base.property_id ? { ...base, type: 'instance_prop', property_id: base.property_id, value: prop.value ?? null } : null
        }
        case SubQueryType.SUBJECT: {
            const instance = (subquery as SubjectConstraint).instance
            return { ...base, type: 'subject', instance_id: instance?.id ?? null, instance_label: instance?.label ?? null }
        }
        case SubQueryType.STRING: {
            const constraint = subquery as StringConstraint
            return { ...base, type: 'string', value: constraint.value ?? '', operator: constraint.type as any }
        }
        case SubQueryType.NUMBER: {
            const constraint = subquery as NumberConstraint
            const value = Number(constraint.value)
            return { ...base, type: 'number', value: Number.isFinite(value) ? value : 0, operator: constraint.type as any }
        }
        case SubQueryType.BOOLEAN:
            return { ...base, type: 'boolean', value: !!(subquery as BooleanConstraint).value }
        case SubQueryType.DATE: {
            const constraint = subquery as DateConstraint
            const date = constraint.value ? new Date(constraint.value) : null
            if (!date || isNaN(date.getTime())) {
                return null
            }
            return { ...base, type: 'date', value: date.toISOString(), operator: constraint.type as any }
        }
        case SubQueryType.VECTOR_SORT: {
            const sort = subquery as VectorSort
            const converted: VectorSortSubQuery & { type: 'vector_sort' } = {
                ...base, type: 'vector_sort',
                modality: sort.modality as any, direction: sort.direction as any, distance: sort.distance as any,
            }
            if (options.payloads ?? true) {
                converted.vector = sort.vector ?? null
                converted.input_state = { image: sort.input_state?.image ?? null, text: sort.input_state?.text ?? null }
            }
            return converted
        }
        default:
            return null
    }
}

export function toGraphSubject(node: SubjectNode, options: QueryGraphOptions = {}): GraphSubject {
    return {
        id: node.internal_id,
        uri: node.subject_id,
        label: node.label || node.subject_id,
        subqueries: (node.subqueries || [])
            .filter((sq) => sq != null)
            .map((sq) => toGraphSubQuery(sq, options))
            .filter((sq): sq is GraphSubQuery => sq !== null),
    }
}

export function toGraphLink(link: Link, from: GraphSubject, to: GraphSubject): GraphLink {
    const converted: GraphLink = {
        id: linkGraphId(link),
        uri: link.property_id ?? '',
        label: link.label || link.property_id || '*',
        from_subject_id: from.id,
        to_subject_id: to.id,
        from_subject_label: from.label,
        from_subject_uri: from.uri,
        to_subject_label: to.label,
        to_subject_uri: to.uri,
    }
    // editor defaults are left out, like the backend's None
    if (link.to_proptype) {
        converted.property_type = link.to_proptype
    }
    if (link.allow_arbitrary) {
        converted.allow_arbitrary = true
    }
    if (link.quantifier) {
        converted.quantifier = { type: link.quantifier.type as any, min: link.quantifier.min ?? null, max: link.quantifier.max ?? null }
    }
    if (link.semantic_link_type && link.semantic_link_type != LinkType.STRUCTURAL) {
        converted.semantic_link_type = link.semantic_link_type as any
    }
    return converted
}

/**
 * The editor graph as QueryGraph. Links that are not configured yet (no property and
 * not arbitrary) or whose subjects are missing are left out, as generateQuery() cannot use them.
 */
export function toQueryGraph(store: NodeLinkRepository | null | undefined, options: QueryGraphOptions = {}): EditorQueryGraph {
    if (!store) {
        return { subjects: [], links: [] }
    }
    const subjects = store.nodes.map((node) => toGraphSubject(node, options))
    const by_id = new Map(subjects.map((s) => [s.id, s]))
    const links: GraphLink[] = []
    for (const link of store.links) {
        const from = by_id.get(link.from_internal_id)
        const to = by_id.get(link.to_internal_id)
        if (!from || !to || (!link.property_id && !link.allow_arbitrary)) {
            continue
        }
        links.push(toGraphLink(link, from, to))
    }
    return { subjects, links }
}

/** Editor link of a subquery: the property `node` is constrained on. */
function subQueryLink(subquery: GraphSubQuery, node: SubjectNode): Link {
    const link = new Link()
    link.link_type = 'relation'
    link.from_id = node.subject_id
    link.from_internal_id = node.internal_id
    link.from_subject = node
    link.property_id = subquery.property_id ?? null
    link.label = subquery.property_label ?? subquery.property_id ?? ''
    link.to_proptype = subquery.property_type ?? null
    return link
}

/** Editor subquery of a backend subquery, attached to `node`. */
export function fromGraphSubQuery(subquery: GraphSubQuery, node: SubjectNode): SubQuery {
    let converted: SubQuery
    switch (subquery.type) {
        case 'query_prop':
        case 'image_prop': {
            const prop = new QueryProp()
            prop.property_id = subquery.property_id
            converted = prop
            break
        }
        case 'instance_prop': {
            const prop = new InstanceQueryProp()
            prop.property_id = subquery.property_id
            prop.value = subquery.value ?? null
            converted = prop
            break
        }
        case 'subject': {
            const constraint = new SubjectConstraint()
            constraint.instance = subquery.instance_id
                ? { id: subquery.instance_id, label: subquery.instance_label ?? '' } as Instance
                : null
            converted = constraint
            break
        }
        case 'string':
            converted = new StringConstraint(subquery.value ?? '', (subquery.operator ?? StringConstraintType.CONTAINS) as unknown as StringConstraintType)
            break
        case 'number':
            converted = new NumberConstraint(subquery.value ?? 0, (subquery.operator ?? NumberConstraintType.GREATER) as unknown as NumberConstraintType)
            break
        case 'boolean':
            converted = new BooleanConstraint(subquery.value ?? false)
            break
        case 'date':
            converted = new DateConstraint(subquery.value, (subquery.operator ?? NumberConstraintType.GREATER) as unknown as NumberConstraintType)
            break
        case 'vector_sort': {
            const sort = new VectorSort(
                (subquery.modality ?? VectorSortModality.IMAGE) as unknown as VectorSortModality,
                (subquery.direction ?? VectorSortDirection.DESCENDING) as unknown as VectorSortDirection,
                (subquery.distance ?? VectorSortDistance.COSINE) as unknown as VectorSortDistance,
            )
            sort.vector = subquery.vector ?? null
            sort.input_state = { image: subquery.input_state?.image ?? null, text: subquery.input_state?.text ?? null }
            converted = sort
            break
        }
        default:
            converted = new SubQuery()
    }
    if (subquery.id != null && subquery.id !== '') {
        // editor ids are numbers from SubQuery.id_counter, keep new ones from colliding
        const numeric = Number(subquery.id)
        if (Number.isInteger(numeric)) {
            converted.id = numeric
            SubQuery.id_counter = Math.max(SubQuery.id_counter, numeric + 1)
        } else {
            converted.id = subquery.id
        }
    }
    converted.link = subQueryLink(subquery, node)
    return converted
}

/** Editor node of a subject; its subqueries are only restored with `with_subqueries`. */
export function subjectNodeFor(subject: AssistantSubject & { id: string }, details?: Subject | null, with_subqueries: boolean = false): SubjectNode {
    const node = new SubjectNode(details ?? { subject_id: subject.uri, label: subject.label })
    node.internal_id = subject.id
    node.subject_id = details?.subject_id ?? subject.uri
    node.label = subject.label || node.label
    if (with_subqueries) {
        node.subqueries = (subject.subqueries || []).map((sq) => fromGraphSubQuery(sq, node))
    }
    fitNode(node)
    return node
}

export function linkFor(link: GraphLink, from: SubjectNode, to: SubjectNode, details?: SubjectLink | null): Link {
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
        property_id: details?.property_id ?? (link.uri || null),
        from_subject: from,
        to_subject: to,
    } as SubjectLink)
    editor_link.from_internal_id = from.internal_id
    editor_link.to_internal_id = to.internal_id
    editor_link.agent_id = link.id
    if (link.property_type) {
        editor_link.to_proptype = link.property_type
    }
    editor_link.allow_arbitrary = !!link.allow_arbitrary
    editor_link.quantifier = link.quantifier
        ? new LinkQuantifier(
            (link.quantifier.type ?? LinkQuantifierType.ONE_OR_MORE) as unknown as LinkQuantifierType,
            link.quantifier.min ?? null, link.quantifier.max ?? null,
        )
        : null
    editor_link.semantic_link_type = (link.semantic_link_type ?? LinkType.STRUCTURAL) as unknown as LinkType
    return editor_link
}

/** Positions new nodes next to the nodes they are linked to, unlinked ones below the graph. */
export function placeNodes(placed: SubjectNode[], fresh: SubjectNode[], links: { from: string, to: string }[]) {
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
 * A new editor store of a QueryGraph (subjects with their subqueries, links with their
 * options), laid out from scratch; the inverse of toQueryGraph() up to the layout.
 */
export function fromQueryGraph(graph: QueryGraph, details: QueryGraphDetails = {}): NodeLinkRepository {
    const subjects = (graph.subjects ?? []).filter((s): s is GraphSubject => !!s.id)
    reserveInternalIds(subjects.map((s) => s.id))
    const nodes = subjects.map((s) => subjectNodeFor(s, details.subjects?.[s.id], true))
    const by_id = new Map(nodes.map((n) => [n.internal_id, n]))
    const links = (graph.links ?? []).filter((l): l is GraphLink =>
        !!l.id && by_id.has(l.from_subject_id) && by_id.has(l.to_subject_id))
    placeNodes([], nodes, links.map((l) => ({ from: l.from_subject_id, to: l.to_subject_id })))
    return new NodeLinkRepository<SubjectNode, Link>(
        nodes,
        links.map((l) => linkFor(l, by_id.get(l.from_subject_id)!, by_id.get(l.to_subject_id)!, details.links?.[l.id])),
    )
}
