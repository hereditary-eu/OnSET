// Pure helpers of the progressive panel: the log-scaled count axis, histogram bins,
// the modifications nearest to a scrubbed count, and the conversion of a modification's
// operations into the agent's GraphChange (for diff previews and applying it).
// No Vue imports, so these can be run and tested in plain node.
import type { AgentLink, AgentQueryGraph, AgentSubject, AgentSubQuery, GraphChange } from '@/utils/agent/protocol'
import type { ProgressiveModification, ProgressiveOperation } from './types'

// --- count axis ---
// Row counts span orders of magnitude (and include 0), so the axis is log10(count + 1).

/** Position of a row count on the log axis. */
export function countPosition(count: number): number {
    return Math.log10(Math.max(count, 0) + 1)
}

/** Row count at a position of the log axis (inverse of countPosition, rounded). */
export function countAtPosition(position: number): number {
    return Math.max(0, Math.round(10 ** position - 1))
}

/** Modifications with a count, i.e. the ones that can be binned. */
export function countedModifications(modifications: ProgressiveModification[]) {
    return modifications.filter((m): m is ProgressiveModification & { count: number } =>
        typeof m.count == 'number' && Number.isFinite(m.count))
}

/** Axis extent [0, max] in positions, covering all counts and the base count. */
export function countExtent(modifications: ProgressiveModification[], base_count: number | null = null): [number, number] {
    const positions = countedModifications(modifications).map((m) => countPosition(m.count))
    if (base_count != null) {
        positions.push(countPosition(base_count))
    }
    // at least one decade, rounded up to the next one
    const max = Math.max(1, ...positions)
    return [0, Math.ceil(max)]
}

export interface HistogramBin {
    index: number
    /** bin range in axis positions, [x0, x1) (the last bin includes x1) */
    x0: number
    x1: number
    /** modifications in the bin */
    ids: string[]
    /** how many of them are constraint modifications (drawn stacked on the others) */
    constraints: number
}

export function isConstraint(modification: ProgressiveModification): boolean {
    return modification.kind == 'constraint'
}

/** Equal-width bins over the log axis; modifications without a count are left out. */
export function histogramBins(
    modifications: ProgressiveModification[], extent: [number, number], bin_count: number = 24,
): HistogramBin[] {
    const [lo, hi] = extent
    const n = Math.max(1, Math.floor(bin_count))
    const width = (hi - lo) / n || 1
    const bins: HistogramBin[] = Array.from({ length: n }, (_, index) => ({
        index, x0: lo + index * width, x1: lo + (index + 1) * width, ids: [], constraints: 0,
    }))
    for (const m of countedModifications(modifications)) {
        const index = Math.floor((countPosition(m.count) - lo) / width)
        const bin = bins[Math.min(n - 1, Math.max(0, index))]
        bin.ids.push(m.id)
        bin.constraints += isConstraint(m) ? 1 : 0
    }
    return bins
}

/**
 * The `k` modifications whose count is nearest to `count` on the log axis, nearest first
 * (ties: smaller count, then id), so the selection does not depend on the input order.
 */
export function nearestModifications(
    modifications: ProgressiveModification[], count: number, k: number = 10,
): ProgressiveModification[] {
    const target = countPosition(count)
    return countedModifications(modifications)
        .map((m) => ({ m, distance: Math.abs(countPosition(m.count) - target) }))
        .sort((a, b) => a.distance - b.distance || a.m.count - b.m.count || a.m.id.localeCompare(b.m.id))
        .slice(0, Math.max(0, k))
        .map(({ m }) => m)
}

/** Median count of the modifications, null without counts. */
export function medianCount(modifications: ProgressiveModification[]): number | null {
    const counts = countedModifications(modifications).map((m) => m.count).sort((a, b) => a - b)
    return counts.length ? counts[Math.floor((counts.length - 1) / 2)] : null
}

