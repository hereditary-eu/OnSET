import type { FuzzyQueryResult, Subject } from "@/api/client.ts/Api";
import { jsonClone, registerClass } from "../parsing";
import { OpenEventType } from "./helpers";
import { aggregateExpression, AggregateFunction, isAggregated, isTensorAggregate, Link, LinkTriplet, LinkType, QueryProp, QuerySet, SubjectConstraint, SubjectNode, SubQuery, TENSOR_AGGREGATES_NS, VectorSort, VectorSortDirection, type QuerySetGenerator } from "./representation";
import { toVar } from "./helpers";
import type { Diffable } from "./diff";
import { linkGeometry, parallelIndex, type Box, type LinkGeometry } from "../graph-layout";
import { el } from "vuetify/locale";


/**
 * The projection of an aggregate query (see AggregateFunction). Every projected variable is
 * either grouped or aggregated; an aggregated variable keeps its name as the alias of its
 * aggregate, `(AVG(?p_3__agg) AS ?p_3)`, and is renamed in the WHERE clause (SPARQL forbids
 * an alias that is bound in the pattern), so results have the same columns as without
 * aggregation and map onto the query graph unchanged.
 *
 * Labels are OPTIONAL joins that would multiply the solutions (one per label/language) and
 * so change the aggregates: only grouped nodes have one, looked up after the grouping in an
 * outer query, `SELECT ... (SAMPLE(?lbl__agg) AS ?lbl) WHERE { { SELECT ... GROUP BY ... }
 * OPTIONAL { ?n rdfs:label ?lbl__agg } } GROUP BY <the inner columns>`.
 */
export interface AggregationPlan {
    // projected terms (of the inner query if there are labels) in the order of the plain query
    select: string[]
    // GROUP BY variables (of the inner query)
    group_by: string[]
    // variables of the WHERE clause that are aggregated -> their name in it
    renames: Record<string, string>
    // projected variables (the aliases of aggregates and the labels included)
    projected: Set<string>
    // a dta: (tensor) aggregate is used
    tensor: boolean
    // labels of the grouped nodes (outer query): node variable, label variable
    labels: { node: string, label: string }[]
    // projection of the outer query (if there are labels)
    outer_select: string[]
}
export const AGGREGATE_VAR_SUFFIX = "__agg"
// string literals and IRIs, in which variables are not renamed
const LITERAL_OR_IRI = /"(?:[^"\\]|\\.)*"|<[^<>\s"]*>/g
/** Renames variables (with their ?) outside of string literals and IRIs. */
export function renameVariables(text: string, renames: Record<string, string>): string {
    const rename = (part: string) => part.replace(/\?[A-Za-z_][A-Za-z0-9_]*/g, (v) => renames[v] ?? v)
    let out = ""
    let last = 0
    for (const match of text.matchAll(LITERAL_OR_IRI)) {
        out += rename(text.slice(last, match.index)) + match[0]
        last = match.index! + match[0].length
    }
    return out + rename(text.slice(last))
}

// the box of a query node that its links attach to (without its constraints)
export const nodeBox = (node: SubjectNode): Box => ({ x: node.x, y: node.y, w: node.width, h: node.height })

