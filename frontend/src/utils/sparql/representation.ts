import type { Api, FuzzyQueryResult, Subject, SubjectLink } from "@/api/client.ts/Api";
import { CONSTRAINT_HEIGHT, CONSTRAINT_WIDTH, NODE_HEIGHT, NODE_WIDTH } from "./explorer";
export enum ConstraintType{
    STRING = "string",
    NUMBER = "number",
    BOOLEAN = "boolean",
    DATE = "date",
    SUBJECT = "subject"
}
export class Constraint {
    link: Link;
    height: number
    width: number
    constraint_type: ConstraintType;
    constructor() {
        this.height = CONSTRAINT_HEIGHT
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
        console.log("Constructed", constraint, link)
        if (constraint) {
            constraint.link = link;
        }
        return constraint;
    }
}
export class SubjectConstraint extends Constraint {
    subject_id: string;
    constructor(subject_id: string) {
        super();
        this.subject_id = subject_id;
        this.constraint_type = ConstraintType.SUBJECT
    }
    filterExpression(property: string): string {
        return `${property} = "${this.subject_id}"`;
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
export class StringConstraint extends Constraint {
    value: string;
    type: StringConstraintType;
    constructor(value: string, type: StringConstraintType) {
        super();
        this.value = value;
        this.type = type;
        this.constraint_type = ConstraintType.STRING
    }
    filterExpression(property: string): string {
        switch (this.type) {
            case StringConstraintType.EQUALS:
                return `${property} ="${this.value}"`;
            case StringConstraintType.CONTAINS:
                return `contains(${property},"${this.value})"`;
            case StringConstraintType.STARTSWITH:

                return `strStarts(${property},"${this.value}")`;
            case StringConstraintType.ENDSWITH:
                return `strEnds(${property},"${this.value}")`;
            case StringConstraintType.REGEX:
                return `regex(${property} ,"${this.value}")`;
        }
    }
    static validPropType(propType: string): boolean {
        return propType == 'xsd:string' ||
            propType == 'xsd:langString'
    }

}
export enum NumberConstraintType {
    EQUALS = "equals",
    LESS = "less",
    GREATER = "greater",
}
export class NumberConstraint extends Constraint {
    value: number;
    type: NumberConstraintType;
    constructor(value: number, type: NumberConstraintType) {
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
            propType == 'xsd:float' ||
            propType.includes('year') ||
            propType.includes('minutes') ||
            propType.includes('centimetre') ||
            propType.includes('kilogram')
    }
}
export class BooleanConstraint extends Constraint {
    value: boolean;
    constructor(value: boolean) {
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
export class DateConstraint extends Constraint {
    value: Date;
    type: NumberConstraintType;
    constructor(value: Date, type: NumberConstraintType) {
        super();
        this.value = value;
        this.type = type;
        this.constraint_type = ConstraintType.DATE
    }
    filterExpression(property: string): string {
        //TODO: test!!
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
        return propType == 'xsd:date'
    }
}

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


    from_links: Link[];
    to_links: Link[];

    property_constraints?: Constraint[];

    unknown: boolean;
    constructor(node: Subject) {
        for (const key in node) {
            if (Object.prototype.hasOwnProperty.call(node, key)) {
                this[key] = node[key];
            }
        }
        this.x = 0;
        this.y = 0;
        this.height = NODE_HEIGHT
        this.width = NODE_WIDTH
        this.unknown = false;
        this.to_links = [];
        this.from_links = [];
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
    label: string;

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