// Geometry and dragging shared by the graph editors (ontology builder cards, query-graph nodes).

export interface Box {
    x: number
    y: number
    w: number
    h: number
}
export interface Point {
    x: number
    y: number
}
export interface LinkGeometry {
    // svg path of a cubic bezier, ending on the target's border (put the arrow marker at its end)
    d: string
    // midpoint of the curve, for the label
    label: Point
}

// gap between the boxes above which links run horizontally between their sides
const SIDE_GAP = 20
// offset between parallel links of the same pair of boxes
const PARALLEL_BEND = 28

/**
 * Directed link between two boxes: a cubic bezier between their facing sides
 * (left/right if they are horizontally apart, top/bottom otherwise), ending on the target's border.
 * Self links loop on the right side. `k` is the index of the link among the parallel links
 * of the same (unordered) pair, so that they bend apart.
 */
export function linkGeometry(a: Box, b: Box, k: number = 0, self: boolean = false): LinkGeometry {
    const bend = k * PARALLEL_BEND
    let p0: Point, p3: Point, c1: Point, c2: Point
    if (self) {
        p0 = { x: a.x + a.w, y: a.y + 8 }
        p3 = { x: a.x + a.w, y: a.y + a.h - 4 }
        c1 = { x: p0.x + 70 + bend, y: p0.y - 30 }
        c2 = { x: p3.x + 70 + bend, y: p3.y + 30 }
    } else if (b.x >= a.x + a.w + SIDE_GAP || a.x >= b.x + b.w + SIDE_GAP) {
        const dir = b.x > a.x ? 1 : -1
        p0 = { x: dir > 0 ? a.x + a.w : a.x, y: a.y + a.h / 2 }
        p3 = { x: dir > 0 ? b.x : b.x + b.w, y: b.y + b.h / 2 }
        const dx = Math.max(40, Math.abs(p3.x - p0.x) / 2) * dir
        c1 = { x: p0.x + dx, y: p0.y + bend }
        c2 = { x: p3.x - dx, y: p3.y + bend }
    } else {
        const dir = b.y > a.y ? 1 : -1
        p0 = { x: a.x + a.w / 2, y: dir > 0 ? a.y + a.h : a.y }
        p3 = { x: b.x + b.w / 2, y: dir > 0 ? b.y : b.y + b.h }
        const dy = Math.max(40, Math.abs(p3.y - p0.y) / 2) * dir
        c1 = { x: p0.x + bend, y: p0.y + dy }
        c2 = { x: p3.x + bend, y: p3.y - dy }
    }
    return {
        d: `M ${p0.x},${p0.y} C ${c1.x},${c1.y} ${c2.x},${c2.y} ${p3.x},${p3.y}`,
        label: { x: (p0.x + 3 * c1.x + 3 * c2.x + p3.x) / 8, y: (p0.y + 3 * c1.y + 3 * c2.y + p3.y) / 8 },
    }
}

/**
 * Index of `item` among the items connecting the same unordered pair, for `linkGeometry`'s `k`.
 */
export function parallelIndex<T>(items: T[], item: T, ends: (t: T) => [string, string]): number {
    const pair = ends(item).slice().sort().join(' ')
    const i = items.filter((t) => ends(t).slice().sort().join(' ') == pair).indexOf(item)
    return Math.max(0, i)
}

/**
 * Drag an element with the pointer from its position `start`: the pointer is captured so fast moves
 * don't lose the element, and `move` gets the new position. `scale` converts screen pixels to the
 * element's coordinates (the zoom of the view).
 */
export function pointerDrag(evt: PointerEvent, start: Point, move: (x: number, y: number) => void,
    scale: number = 1, end?: () => void) {
    if (evt.button != 0) {
        return
    }
    const el = evt.currentTarget as Element
    const x0 = evt.clientX, y0 = evt.clientY
    el.setPointerCapture(evt.pointerId)
    const onMove = (e: PointerEvent) => move(start.x + (e.clientX - x0) / scale, start.y + (e.clientY - y0) / scale)
    const onUp = () => {
        el.removeEventListener('pointermove', onMove as EventListener)
        el.removeEventListener('pointerup', onUp)
        el.removeEventListener('pointercancel', onUp)
        end?.()
    }
    el.addEventListener('pointermove', onMove as EventListener)
    el.addEventListener('pointerup', onUp)
    el.addEventListener('pointercancel', onUp)
}
