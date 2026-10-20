import type { Candidates, EnrichedEntity, EnrichedRelation, EntitiesRelations, Entity, Relation } from "@/api/client.ts/Api";
import { SubQuery, Link, SubjectNode, type SubjectConstraint } from "./representation/index";
import { NodeLinkRepository } from "./store";
import { reactive } from "vue";
import type { Vector2Like } from "three";
import type { HistoryEntry } from "./history";
import { measureText } from "./measure";

export enum OpenEventType {
    TO = 'to_link',
    FROM = 'from_link',
    PROP = 'prop',
    DETAIL = 'detail',
    TYPE = 'type',
    LINK = 'link',
}
export class SelectorOpenEvent {
    node?: SubjectNode;
    side: OpenEventType;
    link?: Link;
    evt: MouseEvent;
}

export class LinkEditEvent {
    link?: Link;
    node?: SubjectNode;
    side: OpenEventType;
    success: boolean;
}


export class InstanceSelectorOpenEvent {
    node: SubjectNode;
    constraint: SubjectConstraint
}
// default node size (before a node is fitted to its label)
export const NODE_WIDTH = 120
export const NODE_HEIGHT = 22
// nodes are auto-sized to their label: text width + 2 * NODE_PADDING_X, at least NODE_MIN_WIDTH
export const NODE_MIN_WIDTH = 36
export const NODE_PADDING_X = 8
export const LINK_WIDTH = 60
// default subquery size (before its content has been measured)
export const CONSTRAINT_WIDTH = 160
export const CONSTRAINT_HEIGHT = 48
export const CONSTRAINT_PADDING = 4
// horizontal offset of a subquery box from its connector line
export const SUBQUERY_INDENT = 10
// radius of the hover edit handles on nodes, links and subqueries
export const EDITPOINT_R = 5
// width of the in-graph selection panels (link/type/instance pickers)
export const PANEL_WIDTH = 240

export function labelWidth(label: string | null | undefined): number {
    return Math.max(NODE_MIN_WIDTH, Math.ceil(measureText(label) + 2 * NODE_PADDING_X))
}
// Fit a node's box to its label (no-op if already fitted, to avoid needless reactive writes)
export function fitNode<T extends { label?: string, width?: number, height?: number }>(node: T | null | undefined): T | null | undefined {
    if (!node) {
        return node
    }
    const width = labelWidth(node.label)
    if (node.width != width) {
        node.width = width
    }
    if (node.height != NODE_HEIGHT) {
        node.height = NODE_HEIGHT
    }
    return node
}
// width reserved for a link so its label fits
export function linkWidth(label: string | null | undefined): number {
    return Math.max(LINK_WIDTH, Math.ceil(measureText(label) + 2 * NODE_PADDING_X))
}


export enum DisplayMode {
    SELECT = 'select',
    EDIT = 'edit',
    EDIT_NO_ADD = 'edit_no_add',
    RESULTS = 'results',
    RESULT_INTERACTIVE = 'result_interactive',

}
export function toVar(v: string | number): string {
    if (typeof v === 'number') {
        return v.toString()
    }
    return v.replace(/[_ &,]/g, '_')
}
export function nodeFromEntity(entity: Entity): SubjectNode {
    let subject_data = (entity as EnrichedEntity).subject ? (entity as EnrichedEntity).subject : entity
    let identifier = toVar(entity.identifier)
    let mapped_node = new SubjectNode({
        label: entity.type,
        subject_id: identifier,
        ...subject_data,
        internal_id: identifier,
    })
    fitNode(mapped_node)
    return mapped_node
}
export function linkFromRelation(relation: Relation, from: SubjectNode, to: SubjectNode, i = 0): Link {
    let link_data = (relation as EnrichedRelation).link ? (relation as EnrichedRelation).link : relation
    return new Link({
        link_id: i,
        from_id: from.subject_id,
        to_id: to.subject_id,
        label: relation.relation,
        from_internal_id: from.internal_id,
        to_internal_id: to.internal_id,
        link_type: 'relation',
        to_proptype: null,
        property_id: null,
        instance_count: 1,
        from_subject: from,
        to_subject: to,
        ...link_data,
    })
}
export function mapERLToStore(step: EntitiesRelations) {

    let store = new NodeLinkRepository()
    store.nodes = step.entities.map(nodeFromEntity)

    step.relations.forEach((relation, i) => {
        let from_internal_id = toVar(relation.entity)
        let to_internal_id = toVar(relation.target)
        let from_subject = store.nodes.find((n) => n.internal_id == from_internal_id)
        if (!from_subject) {
            from_subject = nodeFromEntity({ type: relation.entity, identifier: relation.entity })
        }
        let to_subject = store.nodes.find((n) => n.internal_id == to_internal_id)
        if (!to_subject) {
            to_subject = nodeFromEntity({ type: relation.target, identifier: relation.target })
        }
        let mapped_link = linkFromRelation(relation, from_subject, to_subject, i)
        store.addOutlink(mapped_link, from_subject, to_subject, OpenEventType.TO
        )
    })
    // if ((step as Candidates).constraints) {
    //     (step as Candidates).constraints.forEach((candidate) => {
    //         let constrained_node = store.nodes.find((n) => n.subject_id == candidate.entity)
    //         if (constrained_node) {
    //             let constraint_link = new Link({
    //                 link_id: 0,
    //                 from_id: candidate.entity,
    //                 to_id: null,
    //                 label: candidate.property,
    //                 from_internal_id: candidate.entity,
    //                 to_internal_id: candidate.entity,
    //                 link_type: 'constraint',
    //                 to_proptype: candidate.type,
    //                 property_id: candidate.property,
    //                 instance_count: 1,
    //                 from_subject: constrained_node,
    //                 to_subject: null
    //             })
    //             constrained_node.subqueries.push(SubQuery.construct(constraint_link))
    //         }
    //     })
    // }
    store.nodes = store.nodes.map(node => reactive(node))
    store.links = store.links.map(link => reactive(link))
    return store
}

export function extentNodes(nodes: SubjectNode[] = []) {
    let min_x = Infinity
    let min_y = Infinity
    let max_x = -Infinity
    let max_y = -Infinity

    for (let node of nodes) {
        if (node.x < min_x) {
            min_x = node.x
        }
        if (node.y < min_y) {
            min_y = node.y
        }
        if (node.x + node.width > max_x) {
            max_x = node.x + node.width
        }
        if (node.y + node.height > max_y) {
            max_y = node.y + node.height
        }
    }
    return { x: min_x, y: min_y, width: max_x - min_x, height: max_y - min_y }
}

export class HistoryTooltipEvent {
    position: Vector2Like
    entry: HistoryEntry | null = null
    event: MouseEvent
}