@registerClass
export class MixedResponse<N extends Subject = Subject> implements FuzzyQueryResult {
    link: Link<N>;
    subject: SubjectNode;
    score: number;
    store: NodeLinkRepository;
    compute_layout: boolean = false;
    constructor(result: FuzzyQueryResult = null) {
        for (const key in result) {
            if (Object.prototype.hasOwnProperty.call(result, key)) {
                this[key] = result[key];
            }
        }
        this.store = new NodeLinkRepository()
        if (this.subject) {
            this.subject = new SubjectNode(result.subject)
            this.store.nodes.push(this.subject)
        }
        if (this.link) {
            this.link = new Link(result.link)
            let from_subject = new SubjectNode(result.link.from_subject)
            let to_subject = new SubjectNode(result.link.to_subject)
            this.link.from_internal_id = from_subject.internal_id
            this.link.to_internal_id = to_subject.internal_id
            this.store.links.push(this.link)
            this.store.nodes.push(...[from_subject, to_subject])

        }
    }
    postConstruct(): void {
        
    }

}
export enum RepositoryState {
    STABLE,
    EDITING,
}
@registerClass
export class NodeLinkRepository<N extends SubjectNode = SubjectNode, L extends Link = Link> implements Diffable, QuerySetGenerator {
    nodes: N[] = []
    links: L[] = []
    state: RepositoryState = RepositoryState.STABLE
    private static internal_id_cnt = 0
    _id: string | number
    constructor(nodes: N[] = [], links: L[] = []) {
        this.nodes = nodes
        this.links = links
        this._id = NodeLinkRepository.internal_id_cnt++
    }
    get id() {
        return this._id
    }
    changed(other: NodeLinkRepository): boolean {
        return this._id !== other._id
    }
    fromLinks(node: SubjectNode): L[] {
        return this.links.filter(link => link.from_internal_id === node.internal_id)
    }
    toLinks(node: SubjectNode): L[] {
        return this.links.filter(link => link.to_internal_id === node.internal_id)
    }
    from(link: Link): N | null {
        let outnodes = this.nodes.filter(node => node.internal_id === link.from_internal_id)
        return outnodes.length ? outnodes[0] : null
    }
    to(link: Link): N | null {
        let outnodes = this.nodes.filter(node => node.internal_id === link.to_internal_id)
        return outnodes.length ? outnodes[0] : null
    }
    node(n: N): N | null {
        let outnodes = this.nodes.filter(node => node.internal_id === n.internal_id)
        return outnodes.length ? outnodes[0] : null
    }
    link(l: Link): L | null {
        let outlinks = this.links.filter(link => link.id === l.id)
        return outlinks.length ? outlinks[0] : null
    }
    sameLinks(link: L): L[] {
        return this.links.filter(l => l.from_internal_id === link.from_internal_id && l.to_internal_id === link.to_internal_id)
    }
    circularLink(link: L): boolean {
        return link.from_internal_id === link.to_internal_id
    }
    addOutlink(link: L, origin: N, target: N, side: OpenEventType) {
        if (this.nodes.filter(node => node === origin).length === 0) {
            this.nodes.push(origin)
        }
        if (this.nodes.filter(node => node === target).length === 0) {
            this.nodes.push(target)
        }
        link = this.prepareLink(link, origin, target, side)
        this.links.push(link)
    }
    prepareLink(link: L, origin: N, target: N, side: OpenEventType) {
        switch (side) {
            case OpenEventType.FROM:
                link.from_internal_id = target.internal_id
                link.to_internal_id = origin.internal_id
                break
            case OpenEventType.TO:
                link.from_internal_id = origin.internal_id
                link.to_internal_id = target.internal_id
                break
            // default:
            //     throw new Error("Invalid side")
        }
        return link
    }
    removeLink(link: L) {
        if (link) {
            this.links = this.links.filter(l => l.link_id !== link.link_id)
        }
    }
    removeNode(node: N) {
        if (node) {
            this.nodes = this.nodes.filter(n => n.internal_id !== node.internal_id)
            this.links = this.links.filter(l => l.from_internal_id !== node.internal_id && l.to_internal_id !== node.internal_id)
        }
    }
    subElementsRecursive(node: SubjectNode, visited: SubjectNode[] = []) {
        let subNodes: SubjectNode[] = []
        let subLinks: Link[] = []
        let all_links = [...this.fromLinks(node), ...this.toLinks(node)]
        subLinks.push(...all_links)
        for (let link of all_links) {
            let to = this.to(link)
            let from = this.from(link)
            let target = from === node ? to : from
            if (!target || visited.includes(target) || node.internal_id_cnt > target.internal_id_cnt) {
                continue
            }
            visited.push(target)
            subNodes.push(target)
            subLinks.push(link)
            let subEdges = this.subElementsRecursive(target, visited)
            subNodes.push(...subEdges.nodes)
            subLinks.push(...subEdges.links)
        }
        return {
            nodes: subNodes,
            links: subLinks
        }
    }
    subElements(node: SubjectNode) {
        return this.subElementsRecursive(node)
    }

