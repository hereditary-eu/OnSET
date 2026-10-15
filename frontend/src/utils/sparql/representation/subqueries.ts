

import type { Api, Instance } from "@/api/client.ts/Api";
import { CONSTRAINT_HEIGHT, CONSTRAINT_WIDTH, toVar } from "../helpers";

import { ReconstructableClass, registerClass } from "../../parsing";
import type { Diffable } from "../diff";
import type { Link } from "./graph";

export enum SubQueryType {
    STRING = "string",
    NUMBER = "number",
    BOOLEAN = "boolean",
    DATE = "date",
    SUBJECT = "subject",
    QUERY_PROP = "query_prop",
    INSTANCE_PROP = "instance_prop",

    VECTOR_SORT = "vector_sort",
    IMAGE_PROP = "image_prop"
}
class SubqueryRegisterEntry {
    constructor(public name: string,
        public c: any,
        public allowed_prop_types: string[] = [],
        public allowed_filters: string[] = [],) { }
}

interface SubQueryClass {
    new(): SubQuery;
}

const registeredSubQueryClasses: Record<string, SubqueryRegisterEntry> = {}
export function registerSubquery<C extends SubQueryClass>(allowed_prop_types: string[], allowed_filters: string[] | null = null): (constructor: C) => C {
    if (!allowed_filters) {
        allowed_filters = allowed_prop_types
    }
    return (constructor: C) => {
        constructor.prototype.__parseregister = constructor.name
        registerClass(constructor)
        registeredSubQueryClasses[constructor.name] = new SubqueryRegisterEntry(constructor.name, constructor, allowed_prop_types, allowed_filters)
        let anyparam = constructor as { new(...args: any[]): {} }
        return class extends anyparam {
            __parseregister = constructor.name
        } as unknown as C
    }
}

@registerClass
export class SubQuery implements Diffable, ReconstructableClass {
    link: Link;
    _height: number;
    _width: number;
    constraint_type: SubQueryType;
    id: string | number;
    static allowed_prop_types = []
    static id_counter: number = 0;
    constructor() {
        this._width = CONSTRAINT_WIDTH
        this._height = CONSTRAINT_HEIGHT / 2
        this.id = SubQuery.id_counter++
    }
    postConstruct(): void {
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
    static validFilter(propType: string): boolean {
        for (let key in registeredSubQueryClasses) {
            let entry = registeredSubQueryClasses[key]
            if (entry.allowed_filters.includes(propType)) {
                return true
            }
        }
        return false
    }

    static constructFilter(link: Link): SubQuery {
        let constraint: SubQuery | null = null
        for (let key in registeredSubQueryClasses) {
            let entry = registeredSubQueryClasses[key]
            if (entry.allowed_filters.includes(link.to_proptype)) {
                constraint = new entry.c() as SubQuery
                break
            }
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


await OntoConfig.ensureConfig()
export const ALLOWED_IMAGE_PROP_TYPES = [
    ...OntoConfig.config.config.multimodal.image_types
]
console.log("Allowed image prop types", ALLOWED_IMAGE_PROP_TYPES)



@registerSubquery(ALLOWED_IMAGE_PROP_TYPES, [])
export class QueryProp extends SubQuery {
    property_id: string
    constructor() {
        super();
        this.constraint_type = SubQueryType.QUERY_PROP
    }
    get height(): number {
        return CONSTRAINT_HEIGHT / 2 
    }
    static validProp(propType: string): boolean {
        console.log("Checking if propType is valid for query prop", propType, registeredSubQueryClasses)
        for (let key in registeredSubQueryClasses) {
            let entry = registeredSubQueryClasses[key]
            if (entry.allowed_prop_types.includes(propType)) {
                return true
            }
        }
        return false
    }
    static constructProp(link: Link): QueryProp {
        let query_prop = new QueryProp();
        query_prop.link = link;
        query_prop.property_id = link.property_id;
        return query_prop;
    }
}


@registerSubquery([])
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
}
export enum StringConstraintType {
    EQUALS = "equals",
    NEQUALS = "!=",
    CONTAINS = "contains",
    STARTSWITH = "startswith",
    ENDSWITH = "endswith",
    REGEX = "regex",
}

@registerSubquery([
    'xsd:string',
    'rdf:langString',
    'rdfs:label',
    'rdf:PlainLiteral'
])
export class StringConstraint extends SubQuery {
    value: string;
    type: StringConstraintType;
    constructor(value: string = "", type: StringConstraintType = StringConstraintType.CONTAINS) {
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

}
export enum NumberConstraintType {
    EQUALS = "equals",
    LESS = "less",
    GREATER = "greater",
}

@registerSubquery(
    [
        'xsd:double',
        'xsd:integer',
        'xsd:float',
        'xsd:nonNegativeInteger',
        'xsd:gYear',
        'xsd:gYearMonth',
        'xsd:gMonthDay',
        'xsd:gDay',
        'xsd:gMonth',
        'xsd:duration',
        'xsd:yearMonthDuration',
        'xsd:dayTimeDuration',
    ]
)
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
    static validFilter(propType: string): boolean {
        return registeredSubQueryClasses[NumberConstraint.name].allowed_filters.includes(propType) ||
            propType.includes('year') ||
            propType.includes('Year') ||
            propType.includes('minutes') ||
            propType.includes('minute') ||
            propType.includes('centimetre') ||
            propType.includes('kilogram')
    }
}


@registerSubquery([
    'xsd:boolean'
])
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
}

@registerSubquery([
    'xsd:date',
    'xsd:dateTime'
])
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
}
import { OntoConfig } from "../ontoconfig";

export enum VectorSortModality {
    IMAGE = "image",
    TEXT = "text",
}
export enum VectorSortDirection {
    ASCENDING = "ascending",
    DESCENDING = "descending",
}
export enum VectorSortDistance {
    COSINE = "cosine",
    EUCLIDEAN = "euclidean",
    MANHATTAN = "manhattan",
}
@registerClass
export class VectorData {
    data: number[];
    type: string;
    shape: number[];
    static propType: string = "<https://w3id.org/rdf-tensor/datatypes#NumericDataTensor>"
    constructor(data: number[] = [], type: string = "float32", shape: number[] = []) {
        this.data = data;
        this.type = type;
        this.shape = shape.length > 0 ? shape : [data.length];

    }
    toString(): string {
        let json_str = JSON.stringify({
            "type": this.type,
            "shape": this.shape,
            "data": this.data,
        })
        json_str = json_str.replace(/"/g, '\\"')
        return `"${json_str}"^^${VectorData.propType}`
    }

    postConstruct(): void {
        
    }

}


@registerSubquery([
    VectorData.propType,
])
export class VectorSort extends SubQuery {
    modality: VectorSortModality;
    direction: VectorSortDirection;
    distance: VectorSortDistance;
    vector: number[] | null = null;

