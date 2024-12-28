import type { Node, SubjectConstraint } from "./representation";

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