    deleteWithSubnodes(node: SubjectNode) {
        let subElements = this.subElements(node)
        console.log("Subelements", subElements)
        let subNodeIds = subElements.nodes.map(n => n.internal_id)
        this.nodes = this.nodes.filter(n => !subNodeIds.includes(n.internal_id))

        let subLinkIds = subElements.links.map(l => l.link_id)
        this.links = this.links.filter(l => !subLinkIds.includes(l.link_id))

        this.nodes = this.nodes.filter(n => n.internal_id != node.internal_id)
    }
    linksBetweenNodes(): Record<string, L[]> {
        let links = {}
        for (let link of this.links) {
            if (this.nodes.filter(node => node.internal_id === link.from_internal_id).length === 0 ||
                this.nodes.filter(node => node.internal_id === link.to_internal_id).length === 0) {
                continue
            }
            let from = this.from(link)
            let to = this.to(link)
            let link_hash = `${from.internal_id}-${to.internal_id}`

            if (!links.hasOwnProperty(link_hash)) {
                links[link_hash] = []
            }
            links[link_hash].push(link)
        }
        return links
    }


    // index of the link among the links between the same two nodes (either direction), so parallel links bend apart
    parallelIndex(link: Link): number {
        return parallelIndex<Link>(this.links, this.link(link) ?? link, (l) => [l.from_internal_id, l.to_internal_id])
    }
    // directed path of the link from its subject to its object node (see graph-layout.ts)
    linkGeometry(link: Link, circular: boolean = false, from: SubjectNode | null = this.from(link),
        to: SubjectNode | null = this.to(link)): LinkGeometry | null {
        if (!from || !to) {
            return null
        }
        return linkGeometry(nodeBox(from), nodeBox(to), this.parallelIndex(link),
            circular || from.internal_id === to.internal_id)
    }
    textAttachPoint(link: L, circular: boolean = false): { x: number, y: number } {
        const geometry = this.linkGeometry(link, circular)
        if (!geometry) {
            console.warn("Link has no from or to node", link)
            return { x: 0, y: 0 }
        }
        return geometry.label
    }

    /** Whether a node or a property is grouped or aggregated (generateQuery then aggregates). */
    hasAggregation(): boolean {
        return this.nodes.some((node) => isAggregated(node) ||
            (node.subqueries || []).some((sq) => sq != null && sq.aggregatable && isAggregated(sq)))
    }
    /**
     * Aggregate of a node's variable in an aggregate query (null if grouped). A node that is
     * neither grouped nor aggregated is counted (COUNT DISTINCT, e.g. the ships per homeport),
     * unless one of its properties is grouped: then the group (nearly) determines it and it is
     * sampled (e.g. the place of a grouped place label).
     */
    nodeAggregate(node: SubjectNode): AggregateFunction | null {
        if (node.group_by) {
            return null
        }
        if (node.aggregate) {
            return node.aggregate
        }
        const grouped_property = (node.subqueries || []).some((sq) => sq != null && sq.aggregatable && sq.group_by)
        return grouped_property ? AggregateFunction.SAMPLE : AggregateFunction.COUNT_DISTINCT
    }
    /**
     * Projection of the aggregate query of a query set: grouped nodes/properties as they are,
     * everything not grouped through its aggregate (properties: SAMPLE by default, nodes: see
     * nodeAggregate); labels only for grouped
     * nodes (see AggregationPlan). Vector sorts order the groups by their best similarity (MAX,
     * MIN if ascending).
     */
    aggregationPlan(set: QuerySet = this.querySet()): AggregationPlan {
        type Mode = "group" | "label" | "drop" | AggregateFunction
        const modes = new Map<string, Mode>()
        const nodes = Object.values(set.nodes)
        const label_of = new Map<string, string>()
        for (const node of nodes) {
            modes.set(node.outputId(), this.nodeAggregate(node) ?? "group")
            modes.set(node.labelId(), node.group_by ? "label" : "drop")
            label_of.set(node.labelId(), node.outputId())
        }
        const extra: string[] = []
        for (const constraint of set.filter) {
            const variable = constraint.link.outputId()
            if (!constraint.aggregatable) {
                modes.set(variable, "drop")
            } else if (!modes.has(variable)) {
                modes.set(variable, constraint.group_by ? "group" : (constraint.aggregate ?? AggregateFunction.SAMPLE))
            }
            if (constraint instanceof VectorSort && constraint.postQueryExpression(constraint.propVar()).length > 0) {
                const sim = `?sim_${toVar(constraint.id)}`
                modes.set(sim, constraint.direction == VectorSortDirection.ASCENDING ? AggregateFunction.MIN : AggregateFunction.MAX)
                extra.push(sim)
            }
        }
        const plan: AggregationPlan = {
            select: [], group_by: [], renames: {}, projected: new Set(), tensor: false, labels: [], outer_select: [],
        }
        for (const variable of [...nodes.map((nd) => nd.outputId()), ...set.output_ids, ...extra]) {
            const mode = modes.get(variable) ?? AggregateFunction.SAMPLE
            if (mode == "drop" || plan.projected.has(variable)) {
                continue
            }
            plan.projected.add(variable)
            if (mode == "label") {
                plan.labels.push({ node: label_of.get(variable)!, label: variable })
                plan.outer_select.push(`(SAMPLE(${variable}${AGGREGATE_VAR_SUFFIX}) AS ${variable})`)
                continue
            }
            plan.outer_select.push(variable)
            if (mode == "group") {
                plan.group_by.push(variable)
                plan.select.push(variable)
                continue
            }
            const inner = `${variable}${AGGREGATE_VAR_SUFFIX}`
            plan.renames[variable] = inner
            plan.select.push(`(${aggregateExpression(mode, inner)} AS ${variable})`)
            plan.tensor = plan.tensor || isTensorAggregate(mode)
        }
        return plan
    }

