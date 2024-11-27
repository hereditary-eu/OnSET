import type { Api, FuzzyQueryResult, Subject, SubjectLink } from "@/api/client.ts/Api";

export class Node implements Subject {
    subject_id: string;
    label: string;
    spos: Record<string, string[]>;
    subject_type?: string;
    refcount?: number;
    descendants?: Record<string, Subject[]>;
    total_descendants?: number;
    properties?: Record<string, Subject[]>;

    // d3 specific
    x?: number;
    y?: number;
    height?: number;
    width?: number;


    unknown: boolean;
    constructor(node: Subject) {
        for (const key in node) {
            if (Object.prototype.hasOwnProperty.call(node, key)) {
                this[key] = node[key];
            }
        }
        this.x = 0;
        this.y = 0;
        this.height = 75
        this.width = 125
        this.unknown = false;
    }

}
export class UnknownNode extends Node {
    constructor() {
        super({
            subject_id: '--',
            label: '--',
            spos: {},
            subject_type: '--',
            refcount: 0,
            descendants: {},
            total_descendants: 0,
            properties: {},
        });
        this.unknown = true;
    }
}
export class Link implements SubjectLink {
    link_id: number;
    from_id: string;
    link_type: string;
    to_id: string;
    to_proptype: string;
    property_id: string;
    from_subject: Node;
    to_subject: Node | UnknownNode;
    constructor(link: SubjectLink) {
        for (const key in link) {
            if (Object.prototype.hasOwnProperty.call(link, key)) {
                this[key] = link[key];
            }
        }
        this.from_subject = new Node(link.from_subject);
        this.to_subject = link.to_subject ? new Node(link.to_subject) : new UnknownNode();
    }

}
export class MixedResponse implements FuzzyQueryResult {
    link: Link;
    subject: Node;
    score: number;
    constructor(result: FuzzyQueryResult) {
        for (const key in result) {
            if (Object.prototype.hasOwnProperty.call(result, key)) {
                this[key] = result[key];
            }
        }
        this.subject = result.subject ? new Node(result.subject) : null;
        this.link = result.link ? new Link(result.link) : null;
    }
}

export type FuzzyQueryRequest = Parameters<typeof Api.prototype.classes.searchClassesClassesSearchPost>[0]