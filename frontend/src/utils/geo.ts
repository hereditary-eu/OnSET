// Detection and parsing of geospatial values in query results (no Vue/representation imports, so it
// can be tested on its own). Coordinates are always [longitude, latitude] (GeoJSON order).
//
// Supported value encodings:
// - WKT literals (geo:asWKT, geo:wktLiteral, virtrdf:Geometry, ...): POINT, LINESTRING, POLYGON,
//   MULTIPOINT, MULTILINESTRING, MULTIPOLYGON, GEOMETRYCOLLECTION, with optional Z/M/ZM and an
//   optional leading <crs IRI>. CRS84 (the GeoSPARQL default) and EPSG:4326 (lat/long axis order)
//   are understood; other reference systems are ignored.
// - GeoJSON literals (geo:asGeoJSON, geo:geoJSONLiteral): geometries, Features, FeatureCollections.
// - GeoRSS points ("lat long", georss:point).
// - separate latitude/longitude properties on the same subject (geo:lat + geo:long,
//   schema:latitude + schema:longitude, dbo/dbp variants), paired by their local names.

export type LonLat = [number, number]

export interface GeoGeometry {
    // points, polylines and polygon rings (each ring a closed polyline)
    points: LonLat[]
    lines: LonLat[][]
    polygons: LonLat[][][]
}

export enum GeoColumnKind {
    WKT = 'wkt',
    GEOJSON = 'geojson',
    GEORSS = 'georss',
    LAT_LONG = 'lat_long',
}

// one result property (a column of the result rows) of a query node
export interface GeoPropInfo {
    // result row key (the SPARQL variable without '?')
    var: string
    // property IRI, prefixed (geo:lat) or full (<http://...#lat>)
    property_id?: string | null
    // datatype / range of the property, if known
    datatype?: string | null
    label?: string | null
}

export interface GeoNodeInfo {
    // node id (internal id of the query node)
    id: string
    // class label of the node
    label: string
    // result row keys of the node's instance IRI and label
    instance_var: string
    label_var?: string | null
    props: GeoPropInfo[]
}

export interface GeoColumn {
    kind: GeoColumnKind
    node_id: string
    // WKT/GeoJSON/GeoRSS: the value column; LAT_LONG: the latitude column
    var: string
    // LAT_LONG only: the longitude column
    lon_var?: string
    // human readable name of the column(s)
    label: string
}

export interface GeoFeature {
    column: GeoColumn
    node_id: string
    row_index: number
    instance_id: string | null
    instance_label: string | null
    geometry: GeoGeometry
}

const emptyGeometry = (): GeoGeometry => ({ points: [], lines: [], polygons: [] })
const isEmptyGeometry = (g: GeoGeometry) => g.points.length == 0 && g.lines.length == 0 && g.polygons.length == 0

// ---------------------------------------------------------------------------------------------
// naming helpers

// local name of a (prefixed, full or <wrapped>) IRI, e.g. "<http://...wgs84_pos#lat>" -> "lat"
export function localName(iri: string | null | undefined): string {
    if (!iri) {
        return ''
    }
    let s = String(iri).trim().replace(/^<|>$/g, '')
    const cut = Math.max(s.lastIndexOf('#'), s.lastIndexOf('/'), s.lastIndexOf(':'))
    return cut >= 0 ? s.slice(cut + 1) : s
}

function iriNamespace(iri: string | null | undefined): string {
    if (!iri) {
        return ''
    }
    const s = String(iri).trim().replace(/^<|>$/g, '')
    return s.slice(0, s.length - localName(s).length)
}

const WKT_DATATYPES = ['wktliteral', 'geometry'] // geo:wktLiteral, virtrdf:Geometry
const GEOJSON_DATATYPES = ['geojsonliteral']
const WKT_PROPERTIES = ['aswkt', 'wkt', 'geometry', 'hasgeometry', 'hasdefaultgeometry', 'geom']
const GEOJSON_PROPERTIES = ['asgeojson', 'geojson']
const GEORSS_PROPERTIES = ['point']