    generateQuery(limit: number | null = 100, skip: number | null = null, distinct: boolean = true): string {
        let set = this.querySet()
        let output_names = Object.values(set.nodes).map(nd => nd.outputId())
        // without any group by/aggregate the query is the plain one
        const plan = this.hasAggregation() ? this.aggregationPlan(set) : null
        let query = `
        PREFIX tensorIndex: <https://qlever.cs.uni-freiburg.de/tensorIndex/>
        PREFIX dtf: <https://w3id.org/rdf-tensor/functions#>${plan?.tensor ? `
        PREFIX dta: <${TENSOR_AGGREGATES_NS}>` : ""}
        SELECT ${distinct && !plan ? "DISTINCT" : ""} ${plan ? (plan.labels.length ? plan.outer_select : plan.select).join(" ") : `${output_names.join(" ")} ${set.output_ids.join(" ")}`} WHERE {`
        if (plan && plan.labels.length) {
            query += `\n{ SELECT ${plan.select.join(" ")} WHERE {`
        }
        const body_start = query.length

        for (let link of set.link_triplets) {
            if (link.semantic_link_type === LinkType.STRUCTURAL) {
                query += `\n${link.from_id} ${link.link_id} ${link.to_id}.`
            } else if (link.semantic_link_type === LinkType.SIMILARITY) {
                query += `\n${link.from_id} ${link.link_id} ${link.from_id}_emb.
                 SERVICE tensorIndex: {
                    _:config tensorIndex:numNN 1 ;
                    tensorIndex:left ${link.from_id}_emb ;
                    tensorIndex:bindDistance ?dist ;
                    tensorIndex:payload ?s, ?thumb_ship_emb ;
                    tensorIndex:searchK 1 ;
                    tensorIndex:kIVF 512 ;
                    tensorIndex:experimentalRightCacheName "${link.from_id}-${link.to_id}" ;
                    tensorIndex:right ?${link.to_id}_emb ;
                    tensorIndex:algorithm tensorIndex:ivf ;
                    tensorIndex:distance tensorIndex:dot .
                    {
                        ${link.to_id} ${link.link_id} ${link.to_id}_emb ;
                    }
                }`
            }
        }

        for (let node of Object.values(set.nodes)) {
            if (set.nodes.hasOwnProperty(node.internal_id)) {
                // console.log(internal_id, set.internal_ids[internal_id])
                if (plan) {
                    // labels would multiply the solutions, see AggregationPlan
                    query += `\n${node.outputId()} a ${node.subject_id}.`
                    continue
                }
                query += `\n${node.outputId()} a ${node.subject_id}.
    OPTIONAL {${node.outputId()} rdfs:label ${node.labelId()}.}`
                query += `\nOPTIONAL {${node.outputId()} foaf:name ${node.labelId()}.}`
            }
        }
        for (let constraint of set.filter) {
            // console.log("Constructing", constraint)
            let from = this.from(constraint.link)
            let constrained_id = constraint.propVar()
            let expression = constraint.expression(constrained_id)
            if (constraint instanceof SubjectConstraint) {
                if (constraint.instance) {
                    query += `\nFILTER(${from.outputId()}=${constraint.instance.id})`
                }
            } else if (constraint instanceof QueryProp || !expression || expression.length === 0) {
                query += `\n${from.outputId()} ${constraint.link.property_id} ${constrained_id}.`
            } else {
                query += `\n${from.outputId()} ${constraint.link.property_id} ${constrained_id}.
                ${constraint.expression(constrained_id)}`
            }
        }
        if (plan) {
            query = query.slice(0, body_start) + renameVariables(query.slice(body_start), plan.renames)
        }
        query += "\n}"
        if (plan && plan.group_by.length > 0) {
            query += "\nGROUP BY " + plan.group_by.join(" ")
        }
        if (plan && plan.labels.length) {
            // the labels of the groups (grouped nodes)
            query += "\n}"
            for (const { node, label } of plan.labels) {
                query += `\nOPTIONAL {${node} rdfs:label ${label}${AGGREGATE_VAR_SUFFIX}.}`
                query += `\nOPTIONAL {${node} foaf:name ${label}${AGGREGATE_VAR_SUFFIX}.}`
            }
            query += "\n}\nGROUP BY " + plan.outer_select.filter((term) => !term.startsWith("(")).join(" ")
        }
        const post_query_expressions = set.filter.map((constraint) => constraint.postQueryExpression(constraint.propVar())).filter(expr => expr.length > 0)
        if (post_query_expressions.length > 0) {
            query += "\n" + post_query_expressions.join("\n")
        } else if (!plan) {
            query += "\nORDER BY " + set.output_ids.join(" ")
        } else {
            // by the projected variables only (only grouped nodes have labels)
            const order_ids = set.output_ids.filter((id) => plan.projected.has(id))
            if (order_ids.length > 0) {
                query += "\nORDER BY " + order_ids.join(" ")
            }
        }
        if (limit) {
            query += `\nLIMIT ${limit}`
        }
        if (skip) {
            query += `\nOFFSET ${skip}`
        }
        return query
    }
    queryReadable(): string {
        let set = this.querySet()
        let text = ""
        for (let link of this.links) {
            let from = set.nodes[link.from_internal_id]
            let to = set.nodes[link.to_internal_id]
            text += `${from.label} ${link.label} ${to.label}\n`
        }
        for (let node of Object.values(set.nodes)) {
            text += `${node.id} a ${node.label}\n`
            for (let constraint of node.subqueries) {
                if (constraint instanceof SubjectConstraint) {
                    if (constraint.instance) {
                        text += `${node.label} is exactly ${constraint.instance.label}\n`
                    }
                } else if (constraint instanceof QueryProp) {
                    text += `${node.label}'s ${constraint.link.label} ${constraint.expression(constraint.propVar())}\n`
                }
            }
        }
        return text
    }
    querySet(): QuerySet {
        let set = new QuerySet()

        for (let node of this.nodes) {
            set.nodes[node.internal_id] = node
            set.filter.push(...node.subqueries)
        }

        set.output_ids = Object.values(set.nodes).map(nd => nd.labelId())
        set.output_ids.push(...set.filter.map((constraint) => constraint.link.outputId()))
        for (let link of this.links) {
            let from = this.from(link)
            let to = this.to(link)
            let link_id = link.queryId()
            if (link.allow_arbitrary) {
                set.output_ids.push(link_id)
            }
            set.link_triplets.push({
                from_id: from.outputId(),
                link_id: link_id,
                to_id: to.outputId(),
                semantic_link_type: link.semantic_link_type
            } as LinkTriplet)
        }
        return set
    }
    postConstruct(): void {
        
    }

}