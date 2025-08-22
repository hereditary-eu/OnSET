import type { Candidates, EnrichedEntity, EnrichedRelation, EntitiesRelations, Entity, Relation } from "@/api/client.ts/Api";
import { SubQuery, Link, SubjectNode, type SubjectConstraint } from "./representation";
import { NodeLinkRepository } from "./store";
import { reactive } from "vue";

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
export const NODE_WIDTH = 150
export const NODE_HEIGHT = 32
export const LINK_WIDTH = 75
export const CONSTRAINT_WIDTH = 250
export const CONSTRAINT_HEIGHT = 75
export const CONSTRAINT_PADDING = 5


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
    mapped_node.height = NODE_HEIGHT
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
    if ((step as Candidates).constraints) {
        (step as Candidates).constraints.forEach((candidate) => {
            let constrained_node = store.nodes.find((n) => n.subject_id == candidate.entity)
            if (constrained_node) {
                let constraint_link = new Link({
                    link_id: 0,
                    from_id: candidate.entity,
                    to_id: null,
                    label: candidate.property,
                    from_internal_id: candidate.entity,
                    to_internal_id: candidate.entity,
                    link_type: 'constraint',
                    to_proptype: candidate.type,
                    property_id: candidate.property,
                    instance_count: 1,
                    from_subject: constrained_node,
                    to_subject: null
                })
                constrained_node.subqueries.push(SubQuery.construct(constraint_link))
            }
        })
    }
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