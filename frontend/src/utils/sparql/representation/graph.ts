


import type { Subject, Property, SubjectLink, Api } from "@/api/client.ts/Api";
import { registerClass } from "@/utils/parsing";
import { NODE_HEIGHT, NODE_WIDTH, toVar, OpenEventType } from "../helpers";
import { NodeLinkRepository } from "../store";
import { readableName } from "../querymapper";
import type { SubQuery } from "./subqueries";
import { DiffList, SubQueryDiff, type Diffable } from "../diff";


export enum NodeState {
    NORMAL = "normal",
    SELECTED = "selected",
    HOVERED = "hovered",
    DELETION_IMMINENT = "deletion_imminent",
    ADDED = "added",
    REMOVED = "removed",
    CHANGED = "changed",
    ATTACHING = "attaching",
}
export enum LinkType {
    STRUCTURAL = "structural",
    SIMILARITY = "similarity",
}
@registerClass
export class LinkTriplet {
    from_id: string;
    link_id: string;
    to_id: string;
    semantic_link_type: LinkType;
    constructor(link_type: LinkType = LinkType.STRUCTURAL) {
        this.semantic_link_type = link_type;
    }
}
@registerClass
export class QuerySet {
    //from internal_id to subject_id
    nodes: Record<string, SubjectNode>;
    link_triplets: LinkTriplet[];

    filter: SubQuery[];

    output_ids: string[] = [];

    constructor() {
        this.nodes = {};
        this.link_triplets = [];
        this.filter = [];
        this.output_ids = [];
    }
    merge(other: QuerySet) {
        for (let key in other.nodes) {
            if (!(key in this.nodes)) {
                this.nodes[key] = other.nodes[key]
            }
        }
        this.filter.push(...other.filter)
        this.output_ids.push(...other.output_ids)
        for (let triplet of other.link_triplets) {
            if (this.link_triplets.filter(t => t.from_id == triplet.from_id && t.link_id == triplet.link_id && t.to_id == triplet.to_id).length == 0) {
                this.link_triplets.push(triplet)
            }
        }
        return this
    }
}
export interface QuerySetGenerator {
    querySet(): QuerySet
}
let internal_id_counter: number = 0;
@registerClass
export class SubjectNode implements Subject, Diffable {
    subject_id: string;
    label: string;
    spos?: Record<string, Property>;
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



    subqueries?: SubQuery[];
    internal_id: string;
    internal_id_cnt: number;
    unknown: boolean;
    state: NodeState = NodeState.NORMAL

    constructor(node?: SubjectNode | Subject) {
        if (!(node instanceof SubjectNode)) {
            this.x = 0;
            this.y = 0;
            this.height = NODE_HEIGHT
            this.width = NODE_WIDTH
            this.unknown = false;
            this.subqueries = [];
            this.state = NodeState.NORMAL;
            this.internal_id_cnt = ++internal_id_counter;
            this.internal_id = `node_${this.internal_id_cnt}`;
        }
        for (const key in node) {
            if (Object.prototype.hasOwnProperty.call(node, key)) {
                this[key] = node[key];
            }
        }

    }

    labelId(): string {
        return `?lbl_${toVar(this.internal_id)}`
    }
    outputId(): string {
        return `?${toVar(this.internal_id)}`
    }

    computeConstraintOffsets(padding: number) {

        if (!this.subqueries) {
            return []
        }
        let constraints = this.subqueries.filter(constr => constr != null).map((constraint) => {
            return {
                constraint: constraint,
                y: 0,
                extend_path: 0
            }
        })
        // if (constraints.length > 0) {
        //     constraints[0].first_prop = true
        // }
        let y_pos = this.height + padding
        let last_height = 0
        for (let constr of constraints) {
            constr.y = y_pos
            y_pos += constr.constraint.height + padding
            if (last_height == 0) {
                constr.extend_path = padding
            } else {
                constr.extend_path = last_height / 2 + padding
            }
            last_height = constr.constraint.height
        }
        return constraints
    }

    changed(other: this): boolean {
        let subquery_diff = new DiffList(this.subqueries || [], other.subqueries || [], SubQueryDiff)
        if (subquery_diff.added.length > 0 || subquery_diff.removed.length > 0 || subquery_diff.changed.length > 0) {
            return true
        }
        return false
        return this.subject_id != other.subject_id ||
            this.label != other.label ||
            // this.spos != other.spos ||
            this.subject_type != other.subject_type ||
            this.refcount != other.refcount ||
            // this.descendants != other.descendants ||
            this.total_descendants != other.total_descendants //||
        // this.properties != other.properties;
    }
    get id(): string | number {
        return this.internal_id
    }
}
@registerClass
export class UnknownNode extends SubjectNode {
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
export enum LinkQuantifierType {
    ONE_OR_MORE = "+",
    ZERO_OR_MORE = "*",
    ZERO_OR_ONE = "?",
    BETWEEEN = "BETWEEN",
    EXACTLY = "EXACTLY",
}
@registerClass
export class LinkQuantifier {
    min: number | null;
    max: number | null;
    type: LinkQuantifierType;
    constructor(type: LinkQuantifierType = LinkQuantifierType.ONE_OR_MORE, min: number | null = null, max: number | null = null) {
        this.type = type;
        this.min = min;
        this.max = max;
    }
    toString(): string {
        if (this.type == LinkQuantifierType.EXACTLY) {
            return `{${this.min}}`;
        } else if (this.type == LinkQuantifierType.BETWEEEN) {
            return `{${this.min},${this.max}}`;
        } else if (this.type == LinkQuantifierType.ZERO_OR_ONE) {
            return `?`;
        } else if (this.type == LinkQuantifierType.ZERO_OR_MORE) {
            return `+`;
        } else if (this.type == LinkQuantifierType.ONE_OR_MORE) {
            return `*`;
        }
        return "";
    }
}
@registerClass
export class Link<N extends Subject = Subject> implements SubjectLink, Diffable {

