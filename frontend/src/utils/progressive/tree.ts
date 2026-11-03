// Pure helpers of the progressive tree expansion: the tree of modifications (by parent_id),
// the path of steps to a modification, and counts relative to the parent.
// No Vue imports, so these can be run and tested in plain node.
import type { ProgressiveModification } from './types'

export interface ModificationNode {
    modification: ProgressiveModification
    children: ModificationNode[]
}

export interface ModificationTree {
    /** modifications of the request graph, and ones whose parent is missing */
    roots: ModificationNode[]
    nodes: Map<string, ModificationNode>
}

/** The tree of modifications by parent_id; children in the order of the input. */
export function buildTree(modifications: ProgressiveModification[]): ModificationTree {
    const nodes = new Map<string, ModificationNode>()
    for (const modification of modifications) {
        nodes.set(modification.id, { modification, children: [] })
    }
    const roots: ModificationNode[] = []
    for (const node of nodes.values()) {
        const parent = node.modification.parent_id != null ? nodes.get(node.modification.parent_id) : undefined
        // a cycle cannot be built from parent_id alone unless a node is its own parent
        if (parent && parent !== node) {
            parent.children.push(node)
        } else {
            roots.push(node)
        }
    }
    return { roots, nodes }
}

/** Modifications by id, for the path and parent lookups below. */
export function modificationsById(modifications: ProgressiveModification[]): Map<string, ProgressiveModification> {
    return new Map(modifications.map((m) => [m.id, m]))
}

/** The steps from the first level down to `modification` (inclusive); stops at a missing parent. */
export function modificationPath(
    modification: ProgressiveModification, by_id: Map<string, ProgressiveModification>,
): ProgressiveModification[] {
    const path = [modification]
    const seen = new Set([modification.id])
    let parent_id = modification.parent_id
    while (parent_id != null && !seen.has(parent_id)) {
        const parent = by_id.get(parent_id)
        if (!parent) {
            break
        }
        path.unshift(parent)
        seen.add(parent_id)
        parent_id = parent.parent_id
    }
    return path
}

/** Ids of the ancestors of a modification (to expand the tree down to it). */
export function ancestorIds(id: string, by_id: Map<string, ProgressiveModification>): string[] {
    const modification = by_id.get(id)
    return modification ? modificationPath(modification, by_id).slice(0, -1).map((m) => m.id) : []
}

/** The count a modification changes: its parent's, the base count on the first level. */
export function referenceCount(
    modification: ProgressiveModification, by_id: Map<string, ProgressiveModification>, base_count: number | null,
): number | null {
    if (modification.parent_id == null) {
        return base_count
    }
    return by_id.get(modification.parent_id)?.count ?? null
}

/** Deepest level of the modifications (1 without any). */
export function maxDepth(modifications: ProgressiveModification[]): number {
    return Math.max(1, ...modifications.map((m) => m.depth ?? 1))
}

/** Modifications per level, index 0 for depth 1. */
export function depthCounts(modifications: ProgressiveModification[]): number[] {
    const counts = Array.from({ length: maxDepth(modifications) }, () => 0)
    for (const m of modifications) {
        counts[(m.depth ?? 1) - 1]++
    }
    return counts
}
