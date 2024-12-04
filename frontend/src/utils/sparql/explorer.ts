import type { Node } from "./representation";

export enum NodeSide {
    TO = 'to_link',
    FROM = 'from_link',
    PROP = 'prop'
}
export class OutlinkSelectorOpenEvent {
    node: Node;
    side: NodeSide;

}
export const NODE_WIDTH = 150
export const NODE_HEIGHT = 64
export const LINK_WIDTH = 75
export const CONSTRAINT_WIDTH = 250
export const CONSTRAINT_HEIGHT = 50