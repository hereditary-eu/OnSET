import type { Candidates, EntitiesRelations } from "@/api/client.ts/Api";
import { Link, Node, type SubjectConstraint } from "./representation";
import { NodeLinkRepository } from "./store";
import Constraint from "@/components/explore/elements/Constraint.vue";
import { reactive } from "vue";

export enum NodeSide {
    TO = 'to_link',
    FROM = 'from_link',
    PROP = 'prop',
    DETAIL = 'detail'
}
export class OutlinkSelectorOpenEvent {
    node: Node;
    side: NodeSide;

}
export class InstanceSelectorOpenEvent {
    node: Node;
    constraint: SubjectConstraint
}
export const NODE_WIDTH = 150
export const NODE_HEIGHT = 64
export const LINK_WIDTH = 75
export const CONSTRAINT_WIDTH = 250
export const CONSTRAINT_HEIGHT = 75
export const CONSTRAINT_PADDING = 5


export enum DisplayMode {
    SELECT = 'select',
    EDIT = 'edit',
    RESULTS = 'results',
    RESULT_INTERACTIVE = 'result_interactive',
}
export function mapERLToStore(step: EntitiesRelations) {

    let store = new NodeLinkRepository()
    store.nodes = step.entities.map((entity) => {
        let mapped_node = new Node({
            subject_id: entity.type,
            label: entity.type,
            internal_id: entity.identifier
        })
        mapped_node.height = NODE_HEIGHT / 2
        return mapped_node
    })

    step.relations.forEach((relation, i) => {
        let from_subject = store.nodes.find((n) => n.internal_id == relation.entity)
        if (!from_subject) {
            from_subject = new Node({
                subject_id: relation.entity,
                label: relation.entity,
                internal_id: relation.entity
            })
            from_subject.height = NODE_HEIGHT / 2
        }
        let to_subject = store.nodes.find((n) => n.internal_id == relation.target)
        if (!to_subject) {
            to_subject = new Node({
                subject_id: relation.target,
                label: relation.target,
                internal_id: relation.target
            })
            to_subject.height = NODE_HEIGHT / 2
        }
        store.addOutlink(
            new Link({
                link_id: i,
                from_id: relation.entity,
                to_id: relation.target,
                label: relation.relation,
                from_internal_id: relation.entity,
                to_internal_id: relation.target,
                link_type: 'relation',
                to_proptype: null,
                property_id: null,
                instance_count: 1,
                from_subject,
                to_subject
            }), from_subject, to_subject, NodeSide.TO
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
                constrained_node.property_constraints.push(Constraint.construct(constraint_link))
            }
        })
    }
    store.nodes = store.nodes.map(node => reactive(node))
    store.links = store.links.map(link => reactive(link))
    return store
}