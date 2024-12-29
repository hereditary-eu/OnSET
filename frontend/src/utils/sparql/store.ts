import { registerClass } from "../parsing";
import { NodeSide } from "./helpers";
import { QuerySet, SubjectConstraint, type Link, type Node } from "./representation";
@registerClass
export class NodeLinkRepository<N extends Node = Node, L extends Link = Link> {
    nodes: N[] = []
    links: L[] = []
    constructor(nodes: N[] = [], links: L[] = []) {
        this.nodes = nodes
        this.links = links
    }
    fromLinks(node: Node): L[] {
        return this.links.filter(link => link.from_internal_id === node.internal_id)
    }
    toLinks(node: Node): L[] {
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
        this.links.push(link)
    }
    subElementsRecursive(node: Node, visited: Node[] = []) {
        let subNodes: Node[] = []
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
    subElements(node: Node) {
        return this.subElementsRecursive(node)
    }

    deleteWithSubnodes(node: Node) {
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
        let output_names = Object.values(set.nodes).map(nd => nd.output_id())
        let output_labels = Object.values(set.nodes).map(nd => nd.label_id())
        output_labels.push(...set.filter.map((constraint) => constraint.link.output_id()))
        let query = `SELECT DISTINCT ${output_names.join(" ")} ${output_labels.join(" ")} WHERE {`

        for (let link of set.link_triplets) {
            query += `\n${link.from_id} ${link.link_id} ${link.to_id}.`
        }

        for (let node of Object.values(set.nodes)) {
            if (set.nodes.hasOwnProperty(node.internal_id)) {
                // console.log(internal_id, set.internal_ids[internal_id])
                query += `\n${node.output_id()} a ${node.subject_id}.
    OPTIONAL {${node.output_id()} rdfs:label ${node.label_id()}.}`
                query += `\nOPTIONAL {${node.output_id()} foaf:name ${node.label_id()}.}`
            }
        }
        for (let constraint of set.filter) {
            let from = this.from(constraint.link)
            if (constraint instanceof SubjectConstraint) {
                if (constraint.instance) {
                    query += `\nFILTER(${from.output_id()}=${constraint.instance.id})`
                }
            } else {
                let constrained_id = `?prop_${constraint.link.link_id}`
                query += `\n${from.output_id()} ${constraint.link.property_id} ${constrained_id}.
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
            set.filter.push(...node.property_constraints)
        }
        for (let link of this.links) {
            let from = this.from(link)
            let to = this.to(link)
            console.log("Adding link", link, from, to)
            set.link_triplets.push({
                from_id: from.output_id(),
                link_id: link.property_id,
                to_id: to.output_id()
            })
        }
        return set
    }
}