import type { FuzzyQueryResult, QueryGraph, Subject } from "@/api/client.ts/Api";
import { jsonClone, registerClass } from "../parsing";
import { NodeSide } from "./helpers";
import { Link, QueryProp, QuerySet, SubjectConstraint, SubjectNode, SubQuery } from "./representation";
import type { Diffable } from "./diff";


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

}

@registerClass
export class NodeLinkRepository<N extends SubjectNode = SubjectNode, L extends Link = Link> implements Diffable {
    nodes: N[] = []
    links: L[] = []
    private static internal_id_cnt = 0
    id: string | number
    constructor(nodes: N[] = [], links: L[] = []) {
        this.nodes = nodes
        this.links = links
        this.id = NodeLinkRepository.internal_id_cnt++
    }
    changed(other: NodeLinkRepository): boolean {
        return this.id !== other.id
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

    addOutlink(link: L, origin: N, target: N, side: NodeSide) {
        if (this.nodes.filter(node => node === origin).length === 0) {
            this.nodes.push(origin)
        }
        if (this.nodes.filter(node => node === target).length === 0) {
            this.nodes.push(target)
        }
        link = this.prepareLink(link, origin, target, side)
        this.links.push(link)
    }
    prepareLink(link: L, origin: N, target: N, side: NodeSide) {
        switch (side) {
            case NodeSide.FROM:
                link.from_internal_id = target.internal_id
                link.to_internal_id = origin.internal_id
                break
            case NodeSide.TO:
                link.from_internal_id = origin.internal_id
                link.to_internal_id = target.internal_id
                break
            default:
                throw new Error("Invalid side")
        }
        return link
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

    generateQuery(limit: number | null = 100, skip: number | null = null): string {
        let set = this.querySet()
        let output_names = Object.values(set.nodes).map(nd => nd.outputId())
        let output_labels = Object.values(set.nodes).map(nd => nd.labelId())
        output_labels.push(...set.filter.map((constraint) => constraint.link.outputId()))
        let query = `SELECT DISTINCT ${output_names.join(" ")} ${output_labels.join(" ")} WHERE {`

        for (let link of set.link_triplets) {
            query += `\n${link.from_id} ${link.link_id} ${link.to_id}.`
        }

        for (let node of Object.values(set.nodes)) {
            if (set.nodes.hasOwnProperty(node.internal_id)) {
                // console.log(internal_id, set.internal_ids[internal_id])
                query += `\n${node.outputId()} a ${node.subject_id}.
    OPTIONAL {${node.outputId()} rdfs:label ${node.labelId()}.}`
                query += `\nOPTIONAL {${node.outputId()} foaf:name ${node.labelId()}.}`
            }
        }
        for (let constraint of set.filter) {
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
        FILTER(${constraint.expression(constrained_id)})`
            }
        }
        query += "\n}"
        query += "\nORDER BY " + output_labels.join(" ")
        if (limit) {
            query += `\nLIMIT ${limit}`
        }
        if (skip) {
            query += `\nOFFSET ${skip}`
        }
        return query
    }
    querySet(): QuerySet {
        let set = new QuerySet()
        set.nodes = {}
        set.filter = []
        set.link_triplets = []
        for (let node of this.nodes) {
            set.nodes[node.internal_id] = node
            set.filter.push(...node.subqueries)
        }
        for (let link of this.links) {
            let from = this.from(link)
            let to = this.to(link)
            set.link_triplets.push({
                from_id: from.outputId(),
                link_id: link.property_id,
                to_id: to.outputId()
            })
        }
        return set
    }
    toQueryGraph(): QueryGraph {
        let query_graph = {} as QueryGraph
        query_graph.subjects = this.nodes.map(node => {
            return {
                internal_id: node.internal_id,
                subject_id: node.subject_id,
                label: node.label,
                type: "subject",
                x: node.x,
                y: node.y,
                subqueries: []
            }
        })
        query_graph.links = this.links.map(link => {
            return {
                from_id: link.from_id,
                to_id: link.to_id,
                link_id: link.property_id,
                from_internal_id: link.from_internal_id,
                to_internal_id: link.to_internal_id,
                type: "link",
            }
        })
        return query_graph
    }

}