// splits a local name into a latitude/longitude role and the rest of the name ("family"), used to
// pair e.g. pushpinLatitude with pushpinLongitude or geo:lat with geo:long
export function latLongRole(name: string): { role: 'lat' | 'lon', family: string } | null {
    const local = localName(name)
    // the coordinate word has to end the name (so DBpedia's latd/latm/lats degree parts do not count)
    const m = /^(.*?)(latitude|longitude|lat|long|lon|lng)$/i.exec(local)
    if (!m) {
        return null
    }
    const prefix = m[1]
    // "long" inside a word (e.g. "belong") is not a coordinate
    if (prefix.length > 0 && /[a-z]$/.test(prefix) && /^[a-z]/.test(m[2])) {
        return null
    }
    const token = m[2].toLowerCase()
    const role = token.startsWith('lat') ? 'lat' : 'lon'
    return { role, family: prefix.toLowerCase().replace(/[_\-.]+$/, '') }
}

/** Whether a property (by IRI and range datatype) holds coordinates or a geometry, e.g. for a map icon. */
export function isGeoProperty(property_id: string | null | undefined, proptype?: string | null): boolean {
    const name = localName(property_id).toLowerCase()
    const type = localName(proptype).toLowerCase()
    return WKT_DATATYPES.includes(type) || GEOJSON_DATATYPES.includes(type)
        || WKT_PROPERTIES.includes(name) || GEOJSON_PROPERTIES.includes(name)
        || latLongRole(property_id ?? '') != null
}

// ---------------------------------------------------------------------------------------------
// value parsing

// strips quotes and a ^^datatype / @lang suffix of a literal in N3 form
function literalText(value: unknown): string | null {
    if (value === null || value === undefined) {
        return null
    }
    if (typeof value === 'number') {
        return String(value)
    }
    let s = String(value).trim()
    const typed = /^"([\s\S]*)"(\^\^\S+|@[\w-]+)?$/.exec(s)
    if (typed) {
        s = typed[1]
    }
    return s
}

export function parseCoordinate(value: unknown): number | null {
    if (typeof value === 'number') {
        return Number.isFinite(value) ? value : null
    }
    const s = literalText(value)
    if (s === null || s.length == 0) {
        return null
    }
    // plain decimal numbers only (no DMS strings)
    if (!/^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$/.test(s)) {
        return null
    }
    const n = Number(s)
    return Number.isFinite(n) ? n : null
}

export function validLonLat(lon: number, lat: number): boolean {
    return Number.isFinite(lon) && Number.isFinite(lat) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180
}

const WKT_START = /^\s*(<[^>]*>\s*)?(POINT|LINESTRING|POLYGON|MULTIPOINT|MULTILINESTRING|MULTIPOLYGON|GEOMETRYCOLLECTION|TRIANGLE|TIN|POLYHEDRALSURFACE)\b/i

export function looksLikeWkt(value: unknown): boolean {
    const s = literalText(value)
    return s !== null && WKT_START.test(s)
}

class WktReader {
    pos = 0
    constructor(public text: string) { }
    skipWs() {
        while (this.pos < this.text.length && /\s/.test(this.text[this.pos])) {
            this.pos++
        }
    }
    peek(): string {
        this.skipWs()
        return this.text[this.pos] ?? ''
    }
    expect(ch: string) {
        if (this.peek() != ch) {
            throw new Error(`WKT: expected '${ch}' at ${this.pos}`)
        }
        this.pos++
    }
    word(): string {
        this.skipWs()
        const m = /^[A-Za-z]+/.exec(this.text.slice(this.pos))
        if (!m) {
            return ''
        }
        this.pos += m[0].length
        return m[0].toUpperCase()
    }
    // "x y [z [m]]"
    coord(): LonLat {
        this.skipWs()
        const m = /^[^,()]+/.exec(this.text.slice(this.pos))
        if (!m) {
            throw new Error(`WKT: expected coordinates at ${this.pos}`)
        }
        this.pos += m[0].length
        const nums = m[0].trim().split(/\s+/).map(Number)
        if (nums.length < 2 || nums.some(n => !Number.isFinite(n))) {
            throw new Error(`WKT: invalid coordinates '${m[0]}'`)
        }
        return [nums[0], nums[1]]
    }
    // "(a, b, ...)" of the given element reader; "EMPTY" gives []
    list<T>(element: () => T): T[] {
        if (this.peek() != '(') {
            if (this.word() == 'EMPTY') {
                return []
            }
            throw new Error(`WKT: expected '(' at ${this.pos}`)
        }
        this.expect('(')
        const out = [element()]
        while (this.peek() == ',') {
            this.pos++
            out.push(element())
        }
        this.expect(')')
        return out
    }
    // MULTIPOINT allows both "(1 2, 3 4)" and "((1 2), (3 4))"
    multiPointElement(): LonLat {
        if (this.peek() == '(') {
            this.expect('(')
            const c = this.coord()
            this.expect(')')
            return c
        }
        return this.coord()
    }
    geometry(into: GeoGeometry) {
        const type = this.word()
        // dimension markers
        if (/[A-Za-z]/.test(this.peek())) {
            const dim = this.word()
            if (!['Z', 'M', 'ZM', 'EMPTY'].includes(dim)) {
                throw new Error(`WKT: unexpected '${dim}'`)
            }
            if (dim == 'EMPTY') {
                return
            }
        }
        switch (type) {
            case 'POINT':
                into.points.push(...this.list(() => this.coord()))
                break
            case 'MULTIPOINT':
                into.points.push(...this.list(() => this.multiPointElement()))
                break
            case 'LINESTRING':
                into.lines.push(this.list(() => this.coord()))
                break
            case 'MULTILINESTRING':
                into.lines.push(...this.list(() => this.list(() => this.coord())))
                break
            case 'POLYGON':
            case 'TRIANGLE':
                into.polygons.push(this.list(() => this.list(() => this.coord())))
                break
            case 'MULTIPOLYGON':
            case 'POLYHEDRALSURFACE':
            case 'TIN':
                into.polygons.push(...this.list(() => this.list(() => this.list(() => this.coord()))))
                break
            case 'GEOMETRYCOLLECTION':
                this.list(() => this.geometry(into))
                break
            default:
                throw new Error(`WKT: unknown geometry type '${type}'`)
        }
    }
}