/** Compact row count, e.g. 950, 12.3k, 4.1M; ≥ when it reached the cap `limit` of the count. */
export function formatCount(count: number | null | undefined, limit: number | null = null): string {
    if (count == null) {
        return '–'
    }
    if (limit != null && count >= limit) {
        return '≥' + formatCount(count)
    }
    for (const [size, unit] of [[1e9, 'G'], [1e6, 'M'], [1e3, 'k']] as const) {
        if (count >= size) {
            const value = count / size
            return `${value >= 100 ? value.toFixed(0) : value.toFixed(1).replace(/\.0$/, '')}${unit}`
        }
    }
    return String(Math.round(count))
}

// --- operations -> GraphChange ---

export type OperationKind = 'subject' | 'link' | 'subquery'

/** What an operation's data is: subqueries have a `type`, links their subject ids. */
export function operationKind(operation: ProgressiveOperation): OperationKind {
    const data = operation.data as unknown as Record<string, unknown>
    if (typeof data.type == 'string') {
        return 'subquery'
    }
    if ('from_subject_id' in data || 'to_subject_id' in data) {
        return 'link'
    }
    return 'subject'
}

/**
 * The subjects/links a modification adds/removes, with the unchanged subjects of `graph`
 * its links attach to as context. Subquery operations go to `subqueries`, with their subject
 * (operation.subject_id) as context; ones without a subject id, and operations without ids,
 * cannot be matched and are left out (see `skipped`).
 */
export function operationsToChange(
    operations: ProgressiveOperation[], graph: AgentQueryGraph,
): { change: GraphChange, skipped: ProgressiveOperation[] } {
    const change: GraphChange = {
        added: { subjects: [], links: [] },
        removed: { subjects: [], links: [] },
        context: [],
        subqueries: [],
    }
    const skipped: ProgressiveOperation[] = []
    for (const operation of operations) {
        const kind = operationKind(operation)
        const target = String(operation.operation) == 'remove' ? change.removed : change.added
        if (kind == 'subject' && operation.data.id) {
            const subject = operation.data as AgentSubject
            target.subjects.push({ ...subject, subqueries: subject.subqueries ?? [] })
        } else if (kind == 'link' && operation.data.id) {
            const link = operation.data as AgentLink
            if (link.from_subject_id && link.to_subject_id) {
                target.links.push(link)
                continue
            }
            skipped.push(operation)
        } else if (kind == 'subquery' && operation.subject_id) {
            change.subqueries!.push({
                operation: String(operation.operation) == 'remove' ? 'remove' : 'add',
                subject_id: operation.subject_id,
                subquery: operation.data as AgentSubQuery,
            })
        } else {
            skipped.push(operation)
        }
    }
    const changed = new Set([...change.added.subjects, ...change.removed.subjects].map((s) => s.id))
    const attached = new Set([...change.added.links, ...change.removed.links]
        .flatMap((l) => [l.from_subject_id, l.to_subject_id]))
    for (const subquery of change.subqueries!) {
        attached.add(subquery.subject_id)
    }
    change.context = graph.subjects.filter((s) => attached.has(s.id) && !changed.has(s.id))
    return { change, skipped }
}

// --- constraint settings and display ---

/** Percentiles typed as comma/space-separated numbers, null if one is no number in 0-100. */
export function parsePercentiles(text: string): number[] | null {
    const tokens = text.split(/[\s,;]+/).filter((t) => t.length > 0)
    const values = tokens.map((t) => Number(t.replace(/^p/i, '')))
    return values.every((v) => Number.isFinite(v) && v >= 0 && v <= 100) ? values : null
}

/** Short tag of a constraint modification (e.g. "p75", "category"), null for other modifications. */
export function constraintTag(modification: ProgressiveModification): string | null {
    const constraint = modification.constraint
    if (!isConstraint(modification) || !constraint) {
        return null
    }
    return constraint.kind == 'percentile' && constraint.percentile != null ? `p${constraint.percentile}` : 'category'
}
