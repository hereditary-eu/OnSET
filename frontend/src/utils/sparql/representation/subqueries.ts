

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
// --- GROUP BY / aggregates ---
// Every property (subquery) of a node and every node itself may be grouped (GROUP BY its
// variable) or aggregated. As soon as one is, NodeLinkRepository.generateQuery emits an
// aggregate query: grouped variables are projected as they are, all others through an
// aggregate (SAMPLE by default), see AggregationPlan in ../store.ts. Mirrored by the backend
// (assistant/sparql_gen.py, AggregateFunction in assistant/assistant_model.py).
export enum AggregateFunction {
    COUNT = "count",
    COUNT_DISTINCT = "count_distinct",
    SUM = "sum",
    AVG = "avg",
    MIN = "min",
    MAX = "max",
    SAMPLE = "sample",
    GROUP_CONCAT = "group_concat",
    // elementwise aggregates of tensors (QLever, rdf-tensor), e.g. dta:avg(?x)
    TENSOR_SUM = "tensor_sum",
    TENSOR_AVG = "tensor_avg",
    TENSOR_VAR = "tensor_var",
    TENSOR_STD = "tensor_std",
}
/** Value kinds that decide which aggregates apply. */
export enum AggregateKind {
    NUMBER = "number",
    DATE = "date",
    TENSOR = "tensor",
    TEXT = "text",
    // a class node (IRIs)
    NODE = "node",
}
export const TENSOR_AGGREGATES_NS = "https://w3id.org/rdf-tensor/aggregates#"
export const AGGREGATE_LABELS: Record<AggregateFunction, string> = {
    [AggregateFunction.COUNT]: "count",
    [AggregateFunction.COUNT_DISTINCT]: "count distinct",
    [AggregateFunction.SUM]: "sum",
    [AggregateFunction.AVG]: "avg",
    [AggregateFunction.MIN]: "min",
    [AggregateFunction.MAX]: "max",
    [AggregateFunction.SAMPLE]: "sample",
    [AggregateFunction.GROUP_CONCAT]: "concat",
    [AggregateFunction.TENSOR_SUM]: "tensor sum",
    [AggregateFunction.TENSOR_AVG]: "tensor avg",
    [AggregateFunction.TENSOR_VAR]: "tensor var",
    [AggregateFunction.TENSOR_STD]: "tensor std",
}
const TENSOR_AGGREGATES = [AggregateFunction.TENSOR_SUM, AggregateFunction.TENSOR_AVG, AggregateFunction.TENSOR_VAR, AggregateFunction.TENSOR_STD]
export const AGGREGATES_OF: Record<AggregateKind, AggregateFunction[]> = {
    [AggregateKind.NUMBER]: [AggregateFunction.COUNT, AggregateFunction.COUNT_DISTINCT, AggregateFunction.SUM, AggregateFunction.AVG,
    AggregateFunction.MIN, AggregateFunction.MAX, AggregateFunction.SAMPLE, AggregateFunction.GROUP_CONCAT],
    [AggregateKind.DATE]: [AggregateFunction.COUNT, AggregateFunction.COUNT_DISTINCT, AggregateFunction.MIN, AggregateFunction.MAX,
    AggregateFunction.SAMPLE, AggregateFunction.GROUP_CONCAT],
    [AggregateKind.TENSOR]: [AggregateFunction.COUNT, AggregateFunction.SAMPLE, ...TENSOR_AGGREGATES],
    [AggregateKind.TEXT]: [AggregateFunction.COUNT, AggregateFunction.COUNT_DISTINCT, AggregateFunction.MIN, AggregateFunction.MAX,
    AggregateFunction.SAMPLE, AggregateFunction.GROUP_CONCAT],
    [AggregateKind.NODE]: [AggregateFunction.COUNT, AggregateFunction.COUNT_DISTINCT, AggregateFunction.SAMPLE, AggregateFunction.GROUP_CONCAT],
}
export function isTensorAggregate(fn: AggregateFunction | null | undefined): boolean {
    return !!fn && TENSOR_AGGREGATES.includes(fn)
}
const DATE_TYPE = /(date|gYear|gMonth|gDay)/i
const NUMBER_TYPE = /(double|float|decimal|integer|int|long|short|byte|duration|metre|gram|second|minute|hour|year)>?$/i
/** Kind of the values of a property type (n3 or prefixed datatype), for the aggregates it allows. */
export function aggregateKind(prop_type: string | null | undefined): AggregateKind {
    if (!prop_type) {
        return AggregateKind.TEXT
    }
    if (/DataTensor>?$/.test(prop_type)) {
        return AggregateKind.TENSOR
    }
    if (DATE_TYPE.test(prop_type)) {
        return AggregateKind.DATE
    }
    if (NUMBER_TYPE.test(prop_type)) {
        return AggregateKind.NUMBER
    }
    return AggregateKind.TEXT
}
/** The aggregate of a variable (with its ?), e.g. (AVG(?x)), as projection expression. */
export function aggregateExpression(fn: AggregateFunction, variable: string): string {
    switch (fn) {
        case AggregateFunction.COUNT: return `COUNT(${variable})`
        case AggregateFunction.COUNT_DISTINCT: return `COUNT(DISTINCT ${variable})`
        case AggregateFunction.SUM: return `SUM(${variable})`
        case AggregateFunction.AVG: return `AVG(${variable})`
        case AggregateFunction.MIN: return `MIN(${variable})`
        case AggregateFunction.MAX: return `MAX(${variable})`
        case AggregateFunction.GROUP_CONCAT: return `GROUP_CONCAT(STR(${variable}); SEPARATOR=", ")`
        case AggregateFunction.TENSOR_SUM: return `dta:sum(${variable})`
        case AggregateFunction.TENSOR_AVG: return `dta:avg(${variable})`
        case AggregateFunction.TENSOR_VAR: return `dta:var(${variable})`
        case AggregateFunction.TENSOR_STD: return `dta:std(${variable})`
        case AggregateFunction.SAMPLE:
        default:
            return `SAMPLE(${variable})`
    }
}
/** Something that can be grouped by or aggregated: a subquery or a node. */
export interface Aggregatable {
    group_by: boolean
    aggregate: AggregateFunction | null
}
/** Whether the grouping/aggregation of two elements differs (missing fields are the defaults). */
type AggregationFields = { group_by?: boolean | null, aggregate?: string | null }
export function aggregationChanged(a: AggregationFields | null | undefined, b: AggregationFields | null | undefined): boolean {
    return !!a?.group_by != !!b?.group_by || (a?.aggregate ?? null) != (b?.aggregate ?? null)
}
/** Whether the element is grouped or aggregated. */
export function isAggregated(a: AggregationFields | null | undefined): boolean {
    return !!a?.group_by || !!a?.aggregate
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

export function registerSubquery(allowed_prop_types: string[], allowed_filters: string[] | null = null): <C extends SubQueryClass>(constructor: C) => C {
    if (!allowed_filters) {
        allowed_filters = allowed_prop_types
    }
    return <C extends SubQueryClass>(constructor: C): C => {
        // Extend the decorated class (keeping its constructor and statics) and tag instances with an own
        // __parseregister field, so the class survives (de)serialisation; the extended class is what gets
        // registered, so revived instances pass instanceof checks against the exported class.
        const name = constructor.name
        const wrapped = class extends (constructor as unknown as { new(...args: any[]): SubQuery }) {
            __parseregister = name
        } as unknown as C
        Object.defineProperty(wrapped, 'name', { value: name })
        registerClass(wrapped)
        registeredSubQueryClasses[name] = new SubqueryRegisterEntry(name, wrapped, allowed_prop_types, allowed_filters)
        return wrapped
    }
}

@registerClass
export class SubQuery implements Diffable, ReconstructableClass, Aggregatable {
    link: Link;
    // GROUP BY this subquery's property variable (propVar), see AggregateFunction
    group_by: boolean = false;
    // aggregate of the property variable if it is not grouped (null: SAMPLE in aggregate queries)
    aggregate: AggregateFunction | null = null;
    _height: number;
    _width: number;
    // size of the rendered content, measured by the editor (Subquery.vue); overrides the defaults
    _fit_width: number | null = null;
    _fit_height: number | null = null;
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
        return this._fit_height ?? this._height
    }
    set height(value: number) {
        this._height = value
    }
    get width(): number {
        return this._fit_width ?? this._width
    }
    set width(value: number) {
        this._width = value
    }
    changed(other: Diffable): boolean {
        const testvar = "?test"
        return this.filterExpression(testvar) != (other as SubQuery).filterExpression(testvar)! ||
            aggregationChanged(this, other as SubQuery);
    }
    /** Whether the property variable can be grouped/aggregated (it is bound in the query). */
    get aggregatable(): boolean {
        return true
    }
    /** Value kind of the property, which decides the aggregates it allows. */
    aggregateKind(): AggregateKind {
        return aggregateKind(this.link?.to_proptype)
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


// filled from the active configuration by OntoConfig.ensureConfig()
export { ALLOWED_IMAGE_PROP_TYPES }



@registerSubquery(ALLOWED_IMAGE_PROP_TYPES, [])
export class QueryProp extends SubQuery {
    property_id: string
    constructor() {
        super();
        this.constraint_type = SubQueryType.QUERY_PROP
    }
    get height(): number {
        return this._fit_height ?? CONSTRAINT_HEIGHT / 2
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


/** Geometry literal types, shown as plain properties (e.g. for the results map). */
export const GEO_PROP_TYPES = [
    'geo:wktLiteral', 'geo:geoJSONLiteral',
    'http://www.opengis.net/ont/geosparql#wktLiteral', 'http://www.opengis.net/ont/geosparql#geoJSONLiteral',
]
@registerSubquery(GEO_PROP_TYPES, [])
export class GeoProp extends QueryProp { }

@registerSubquery([])
export class SubjectConstraint extends SubQuery {
    instance: Instance;
    constructor() {
        super();
        this.height = CONSTRAINT_HEIGHT / 2
        this.instance = null;
        this.constraint_type = SubQueryType.SUBJECT
    }
    get aggregatable(): boolean {
        // its property variable is never bound, the instance fixes the node itself
        return false
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
        // (in)equality on STR(), so language-tagged labels match (as the backend's generator);
        // sampled values (progressive constraints) may contain quotes
        const literal = `"${String(this.value ?? '').replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`
        switch (this.type) {
            case StringConstraintType.EQUALS:
                return `STR(${property}) = ${literal}`;
            case StringConstraintType.NEQUALS:
                return `STR(${property}) != ${literal}`;
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
        "<http://dbpedia.org/datatype/millimetre>",
        "<http://dbpedia.org/datatype/centimetre>",
        "<http://dbpedia.org/datatype/metre>",
        "<http://dbpedia.org/datatype/kilometre>",
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
import { ALLOWED_IMAGE_PROP_TYPES } from "../ontoconfig";

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
        if (this._fit_height != null) {
            return this._fit_height
        }
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