function mapGeometry(g: GeoGeometry, f: (c: LonLat) => LonLat): GeoGeometry {
    return {
        points: g.points.map(f),
        lines: g.lines.map(l => l.map(f)),
        polygons: g.polygons.map(p => p.map(r => r.map(f))),
    }
}

function geometryValid(g: GeoGeometry): boolean {
    const ok = (c: LonLat) => validLonLat(c[0], c[1])
    return g.points.every(ok) && g.lines.every(l => l.every(ok)) && g.polygons.every(p => p.every(r => r.every(ok)))
}

// CRS84 / no CRS: lon lat; EPSG:4326: lat lon; anything else is not supported
function crsAxisOrder(crs: string | null): 'lonlat' | 'latlon' | null {
    if (!crs) {
        return 'lonlat'
    }
    const c = crs.toUpperCase()
    if (c.includes('CRS84')) {
        return 'lonlat'
    }
    if (/EPSG\/\d+\/4326$|EPSG:4326$/.test(c)) {
        return 'latlon'
    }
    return null
}

export function parseWkt(value: unknown): GeoGeometry | null {
    let s = literalText(value)
    if (s === null || !looksLikeWkt(s)) {
        return null
    }
    let crs: string | null = null
    const crs_match = /^\s*<([^>]*)>\s*/.exec(s)
    if (crs_match) {
        crs = crs_match[1]
        s = s.slice(crs_match[0].length)
    }
    const order = crsAxisOrder(crs)
    if (!order) {
        return null
    }
    try {
        const reader = new WktReader(s)
        let g = emptyGeometry()
        reader.geometry(g)
        if (order == 'latlon') {
            g = mapGeometry(g, ([a, b]) => [b, a])
        }
        return !isEmptyGeometry(g) && geometryValid(g) ? g : null
    } catch {
        return null
    }
}

function geoJsonInto(obj: any, into: GeoGeometry) {
    if (!obj || typeof obj !== 'object') {
        return
    }
    const pt = (c: any): LonLat => [Number(c[0]), Number(c[1])]
    switch (obj.type) {
        case 'Point': into.points.push(pt(obj.coordinates)); break
        case 'MultiPoint': into.points.push(...obj.coordinates.map(pt)); break
        case 'LineString': into.lines.push(obj.coordinates.map(pt)); break
        case 'MultiLineString': into.lines.push(...obj.coordinates.map((l: any[]) => l.map(pt))); break
        case 'Polygon': into.polygons.push(obj.coordinates.map((r: any[]) => r.map(pt))); break
        case 'MultiPolygon':
            into.polygons.push(...obj.coordinates.map((p: any[]) => p.map((r: any[]) => r.map(pt))))
            break
        case 'GeometryCollection': obj.geometries?.forEach((g: any) => geoJsonInto(g, into)); break
        case 'Feature': geoJsonInto(obj.geometry, into); break
        case 'FeatureCollection': obj.features?.forEach((f: any) => geoJsonInto(f, into)); break
    }
}

