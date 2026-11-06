// Link strength of the visual query editor: stroke width (and arrow/label emphasis) from the number
// of triples of a link. Configured KGs carry it as ``Link.instance_count`` (stored schema); a view can
// provide live counts instead (the ontology builder: counts in the KG being extracted).
import type { InjectionKey, Ref } from 'vue'

/** Live triple counts of links by subject class, property and object class (prefixed ids). */
export interface LinkCountLookup {
    count(from_id?: string | null, property_id?: string | null, to_id?: string | null): number | undefined
    // the largest count, the scale's maximum
    max: number
}

export const LINK_COUNTS_KEY: InjectionKey<Ref<LinkCountLookup | null>> = Symbol('linkCounts')

export function linkCountLookup(links: { from_id: string, property_id: string, to_id: string | null, count: number }[]): LinkCountLookup {
    const key = (f?: string | null, p?: string | null, t?: string | null) => `${f ?? ''}|${p ?? ''}|${t ?? ''}`
    const counts = new Map(links.map((l) => [key(l.from_id, l.property_id, l.to_id), l.count]))
    return {
        count: (f, p, t) => counts.get(key(f, p, t)),
        max: Math.max(0, ...links.filter((l) => l.to_id).map((l) => l.count)),
    }
}

export const LINK_MIN_WIDTH = 1.25
export const LINK_MAX_WIDTH = 6
// width of a link without triples (drawn dashed)
export const LINK_EMPTY_WIDTH = 1

export interface LinkStrength {
    width: number
    // 0..1 on the scale (for label emphasis)
    weight: number
    // a known count of 0
    empty: boolean
}

/** Log scale between the min and max width: relative to ``max`` if given (live counts), otherwise
 * absolute (1 + log10(count + 1), the stored schema's instance counts). Unknown counts (< 0) are thin. */
export function linkStrength(count: number | undefined, max?: number): LinkStrength {
    if (count === undefined || count < 0) {
        return { width: LINK_MIN_WIDTH, weight: 0, empty: false }
    }
    if (max !== undefined) {
        if (count == 0) {
            return { width: LINK_EMPTY_WIDTH, weight: 0, empty: true }
        }
        const weight = Math.min(1, Math.log1p(count) / Math.log1p(Math.max(max, 1)))
        return { width: LINK_MIN_WIDTH + (LINK_MAX_WIDTH - LINK_MIN_WIDTH) * weight, weight, empty: false }
    }
    const width = Math.min(LINK_MAX_WIDTH, 1 + Math.log10(count + 1))
    return { width, weight: (width - 1) / (LINK_MAX_WIDTH - 1), empty: false }
}
