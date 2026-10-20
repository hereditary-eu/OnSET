// Text measurement for auto-sizing graph elements to their content.
// Uses an offscreen canvas, so it works before (and without) the SVG being laid out.

// must match the `.node_text` / `.link_text` styles in assets/graph.css
export const GRAPH_FONT_SIZE = 10
export const GRAPH_FONT = `${GRAPH_FONT_SIZE}px 'Roboto Mono', monospace`

let ctx: CanvasRenderingContext2D | null = null
const cache = new Map<string, number>()

export function measureText(text: string | null | undefined, font: string = GRAPH_FONT): number {
    if (!text) {
        return 0
    }
    const key = `${font}|${text}`
    const cached = cache.get(key)
    if (cached !== undefined) {
        return cached
    }
    if (!ctx && typeof document !== 'undefined') {
        ctx = document.createElement('canvas').getContext('2d')
    }
    let width: number
    if (ctx) {
        ctx.font = font
        width = ctx.measureText(text).width
    } else {
        // monospace fallback
        width = text.length * GRAPH_FONT_SIZE * 0.6
    }
    if (cache.size > 5000) {
        cache.clear()
    }
    cache.set(key, width)
    return width
}

// Shorten `text` with an ellipsis so it fits into `max_width` pixels.
export function truncateText(text: string | null | undefined, max_width: number, font: string = GRAPH_FONT): string {
    if (!text || measureText(text, font) <= max_width) {
        return text || ''
    }
    let lo = 0
    let hi = text.length
    while (lo < hi) {
        const mid = Math.ceil((lo + hi) / 2)
        if (measureText(text.slice(0, mid) + '…', font) <= max_width) {
            lo = mid
        } else {
            hi = mid - 1
        }
    }
    return text.slice(0, lo) + '…'
}
