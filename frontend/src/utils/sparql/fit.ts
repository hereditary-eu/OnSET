export interface Box {
    x: number
    y: number
    width: number
    height: number
}

/** The box around the nodes (positioned by their top left corner), null without placed nodes. */
export function nodesBox(nodes: Iterable<Partial<Box>>): Box | null {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity
    for (const n of nodes) {
        if (n.x == null || n.y == null) {
            continue
        }
        x0 = Math.min(x0, n.x)
        y0 = Math.min(y0, n.y)
        x1 = Math.max(x1, n.x + (n.width ?? 0))
        y1 = Math.max(y1, n.y + (n.height ?? 0))
    }
    return isFinite(x0) && isFinite(y0) ? { x: x0, y: y0, width: x1 - x0, height: y1 - y0 } : null
}

/**
 * The transform ``translate(offset) scale(scale)`` that puts the centre of ``box`` (graph coordinates)
 * at the centre of a ``view`` of the given size: shrunk to fit inside it with ``padding`` pixels on each
 * side, never enlarged beyond ``max_scale``. Unscaled at the view's top left without a usable box or view.
 */
export function centerTransform(box: Box | null, view: { width: number, height: number },
    padding: number = 0, max_scale: number = 1): { offset: { x: number, y: number }, scale: number } {
    if (!box || !(view.width > 0) || !(view.height > 0) || !isFinite(box.x) || !isFinite(box.y)) {
        return { offset: { x: 0, y: 0 }, scale: 1 }
    }
    const room = { x: Math.max(view.width - 2 * padding, 1), y: Math.max(view.height - 2 * padding, 1) }
    const scale = Math.min(max_scale, box.width > 0 ? room.x / box.width : Infinity, box.height > 0 ? room.y / box.height : Infinity)
    return {
        offset: {
            x: view.width / 2 - (box.x + box.width / 2) * scale,
            y: view.height / 2 - (box.y + box.height / 2) * scale,
        },
        scale,
    }
}
