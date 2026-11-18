// Bridges the visual query (NodeLinkRepository) and the pure geo detection (utils/geo.ts), and builds
// the plotly map traces of the detected geometries.
import * as d3 from 'd3'
import type { NodeLinkRepository } from '@/utils/sparql/store'
import { SubQueryType } from '@/utils/sparql/representation'
import { readableName } from '@/utils/sparql/querymapper'
import type { GeoFeature, GeoNodeInfo, LonLat } from '@/utils/geo'

// the result columns of the query's nodes: instance, label and every property value the query returns
export function geoNodesOf(store: NodeLinkRepository): GeoNodeInfo[] {
    return store.nodes.map((node) => ({
        id: node.internal_id,
        label: node.label || readableName(node.subject_id),
        instance_var: node.outputId().replace('?', ''),
        label_var: node.labelId().replace('?', ''),
        props: (node.subqueries || [])
            .filter((sq) => sq.link && sq.constraint_type != SubQueryType.SUBJECT)
            .map((sq) => ({
                var: sq.propVar().replace('?', ''),
                property_id: sq.link.property_id,
                datatype: sq.link.to_proptype,
                label: sq.link.label,
            })),
    }))
}

export enum GeoMapMode {
    TILES = 'Map',
    GLOBE = 'Globe',
}

export const GEO_PALETTE = d3.schemeTableau10 as readonly string[]

// one plotly trace per node and geometry type; customdata holds the feature index for clicks
export function buildGeoTraces(features: GeoFeature[], nodes: GeoNodeInfo[], mode: GeoMapMode, selected: number | null = null): any[] {
    const type = mode == GeoMapMode.TILES ? 'scattermap' : 'scattergeo'
    const traces: any[] = []
    nodes.forEach((node, node_index) => {
        const color = GEO_PALETTE[node_index % GEO_PALETTE.length]
        const node_features = features.map((f, i) => ({ f, i })).filter(({ f }) => f.node_id == node.id)
        if (node_features.length == 0) {
            return
        }
        // one legend entry per node
        let legend_shown = false
        const legend = () => {
            const show = !legend_shown
            legend_shown = true
            return show
        }
        const hover = (f: GeoFeature) => `${f.instance_label || readableName(f.instance_id ?? undefined)}`
        const common = {
            type,
            name: node.label,
            legendgroup: node.id,
            hovertemplate: `%{text}<br><i>${node.label}</i> · %{customdata[1]}<extra></extra>`,
        }
        // points
        const pts = node_features.flatMap(({ f, i }) => f.geometry.points.map((c) => ({ c, f, i })))
        if (pts.length > 0) {
            traces.push({
                ...common,
                showlegend: legend(),
                mode: 'markers',
                lon: pts.map(p => p.c[0]),
                lat: pts.map(p => p.c[1]),
                text: pts.map(p => hover(p.f)),
                customdata: pts.map(p => [p.i, p.f.column.label]),
                marker: { size: 9, color, opacity: 0.85 },
            })
        }
        // lines and polygons, separated by gaps (null) in one trace each
        const pathTrace = (paths: { path: LonLat[], f: GeoFeature, i: number }[], fill: boolean) => {
            if (paths.length == 0) {
                return
            }
            const lon: (number | null)[] = [], lat: (number | null)[] = [], text: (string | null)[] = [], customdata: any[] = []
            for (const { path, f, i } of paths) {
                for (const c of path) {
                    lon.push(c[0]); lat.push(c[1]); text.push(hover(f)); customdata.push([i, f.column.label])
                }
                lon.push(null); lat.push(null); text.push(null); customdata.push(null)
            }
            traces.push({
                ...common,
                showlegend: legend(),
                mode: 'lines',
                lon, lat, text, customdata,
                line: { width: 2, color },
                ...(fill ? { fill: 'toself', fillcolor: d3.color(color)!.copy({ opacity: 0.25 }).formatRgb() } : {}),
            })
        }
        pathTrace(node_features.flatMap(({ f, i }) => f.geometry.lines.map(path => ({ path, f, i }))), false)
        pathTrace(node_features.flatMap(({ f, i }) => f.geometry.polygons.flatMap(rings => rings.map(path => ({ path, f, i })))), true)
    })
    // highlight of the selected feature (and the other geometries of the same instance)
    if (selected !== null && features[selected]) {
        const sel = features[selected]
        const same = features.filter(f => f.instance_id == sel.instance_id && f.node_id == sel.node_id)
        const coords = same.flatMap(f => [
            ...f.geometry.points,
            ...f.geometry.lines.flat(),
            ...f.geometry.polygons.flat(2),
        ])
        traces.push({
            type,
            name: 'Selected',
            showlegend: false,
            hoverinfo: 'skip',
            mode: 'markers',
            lon: coords.map(c => c[0]),
            lat: coords.map(c => c[1]),
            marker: { size: 16, color: 'rgba(0,0,0,0)', ...(type == 'scattergeo' ? { line: { width: 3, color: '#e15759' } } : {}) },
        })
        if (type == 'scattermap') {
            // scattermap markers have no outline: a larger red dot below a small white one
            const last = traces[traces.length - 1]
            last.marker = { size: 17, color: '#e15759' }
            traces.push({ ...last, marker: { size: 7, color: '#ffffff' } })
        }
    }
    return traces
}
