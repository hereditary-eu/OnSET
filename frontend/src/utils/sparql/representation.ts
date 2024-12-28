import type { Api, FuzzyQueryResult, Instance, Property, Subject, SubjectLink } from "@/api/client.ts/Api";
import { CONSTRAINT_HEIGHT, CONSTRAINT_WIDTH, NODE_HEIGHT, NODE_WIDTH } from "./helpers";
import { isProxy, toRaw } from "vue";
import { jsonProperty, Serializable } from "ts-serializable";
import { registerClass } from "../parsing";



export enum ConstraintType {
    STRING = "string",
    NUMBER = "number",
    BOOLEAN = "boolean",
    DATE = "date",
    SUBJECT = "subject"
}
@registerClass
export class Constraint {
    link: Link;
    height: number
    width: number
    constraint_type: ConstraintType;
    constructor() {
        this.height = CONSTRAINT_HEIGHT / 2
        this.width = CONSTRAINT_WIDTH
    }
    static validPropType(propType: string): boolean {
        return false;
    }
    static construct(link: Link): Constraint {
        let constraint = null

        if (StringConstraint.validPropType(link.to_proptype)) {
            constraint = new StringConstraint("", StringConstraintType.CONTAINS);
        } else if (NumberConstraint.validPropType(link.to_proptype)) {
            constraint = new NumberConstraint(0, NumberConstraintType.GREATER);
        } else if (BooleanConstraint.validPropType(link.to_proptype)) {
            constraint = new BooleanConstraint(true);
        } else if (DateConstraint.validPropType(link.to_proptype)) {
            constraint = new DateConstraint(new Date(), NumberConstraintType.GREATER);
        }
        if (constraint) {
            constraint.link = link;
        }
        return constraint;
    }
    filterExpression(property: string): string {
        return ""
    }
    expression(property: string): string {
        return this.filterExpression(property);
    }
}
@registerClass
export class SubjectConstraint extends Constraint {
    instance: Instance;
    constructor() {
        super();
        this.height = CONSTRAINT_HEIGHT / 2
        this.instance = null;
        this.constraint_type = ConstraintType.SUBJECT
    }
    filterExpression(property: string): string {
        return `${property} = "${this.instance.id}"`;
    }
    static validPropType(propType: string): boolean {
        return false
    }
}
export enum StringConstraintType {
    EQUALS = "equals",
    CONTAINS = "contains",
    STARTSWITH = "startswith",
    ENDSWITH = "endswith",
    REGEX = "regex",
}
@registerClass
export class StringConstraint extends Constraint {
    value: string;
    type: StringConstraintType;
    constructor(value: string = null, type: StringConstraintType = StringConstraintType.CONTAINS) {
        super();
        this.height = CONSTRAINT_HEIGHT / 1.3
        this.value = value;
        this.type = type;
        this.constraint_type = ConstraintType.STRING
    }
    filterExpression(property: string): string {
        switch (this.type) {
            case StringConstraintType.EQUALS:
                return `${property} ="${this.value}"`;
            case StringConstraintType.CONTAINS:
                return `CONTAINS(${property},"${this.value}")`;
            case StringConstraintType.STARTSWITH:
                return `STRSTARTS(${property},"${this.value}")`;
            case StringConstraintType.ENDSWITH:
                return `STRENDS(${property},"${this.value}")`;
            case StringConstraintType.REGEX:
                return `REGEX(${property} ,"${this.value}")`;
        }
    }
    static validPropType(propType: string): boolean {
        return propType == 'xsd:string' ||
            propType == 'rdf:langString'
            || propType == 'rdfs:label'
    }

}
export enum NumberConstraintType {
    EQUALS = "equals",
    LESS = "less",
    GREATER = "greater",
}
@registerClass
export class NumberConstraint extends Constraint {
    value: number;
    type: NumberConstraintType;
    constructor(value: number = 0, type: NumberConstraintType = NumberConstraintType.GREATER) {
        super();
        this.value = value;
        this.type = type;
        this.constraint_type = ConstraintType.NUMBER
    }
    filterExpression(property: string): string {
        switch (this.type) {
            case NumberConstraintType.EQUALS:
                return `${property} = ${this.value}`;
            case NumberConstraintType.LESS:
                return `${property} < ${this.value}`;
            case NumberConstraintType.GREATER:
                return `${property} > ${this.value}`;
        }
    }
    static validPropType(propType: string): boolean {
        return propType == 'xsd:double' ||
            propType == 'xsd:integer' ||
            propType == 'xsd:nonNegativeInteger' ||
            propType == 'xsd:float' ||
            propType.includes('year') ||
            propType.includes('Year') ||
            propType.includes('minutes') ||
            propType.includes('minute') ||
            propType.includes('centimetre') ||
            propType.includes('kilogram')
    }
}

@registerClass
export class BooleanConstraint extends Constraint {
    value: boolean;
    constructor(value: boolean = false) {
        super();
        this.value = value;
        this.constraint_type = ConstraintType.BOOLEAN
    }
    filterExpression(property: string): string {
        return `${property} = ${this.value}`;
    }
    static validPropType(propType: string): boolean {
        return propType == 'xsd:boolean'
    }
}
@registerClass
export class DateConstraint extends Constraint {
    value: Date;
    type: NumberConstraintType;
    constructor(value: Date = new Date(), type: NumberConstraintType = NumberConstraintType.GREATER) {
        super();
        this.value = value;
        this.type = type;
        this.constraint_type = ConstraintType.DATE
    }
    valueExpression(): string {
        return `"${this.value.toISOString()}"^^xsd:dateTime`
    }
    filterExpression(property: string): string {
        //TODO: test!!
        switch (this.type) {
            case NumberConstraintType.EQUALS:
                return `${property} = ${this.valueExpression()}`;
            case NumberConstraintType.LESS:
                return `${property} < ${this.valueExpression()}`;
            case NumberConstraintType.GREATER:
                return `${property} > ${this.valueExpression()}`;
        }

    }
    static validPropType(propType: string): boolean {
        return propType == 'xsd:date'
    }
}
@registerClass
export class LinkTriplet {
    from_id: string;
    link_id: string;
    to_id: string;
}
@registerClass
export class QuerySet {
    //from internal_id to subject_id
    nodes: Record<string, Node>;
    link_triplets: LinkTriplet[];

