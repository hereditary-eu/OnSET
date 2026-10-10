

import type { Api, Instance } from "@/api/client.ts/Api";
import { CONSTRAINT_HEIGHT, CONSTRAINT_WIDTH, toVar } from "../helpers";

import { registerClass } from "../../parsing";
import type { Diffable } from "../diff";
import type { Link } from "./graph";
import { VectorSort, VectorSortDirection, VectorSortDistance, VectorSortModality } from "./vectors";

export enum SubQueryType {
    STRING = "string",
    NUMBER = "number",
    BOOLEAN = "boolean",
    DATE = "date",
    SUBJECT = "subject",
    QUERY_PROP = "query_prop",

    VECTOR_SORT = "vector_sort"
}

@registerClass
export class SubQuery implements Diffable {
    link: Link;
    _height: number;
    _width: number;
    constraint_type: SubQueryType;
    id: string | number;
    static id_counter: number = 0;
    constructor() {
        this._width = CONSTRAINT_WIDTH
        this._height = CONSTRAINT_HEIGHT/2
        this.id = SubQuery.id_counter++
    }
    get height(): number {
        return this._height
    }
    set height(value: number) {
        this._height = value
    }
    get width(): number {
        return this._width
    }
    set width(value: number) {
        this._width = value
    }
    changed(other: Diffable): boolean {
        const testvar = "?test"
        return this.filterExpression(testvar) != (other as SubQuery).filterExpression(testvar)!;
    }
    propVar(): string {
        return this.link.outputId()
    }
    static validPropType(propType: string): boolean {
        return false;
    }
    static async construct(link: Link): Promise<SubQuery> {
        let constraint = null
        if (StringConstraint.validPropType(link.to_proptype)) {
            constraint = new StringConstraint("", StringConstraintType.CONTAINS);
        } else if (NumberConstraint.validPropType(link.to_proptype)) {
            constraint = new NumberConstraint(0, NumberConstraintType.GREATER);
        } else if (BooleanConstraint.validPropType(link.to_proptype)) {
            constraint = new BooleanConstraint(true);
        } else if (DateConstraint.validPropType(link.to_proptype)) {
            constraint = new DateConstraint(new Date(), NumberConstraintType.GREATER);
        } else if (VectorSort.validPropType(link.to_proptype) || link.to_proptype == "dbo:Image") { //TODO: load config for image type from backend
            constraint = new VectorSort(VectorSortModality.IMAGE, VectorSortDirection.DESCENDING, VectorSortDistance.COSINE);
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
        let filter_expr = this.filterExpression(property)
        if (!filter_expr || filter_expr.length == 0) {
            return ""
        }
        return `FILTER(${this.filterExpression(property)})`;
    }
    postQueryExpression(property: string): string {
        return "";
    }
}

@registerClass
export class QueryProp extends SubQuery {
    property_id: string
    constructor() {
        super();
        this.constraint_type = SubQueryType.QUERY_PROP
    }
    get height(): number {
        return CONSTRAINT_HEIGHT / 2
    }
    static async construct(link: Link): Promise<QueryProp> {
        let query_prop = new QueryProp();
        query_prop.link = link;
        query_prop.property_id = link.property_id;
        return query_prop;
    }
}

@registerClass
export class SubjectConstraint extends SubQuery {
    instance: Instance;
    constructor() {
        super();
        this.height = CONSTRAINT_HEIGHT / 2
        this.instance = null;
        this.constraint_type = SubQueryType.SUBJECT
    }
    filterExpression(property: string): string {
        if (!this.instance) {
            return ``;
        }
        return `${property} = "${this.instance.id}"`;
    }
    static validPropType(propType: string): boolean {
        return false
    }
}
export enum StringConstraintType {
    EQUALS = "equals",
    NEQUALS = "!=",
    CONTAINS = "contains",
    STARTSWITH = "startswith",
    ENDSWITH = "endswith",
    REGEX = "regex",
}
@registerClass
export class StringConstraint extends SubQuery {
    value: string;
    type: StringConstraintType;
    constructor(value: string = null, type: StringConstraintType = StringConstraintType.CONTAINS) {
        super();
        this.height = CONSTRAINT_HEIGHT / 1.3
        this.value = value;
        this.type = type;
        this.constraint_type = SubQueryType.STRING
    }
    filterExpression(property: string): string {
        switch (this.type) {
            case StringConstraintType.EQUALS:
                return `${property} ="${this.value}"`;
            case StringConstraintType.NEQUALS:
                return `${property} != "${this.value}"`;
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
            || propType == 'rdf:PlainLiteral'
    }

}
export enum NumberConstraintType {
    EQUALS = "equals",
    LESS = "less",
    GREATER = "greater",
}
@registerClass
export class NumberConstraint extends SubQuery {
    value: number;
    type: NumberConstraintType;
    constructor(value: number = 0, type: NumberConstraintType = NumberConstraintType.GREATER) {
        super();
        this.value = value;
        this.type = type;
        this.constraint_type = SubQueryType.NUMBER
    }
    filterExpression(property: string): string {
        let filter_cond = ""
        switch (this.type) {
            default:
            case NumberConstraintType.EQUALS:
                filter_cond = `${property} = `;
                break;
            case NumberConstraintType.LESS:
                filter_cond = `${property} < `;
                break;
            case NumberConstraintType.GREATER:
                filter_cond = `${property} > `;
                break;
        }
        filter_cond = `${filter_cond} "${this.value}"^^${this.link.to_proptype}`;
        return filter_cond;
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
export class BooleanConstraint extends SubQuery {
    value: boolean;
    constructor(value: boolean = false) {
        super();
        this.value = value;
        this.constraint_type = SubQueryType.BOOLEAN
    }
    filterExpression(property: string): string {
        return `${property} = ${this.value}`;
    }
    static validPropType(propType: string): boolean {
        return propType == 'xsd:boolean'
    }
}
@registerClass
export class DateConstraint extends SubQuery {
    value: Date;
    type: NumberConstraintType;
    constructor(value: Date | string = new Date(), type: NumberConstraintType = NumberConstraintType.GREATER) {
        super();
        if (typeof value == 'string') {
            this.value = new Date(value as string)
        } else {
            this.value = value as Date;
        }
        this.type = type;
        this.constraint_type = SubQueryType.DATE
    }
    postConstruct() {
        console.log("Postconstruct date constraint", this.value)
        if (typeof this.value == 'string') {
            this.value = new Date(this.value as unknown as string)
        }
    }
    valueExpression(): string {
        let date_str: string | Date = this.value
        if (!(this.value instanceof String)) {
            if (this.value.toISOString instanceof Function) {
                date_str = this.value.toISOString()
            } else {
                console.log("Date value is not a string", this.value)
            }

        }
        return `"${date_str}"^^xsd:dateTime`
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