export function parseGeoJson(value: unknown): GeoGeometry | null {
    const s = literalText(value)
    if (s === null || !/^\s*\{/.test(s) || !/"type"\s*:/.test(s)) {
        return null
    }
    try {
        const g = emptyGeometry()
        geoJsonInto(JSON.parse(s), g)
        return !isEmptyGeometry(g) && geometryValid(g) ? g : null
    } catch {
        return null
    }
}

// GeoRSS simple point: "lat long"
export function parseGeoRssPoint(value: unknown): GeoGeometry | null {
    const s = literalText(value)
    const m = s && /^\s*([+-]?\d+(?:\.\d*)?)[\s,]+([+-]?\d+(?:\.\d*)?)\s*$/.exec(s)
    if (!m) {
        return null
    }
    const lat = Number(m[1]), lon = Number(m[2])
    return validLonLat(lon, lat) ? { points: [[lon, lat]], lines: [], polygons: [] } : null
}

export function parseLatLong(lat_value: unknown, lon_value: unknown): GeoGeometry | null {
    const lat = parseCoordinate(lat_value)
    const lon = parseCoordinate(lon_value)
    if (lat === null || lon === null || !validLonLat(lon, lat)) {
        return null
    }
    return { points: [[lon, lat]], lines: [], polygons: [] }
}

// the geometry of a column in one result row
export function geometryOf(column: GeoColumn, row: Record<string, unknown>): GeoGeometry | null {
    switch (column.kind) {
        case GeoColumnKind.WKT: return parseWkt(row[column.var])
        case GeoColumnKind.GEOJSON: return parseGeoJson(row[column.var])
        case GeoColumnKind.GEORSS: return parseGeoRssPoint(row[column.var])
        case GeoColumnKind.LAT_LONG: return parseLatLong(row[column.var], row[column.lon_var])
    }
}

// ---------------------------------------------------------------------------------------------
// column detection

function propName(p: GeoPropInfo) {
    return p.label || localName(p.property_id) || p.var
}

// geo columns of the nodes judged by property names and datatypes only (no result values needed)
export function detectGeoColumnsByName(nodes: GeoNodeInfo[]): GeoColumn[] {
    const columns: GeoColumn[] = []
    for (const node of nodes) {
        const lats: { p: GeoPropInfo, family: string }[] = []
        const lons: { p: GeoPropInfo, family: string }[] = []
        for (const p of node.props) {
            const local = localName(p.property_id).toLowerCase()
            const dtype = localName(p.datatype).toLowerCase()
            const ns = iriNamespace(p.property_id)
            if (WKT_DATATYPES.includes(dtype) || WKT_PROPERTIES.includes(local)) {
                columns.push({ kind: GeoColumnKind.WKT, node_id: node.id, var: p.var, label: propName(p) })
            } else if (GEOJSON_DATATYPES.includes(dtype) || GEOJSON_PROPERTIES.includes(local)) {
                columns.push({ kind: GeoColumnKind.GEOJSON, node_id: node.id, var: p.var, label: propName(p) })
            } else if (GEORSS_PROPERTIES.includes(local) && (ns.includes('georss') || p.property_id?.startsWith('georss:'))) {
                columns.push({ kind: GeoColumnKind.GEORSS, node_id: node.id, var: p.var, label: propName(p) })
            } else {
                const role = latLongRole(p.property_id || '')
                if (role) {
                    (role.role == 'lat' ? lats : lons).push({ p, family: role.family })
                }
            }
        }
        // pair latitudes with longitudes: same family (and namespace) first, then whatever is left
        const used = new Set<GeoPropInfo>()
        const pair = (match: (a: { p: GeoPropInfo, family: string }, b: { p: GeoPropInfo, family: string }) => boolean) => {
            for (const lat of lats) {
                if (used.has(lat.p)) continue
                const lon = lons.find(l => !used.has(l.p) && match(lat, l))
                if (lon) {
                    used.add(lat.p)
                    used.add(lon.p)
                    columns.push({
                        kind: GeoColumnKind.LAT_LONG, node_id: node.id, var: lat.p.var, lon_var: lon.p.var,
                        label: `${propName(lat.p)} / ${propName(lon.p)}`
                    })
                }
            }
        }
        pair((a, b) => a.family == b.family && iriNamespace(a.p.property_id) == iriNamespace(b.p.property_id))
        pair((a, b) => a.family == b.family)
        pair(() => true)
    }
    return columns
}

// share of the sampled (non-empty) values a column parses, 0 for no values
function parseRate(column: GeoColumn, rows: Record<string, unknown>[]): number {
    let present = 0, parsed = 0
    for (const row of rows) {
        const v = row[column.var]
        if (v === null || v === undefined || v === '') continue
        present++
        if (geometryOf(column, row)) parsed++
    }
    return present == 0 ? 0 : parsed / present
}

// geo columns of the nodes: the ones found by name that parse in the sample rows (or all of them
// without rows), plus value columns whose sampled values are WKT/GeoJSON literals
export function detectGeoColumns(nodes: GeoNodeInfo[], rows: Record<string, unknown>[] | null = null, min_rate = 0.5): GeoColumn[] {
    let columns = detectGeoColumnsByName(nodes)
    if (!rows || rows.length == 0) {
        return columns
    }
    columns = columns.filter(c => parseRate(c, rows) >= min_rate)
    const taken = new Set(columns.flatMap(c => [c.var, c.lon_var]))
    for (const node of nodes) {
        for (const p of node.props) {
            if (taken.has(p.var)) continue
            for (const kind of [GeoColumnKind.WKT, GeoColumnKind.GEOJSON]) {
                const column: GeoColumn = { kind, node_id: node.id, var: p.var, label: propName(p) }
                if (parseRate(column, rows) >= min_rate) {
                    columns.push(column)
                    taken.add(p.var)
                    break
                }
            }
        }
    }
    return columns
}

// the geometries of all rows; duplicate (instance, column) pairs of a row set are kept once
export function extractFeatures(nodes: GeoNodeInfo[], columns: GeoColumn[], rows: Record<string, unknown>[]): GeoFeature[] {
    const features: GeoFeature[] = []
    const seen = new Set<string>()
    const by_id = new Map(nodes.map(n => [n.id, n]))
    rows.forEach((row, row_index) => {
        for (const column of columns) {
            const node = by_id.get(column.node_id)
            const geometry = geometryOf(column, row)
            if (!geometry || !node) continue
            const instance_id = row[node.instance_var] != null ? String(row[node.instance_var]) : null
            const key = `${column.node_id}|${column.var}|${instance_id}|${JSON.stringify(geometry)}`
            if (seen.has(key)) continue
            seen.add(key)
            const label = node.label_var ? row[node.label_var] : null
            features.push({
                column, node_id: column.node_id, row_index, instance_id,
                instance_label: label != null ? literalText(label) : null,
                geometry,
            })
        }
    })
    return features
}

export function geometryBounds(features: GeoFeature[]): { min: LonLat, max: LonLat } | null {
    let min: LonLat = [Infinity, Infinity], max: LonLat = [-Infinity, -Infinity]
    const add = (c: LonLat) => {
        min = [Math.min(min[0], c[0]), Math.min(min[1], c[1])]
        max = [Math.max(max[0], c[0]), Math.max(max[1], c[1])]
    }
    for (const f of features) {
        f.geometry.points.forEach(add)
        f.geometry.lines.forEach(l => l.forEach(add))
        f.geometry.polygons.forEach(p => p.forEach(r => r.forEach(add)))
    }
    return Number.isFinite(min[0]) ? { min, max } : null
}

// a center/zoom (web mercator, 512px tiles) that fits the bounds into a view of the given size
export function fitView(bounds: { min: LonLat, max: LonLat } | null, width = 600, height = 400): { center: { lon: number, lat: number }, zoom: number } {
    if (!bounds) {
        return { center: { lon: 0, lat: 20 }, zoom: 0.5 }
    }
    const merc = (lat: number) => Math.log(Math.tan(Math.PI / 4 + (Math.max(-85, Math.min(85, lat)) * Math.PI) / 360))
    const center = {
        lon: (bounds.min[0] + bounds.max[0]) / 2,
        lat: (bounds.min[1] + bounds.max[1]) / 2,
    }
    const lon_span = Math.max(bounds.max[0] - bounds.min[0], 1e-4) / 360
    const lat_span = Math.max(merc(bounds.max[1]) - merc(bounds.min[1]), 1e-4) / (2 * Math.PI)
    const zoom = Math.min(Math.log2(width / 512 / lon_span), Math.log2(height / 512 / lat_span)) - 0.3
    return { center, zoom: Math.max(0, Math.min(14, zoom)) }
}