    filter: Constraint[];

    constructor() {
        this.nodes = {};
        this.link_triplets = [];
        this.filter = [];
    }
}
let internal_id_counter: number = 0;
@registerClass
export class Node implements Subject {
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


    from_links: Link[];
    to_links: Link[];

    property_constraints?: Constraint[];
    internal_id: string;
    unknown: boolean;
    deletion_imminent: boolean

    constructor(node?: Node | Subject) {
        if (!(node instanceof Node)) {
            this.x = 0;
            this.y = 0;
            this.height = NODE_HEIGHT
            this.width = NODE_WIDTH
            this.unknown = false;
            this.to_links = [];
            this.from_links = [];
            this.property_constraints = [];
            this.deletion_imminent = false;
            this.internal_id = `node_${++internal_id_counter}`;
        }
        for (const key in node) {
            if (Object.prototype.hasOwnProperty.call(node, key)) {
                this[key] = node[key];
            }
        }

    }

    label_id(): string {
        return `?lbl_${this.internal_id}`
    }
    output_id(): string {
        return `?${this.internal_id}`
    }
    generateQuery(limit: number | null = 100, skip: number | null = null): string {
        let set = this.querySet()
        let output_names = Object.values(set.nodes).map(nd => nd.output_id())
        let output_labels = Object.values(set.nodes).map(nd => nd.label_id())
        output_labels.push(...set.filter.map((constraint) => constraint.link.output_id()))
        let query = `SELECT DISTINCT ${output_names.join(" ")} ${output_labels.join(" ")} WHERE {`

        for (let link of set.link_triplets) {
            query += `\n${link.from_id} ${link.link_id} ${link.to_id}.`
        }

        for (let node of Object.values(set.nodes)) {
            if (set.nodes.hasOwnProperty(node.internal_id)) {
                // console.log(internal_id, set.internal_ids[internal_id])
                query += `\n${node.output_id()} a ${node.subject_id}.
OPTIONAL {${node.output_id()} rdfs:label ${node.label_id()}.}`
                query += `\nOPTIONAL {${node.output_id()} foaf:name ${node.label_id()}.}`
            }
        }
        for (let constraint of set.filter) {
            if (constraint instanceof SubjectConstraint) {
                if (constraint.instance) {
                    query += `\nFILTER(${constraint.link.from_subject.output_id()}=${constraint.instance.id})`
                }
            } else {
                let constrained_id = `?prop_${constraint.link.link_id}`
                query += `\n${constraint.link.from_subject.output_id()} ${constraint.link.property_id} ${constrained_id}.
    FILTER(${constraint.expression(constrained_id)})`
            }
        }
        query += "\n}"
        query += "\nORDER BY " + output_labels.join(" ")
        if (limit) {
            query += `\nLIMIT ${limit}`
        }
        if (skip) {
            query += `\nOFFSET ${skip}`
        }
        return query
    }
    querySet(): QuerySet {
        let set = new QuerySet()
        set.nodes[this.internal_id] = this
        set.filter.push(...this.property_constraints)
        let subsets = []
        for (let to_link of this.to_links) {
            let subset = to_link.to_subject.querySet()
            set.nodes = Object.assign(set.nodes, subset.nodes)
            set.filter.push(...subset.filter)
            set.link_triplets.push(...subset.link_triplets)
            set.link_triplets.push({
                from_id: this.output_id(),
                link_id: to_link.property_id,
                to_id: to_link.to_subject.output_id()
            })
        }
        for (let from_link of this.from_links) {
            let subset = from_link.from_subject.querySet()
            set.nodes = Object.assign(set.nodes, subset.nodes)
            set.filter.push(...subset.filter)
            set.link_triplets.push(...subset.link_triplets)
            set.link_triplets.push({
                from_id: from_link.from_subject.output_id(),
                link_id: from_link.property_id,
                to_id: this.output_id()
            })
        }
        return set
    }

    computeConstraintOffsets(padding: number) {

        if (!this.property_constraints) {
            return []
        }
        let constraints = this.property_constraints.filter(constr => constr != null).map((constraint) => {
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
}
@registerClass
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
@registerClass
export class Link implements SubjectLink {
    link_id: number;
    from_id: string;
    link_type: string;
    to_id: string;
    to_proptype: string;
    property_id: string;
    from_subject: Node;
    to_subject: Node | UnknownNode;
    constructor(link?: SubjectLink) {
        if (link) {
            for (const key in link) {
                if (Object.prototype.hasOwnProperty.call(link, key)) {
                    this[key] = link[key];
                }
            }
            if (!(link.from_subject instanceof Node)) {
                this.from_subject = new Node(link.from_subject);
            }
            if (!(link.to_subject instanceof Node)) {
                this.to_subject = link.to_subject ? new Node(link.to_subject) : new UnknownNode();
            }
        }
        this.link_id = internal_id_counter++
    }
    instance_count: number;
    label: string;
    output_id(): string {
        return `?prop_${this.link_id}`
    }
}
@registerClass
export class MixedResponse implements FuzzyQueryResult {
    link: Link;
    subject: Node;
    score: number;
    constructor(result: FuzzyQueryResult = null) {
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
