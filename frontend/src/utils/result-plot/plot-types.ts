import type { QueryProp } from "../sparql/representation"

export enum PropType {
    CONTINOUS = 'continous',
    DISCRETE = 'discrete',
    VECTOR = 'vector'
}
export enum PropSpecificType {
    DATE = 'date',
    NUMBER = 'linear',
    STRING = 'category',
    VECTOR = 'vector'
}
export enum ChartMode {
    BAR = 'bar',
    SCATTER = 'scatter',
    HEATMAP = 'heatmap',
    DIM_REDUCED = 'dim_reduced',
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
const DAY_MS = 24 * 60 * 60 * 1000
export class ContinuousBucketSpecifier extends BucketSpecifier {
    // closed: the upper bound belongs to the bin (only for the last bin), step: bin width
    constructor(public lower: number,
        public upper: number,
        public count: number,
        public prop: AnalyzedProp,
        public closed: boolean = true,
        public step: number = upper - lower) {
        super(lower, upper, count, prop)
    }
    inside(value: number | string | Date) {
        // raw result values: dates are strings there, the bounds are timestamps
        const val = this.prop.prop_specific_type == PropSpecificType.DATE ? new Date(value).getTime() : Number(value)
        return val >= this.lower && (val < this.upper || (this.closed && val <= this.upper))
    }
    display() {
        if (this.prop.prop_specific_type == PropSpecificType.DATE) {
            // bins narrower than a day would share a label (and thus a bar) without the time
            const format = (val: number) => this.step < DAY_MS ? new Date(val).toLocaleString() : new Date(val).toLocaleDateString()
            return this.lower == this.upper ? format(this.lower) : `${format(this.lower)} - ${format(this.upper)}`
        }
        // round to the bin width, so neighbouring bins still get distinct labels
        const digits = this.step > 0 ? Math.min(10, Math.max(0, 1 - Math.floor(Math.log10(this.step)))) : 2
        const format = (val: number) => parseFloat(val.toFixed(digits)).toString()
        return this.lower == this.upper ? format(this.lower) : `${format(this.lower)} - ${format(this.upper)}`
    }
}
export interface AnalyzedProp {
    prop: QueryProp,
    prop_data: any[],
    prop_type: PropType,
    prop_specific_type: PropSpecificType,
    query_id: string
}

export enum MiniatureType {
    BOTH = 'both',
    LEFT = 'left',
    RIGHT = 'right'
}