import { jsonClone, stringifyJSON } from "../parsing"
import { DiffInstanceNodeLinkRepository, type InstanceNodeLinkRepository, type ResultList } from "./querymapper"
import type { Link, SubjectNode, SubQuery } from "./representation"
import type { NodeLinkRepository } from "./store"

export interface Diffable {
    changed(other: this): boolean
    get id(): string | number
}
export class InstanceDiff<T extends Diffable> {
    right: T
    left: T
    change_set: Record<string, any> = {}
    constructor(left: T, right: T) {
        this.left = jsonClone(left)
        this.right = jsonClone(right)
        if (!left || !right) {
            this.change_set = {}
            return
        }
        for (let key in right) {
            let left_data = stringifyJSON(left[key])
            let right_data = stringifyJSON(right[key])
            if (left_data !== right_data) {
                this.change_set[key] = right[key]
            }
        }
    }
}
export class SubQueryDiff extends InstanceDiff<SubQuery> {
}
export class LinkDiff<L extends Link = Link> extends InstanceDiff<L> {

}
export class DiffList<T extends Diffable, D extends InstanceDiff<T> = InstanceDiff<T>> {
    added: D[] = []
    removed: D[] = []
    changed: D[] = []

    constructor(left: T[], right: T[], diff_class: new (left: T, right: T) => D) {
        this.added = right.filter(r => left.filter(l => l.id == r.id).length === 0).map(r => new diff_class(null, r))
        this.removed = left.filter(l => right.filter(r => l.id == r.id).length === 0).map(l => new diff_class(l, null))
        this.changed = right.map(r => {
            let l = left.find(l => l.id == r.id);
            return l === undefined ? null : {
                left: l,
                right: r,
                changed: l.changed(r)
            }
        }).filter(lr => lr !== null).filter(lr => lr.changed).map(lr => new diff_class(lr.left, lr.right))
    }
}
export class NodeDiff<N extends SubjectNode = SubjectNode> extends InstanceDiff<N> {

    diff_subqueries: DiffList<SubQuery> = null

    constructor(left: N, right: N) {
        super(left, right)
        this.diff_subqueries = new DiffList(left?.subqueries || [],
            right?.subqueries || [], SubQueryDiff)
    }
}

export class NodeLinkRepositoryDiff<N extends SubjectNode = SubjectNode, L extends Link = Link>
    extends InstanceDiff<NodeLinkRepository<N, L>> {

    diff_nodes: DiffList<N, NodeDiff<N>> = null
    diff_links: DiffList<L, LinkDiff<L>> = null


    constructor(left: NodeLinkRepository<N, L>, right: NodeLinkRepository<N, L>) {
        super(left, right)
        this.diff_nodes = new DiffList(left ? left.nodes : [], right ? right.nodes : [], NodeDiff)
        this.diff_links = new DiffList(left ? left.links : [], right ? right.links : [], LinkDiff)
    }

}

export class ResultListDiff extends InstanceDiff<ResultList> {
    diff_instances: DiffList<InstanceNodeLinkRepository, DiffInstanceNodeLinkRepository>
    constructor(left: ResultList, right: ResultList) {
        super(left, right)
        this.diff_instances = new DiffList(left.instances, right.instances, DiffInstanceNodeLinkRepository)
    }
}