    input_state: {
        image: string | null;
        text: string | null;
    } = {
            image: null,
            text: null,
        }
    constructor(modality: VectorSortModality = VectorSortModality.IMAGE, direction: VectorSortDirection = VectorSortDirection.DESCENDING, distance: VectorSortDistance = VectorSortDistance.COSINE) {
        super();
        this.modality = modality;
        this.direction = direction;
        this.distance = distance;
        this.constraint_type = SubQueryType.VECTOR_SORT
    }
    set height(value: number) {
        // no-op, height is determined by modality
    }
    get height(): number {
        switch (this.modality) {
            case VectorSortModality.IMAGE:
                return CONSTRAINT_HEIGHT * 4
            case VectorSortModality.TEXT:
                return CONSTRAINT_HEIGHT * 1
        }
    }

    async reloadVectorFromState(api: Api<any>) {
        this.vector = null
        let vector_resp = null
        switch (this.modality) {
            case VectorSortModality.TEXT:
                if (this.input_state.text && this.input_state.text.length > 0) {
                    vector_resp = await api.search.encodeTextSearchEncodeTextPost(this.input_state.text)
                }
                break
            case VectorSortModality.IMAGE:
                if (this.input_state.image) {
                    vector_resp = await api.search.encodeImageSearchEncodeImagePost(this.input_state.image)
                }
                break
        }
        this.vector = vector_resp.data.data
    }
    expression(property: string): string {
        let distance_func = ""
        switch (this.distance) {
            case VectorSortDistance.COSINE:
                distance_func = "dtf:cosineSimilarity"
                break;
            case VectorSortDistance.EUCLIDEAN:
                distance_func = "dtf:euclideanDistance"
                break;
            case VectorSortDistance.MANHATTAN:
                distance_func = "dtf:manhattanDistance"
                break;
        }
        return `BIND(${distance_func}(${property}, ${this.vectorExpression()}) AS ?sim_${toVar(this.id)})`
    }
    postQueryExpression(property: string): string {
        let order_dir = this.direction == VectorSortDirection.ASCENDING ? "ASC" : "DESC"
        return `ORDER BY ${order_dir}(?sim_${toVar(this.id)})`
    }
    static validFilter(propType: string): boolean {
        // console.log("Checking if propType is valid for vector sort", propType, VectorData.propType)
        return propType == VectorData.propType
    }
    vectorExpression(): string {
        if (!this.vector) {
            return ""
        } else {
            return new VectorData(this.vector).toString()
        }

    }
}
