import type { QueryProp } from "../sparql/representation"

export enum PropType {
    CONTINOUS = 'continous',
    DISCRETE = 'discrete'
}
export enum PropSpecificType {
    DATE = 'date',
    NUMBER = 'linear',
    STRING = 'category'
}
export enum ChartMode {
    BAR = 'bar',
    SCATTER = 'scatter',
    HEATMAP = 'heatmap'
}
export abstract class BucketSpecifier {
    constructor(public lower: number | string,
        public upper: number | string,
        public count: number,
        public prop: AnalyzedProp) { }
    id() {
        return `${this.prop.query_id}~${this.lower}-${this.upper}`
    }
    display() {
        if (this.lower == this.upper) {
            return `${this.lower}`
        }
        if (this.prop.prop_specific_type == PropSpecificType.DATE) {
            return `${new Date(this.lower).toLocaleDateString()} - ${new Date(this.upper).toLocaleDateString()}`
        }
        return `${this.lower} - ${this.upper} `
    }
    inside(value: number | string) {
        return false
    }
}
export class DiscreteBucketSpecifier extends BucketSpecifier {
    constructor(public val: string | number,
        count: number,
        prop: AnalyzedProp) {
        super(val, val, count, prop)
    }
    inside(value: string | number) {
        return this.val == value
    }
}
export class ContinuousBucketSpecifier extends BucketSpecifier {
    constructor(public lower: number,
        public upper: number,
        public count: number,
        public prop: AnalyzedProp) {
        super(lower, upper, count, prop)
    }
    inside(value: number) {
        return value >= this.lower && value <= this.upper
    }
}
export interface AnalyzedProp {
    prop: QueryProp,
    prop_data: any[],
    prop_type: PropType,
    prop_specific_type: PropSpecificType,
    query_id: string
}