    link_id: number;
    from_id: string;
    link_type: string;
    to_id: string;
    to_proptype: string | null;
    property_id: string | null;

    semantic_link_type: LinkType = LinkType.STRUCTURAL;

    allow_arbitrary: boolean = false;
    quantifier: LinkQuantifier | null = null;

    from_internal_id: string;
    to_internal_id: string;

    from_subject: N | SubjectNode;
    to_subject: N | UnknownNode;

    initialized: boolean = true;
    static betweenNodes(from: SubjectNode, to: SubjectNode, link_id = "-"): NodeLinkRepository<SubjectNode, Link> {
        let repository = new NodeLinkRepository<SubjectNode, Link>([from, to], []);
        let link = new Link({
            from_id: from.subject_id,
            to_id: to.subject_id,
            from_internal_id: from.internal_id,
            to_internal_id: to.internal_id,
            link_type: 'relation',
            link_id: -1,
            label: `*`,
            to_proptype: null,
            property_id: null,
            instance_count: 1,
            from_subject: from,
            to_subject: to,
            allow_arbitrary: false,
            initialized: false,
            quantifier: null,
        });
        link.initialized = false
        repository.addOutlink(link, from, to, OpenEventType.TO);
        return repository;


    }
    constructor(link?: SubjectLink | Link) {
        if (link) {
            for (const key in link) {
                if (Object.prototype.hasOwnProperty.call(link, key)) {
                    this[key] = link[key];
                }
            }
            if (!(link.from_subject instanceof SubjectNode)) {
                this.from_subject = new SubjectNode(link.from_subject);
            }
            if (!(link.to_subject instanceof SubjectNode)) {
                this.to_subject = link.to_subject ? new SubjectNode(link.to_subject) : new UnknownNode();
            }
        }
        this.link_id = internal_id_counter++
    }
    instance_count: number;
    label: string;
    outputId(): string {
        return `?p_${toVar(this.link_id)}`
    }
    identifier(): string {
        return `${this.from_internal_id}-${this.link_id}-${this.to_internal_id}`
    }
    queryId(): string {

        let link_var = this.property_id
        if (this.allow_arbitrary) {
            link_var = this.outputId();
        }
        if (this.quantifier) {
            link_var += this.quantifier.toString();
        }
        // console.log("Query ID for link", this, "is", link_var)
        return link_var
    }
    changed(other: this): boolean {
        return this.from_id != other.from_id ||
            this.to_id != other.to_id ||
            this.link_type != other.link_type ||
            this.to_proptype != other.to_proptype ||
            this.property_id != other.property_id;
    }
    get id(): string | number {
        return this.link_id
    }
}
export type FuzzyQueryRequest = Parameters<typeof Api.prototype.classes.searchClassesClassesSearchPost>[0]

@registerClass
export class InstanceNode extends SubjectNode {
    instance_label: string = null
    instance_id: string = null
    interactive_clone: InstanceNode | null = null
    expanded: boolean = false
    instance_data: Record<string, string> = null
    constructor(base_node?: SubjectNode | InstanceNode, instance_data?: Record<string, string>) {
        super(base_node)
        if (!base_node) {
            this.instance_data = instance_data || {}
        } else {
            this.instance_data = instance_data || (base_node as InstanceNode).instance_data || {}
        }
        this.instance_id = this.instance_data[this.outputId().replace('?', '')]
        this.instance_label = this.instance_data[this.labelId().replace('?', '')]
        this.instance_label = readableName(this.instance_id, this.instance_label)
    }
    get id() {
        return this.instance_id
    }
}
@registerClass
export class InstanceLink extends Link {
    instance_label: string = null
    instance_id: string = null
    constructor(base_link: Link = null, public instance_data: Record<string, string> = null) {
        super(base_link)
        if (!base_link) {
            this.instance_data = instance_data || {}
        } else {
            this.instance_data = instance_data || (base_link as InstanceLink).instance_data || {}
        }
        this.instance_id = this.instance_data[this.outputId().replace('?', '')]
        // this.instance_label = this.instance_data[this.outputId().replace('?', '')]
        this.instance_label = readableName(this.instance_id, this.label)
    }
    get id() {
        return this.link_id
    }
}