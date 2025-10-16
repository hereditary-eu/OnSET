import type { Vector2, Vector2Like } from "three"
import { NodeLinkRepositoryDiff } from "./diff"
import { RepositoryState, type NodeLinkRepository } from "./store"
import { scalingFactors } from "./querymapper"
import { jsonClone } from "../parsing"

export class HistoryEntry {
    query: NodeLinkRepository
    previous_diff: NodeLinkRepositoryDiff | null
    timestamp: number

    text_representation: string
    embedding: number[] | null

    offset: Vector2Like = { x: 0, y: 0 }
    scale: number = 1.0
    size: Vector2Like = { x: 0, y: 0 }
    constructor(
        query: NodeLinkRepository,
        previous_diff: NodeLinkRepositoryDiff | null,
    ) {
        this.query = jsonClone(query)
        this.previous_diff = jsonClone(previous_diff)
        this.timestamp = Date.now()
        
        this.text_representation = query.queryReadable()
        this.embedding = null
    }
    rescale(target_size: Vector2Like,) {
        let { offset, scale, size } = scalingFactors(this.previous_diff || this.query, target_size)
        if(isNaN(scale)) {
            scale = 1.0
            offset = { x: 0, y: 0 }
            size = { x: 0, y: 0 }
        }
        this.offset = offset
        this.scale = scale
        this.size = size
    }
}

export class QueryHistory {
    private history: Record<number, HistoryEntry> = {};
    get length(): number { return Object.keys(this.history).length }
    get reverse_entries(): HistoryEntry[] { return Object.values(this.history).reverse() }
    get entries(): HistoryEntry[] { return Object.values(this.history) }
    tryAddEntry(
        query: NodeLinkRepository): NodeLinkRepositoryDiff | null {
        let diff: NodeLinkRepositoryDiff | null = null
        let add = false
        if(query.state === RepositoryState.EDITING) {
            // do not add entries while editing
            return null
        }
        if (Object.keys(this.history).length === 0) {
            add = true
        } else {
            let last_key = Object.keys(this.history)[Object.keys(this.history).length - 1]
            let last = this.history[last_key]
            diff = new NodeLinkRepositoryDiff(last.query, query)
            console.log("diff", diff)
            if (diff.diff_links.added.length > 0 ||
                diff.diff_links.removed.length > 0 ||
                diff.diff_links.changed.length > 0) {
                add = true
            }
            if (diff.diff_nodes.added.length > 0 ||
                diff.diff_nodes.removed.length > 0 ||
                diff.diff_nodes.changed.length > 0) {
                add = true
            }
        }
        if (add) {
            let new_entry = new HistoryEntry(query, diff)
            this.history[new_entry.timestamp] = new_entry
        }
        return add ? diff : null
    }
}
