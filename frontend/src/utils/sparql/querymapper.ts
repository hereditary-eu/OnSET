import { Api } from "@/api/client.ts/Api";
import { Link, Node } from "./representation";
import { BACKEND_URL } from "../config";
import { Vector2, type Vector2Like } from "three";
import { parseJSON, registerClass, stringifyJSON } from "../parsing";
export function readableName(uri?: string, label?: string) {

    uri = uri || "-"
    if (!label) {
        try {
            uri = uri.replace(/<|>/g, "")
            label = (new URL(uri)).pathname.split("/").pop().replace(/_/g, " ")
        } catch (error) {
            // console.log("Failed to parse id for readable labe", uri, error)
            label = uri
        }
    }
    return label
}
@registerClass
export class InstanceNode extends Node {
    instance_label: string = null
    instance_id: string = null
    interactive_clone: InstanceNode = null
    expanded: boolean = false
    instance_data: Record<string, string> = null
    constructor(base_node?: Node | InstanceNode, instance_data?: Record<string, string>) {
        super(base_node)
        this.instance_data = instance_data || (base_node as InstanceNode).instance_data || {}
        this.instance_id = this.instance_data[this.output_id().replace('?', '')]
        this.instance_label = this.instance_data[this.label_id().replace('?', '')]
        this.instance_label = readableName(this.instance_id, this.instance_label)
        if (base_node) {
            this.to_links = base_node.to_links.map((link) => {
                let instance = new InstanceLink(link, instance_data)
                if (instance.to_subject) {
                    instance.to_subject = new InstanceNode(link.to_subject, instance_data)
                    instance.to_subject.from_links = instance.to_subject.from_links.map((link) => {
                        let instance = new InstanceLink(link, instance_data)
                        return instance
                    })
                }
                instance.from_subject = this
                return instance
            })
            this.from_links = base_node.from_links.map((link) => {
                let instance = new InstanceLink(link, instance_data)
                if (instance.from_subject) {
                    instance.from_subject = new InstanceNode(link.from_subject, instance_data)
                    instance.from_subject.to_links = instance.from_subject.to_links.map((link) => {
                        let instance = new InstanceLink(link, instance_data)
                        return instance
                    })
                }
                instance.to_subject = this
                return instance
            })
        }
    }
}
@registerClass
export class InstanceLink extends Link {
    constructor(base_link: Link = null, public instance_data: Record<string, string> = null) {
        super(base_link)
    }
}
export class PropertiesOpenEvent {
    node: InstanceNode;
}
export class QueryMapper {
    api: Api<unknown> = null;
    constructor(public root_node: Node, public target_size: Vector2Like) {
        this.api = new Api(
            {
                baseURL: BACKEND_URL
            }
        )

    }
    async runAndMap(query: string) {
        if (!this.root_node) {
            return { mapped_nodes: [], offset: new Vector2(0, 0), scale: 1 }
        }
        const response = await this.api.sparql.sparqlQuerySparqlPost({
            query: this.root_node.generateQuery()
        })
        let copied_node = parseJSON<Node>(stringifyJSON(this.root_node))
        console.log("Copied node", copied_node, stringifyJSON(this.root_node))
        let mapped_nodes = response.data.map((instance_data) => {
            return new InstanceNode(copied_node, instance_data as Record<string, string>)
        })

        mapped_nodes.forEach((node) => {
            node.interactive_clone = new InstanceNode(node)
        })
        let querySet = this.root_node.querySet()

        let bbox = { br: new Vector2(0, 0), tl: new Vector2(Infinity, Infinity) }

        Object.values(querySet.nodes).forEach((node) => {
            if (node.x < bbox.tl.x) {
                bbox.tl.x = node.x
            }
            if (node.y < bbox.tl.y) {
                bbox.tl.y = node.y
            }
            if (node.x + node.width > bbox.br.x) {
                bbox.br.x = node.x + node.width
            }
            if (node.y + node.height > bbox.br.y) {
                bbox.br.y = node.y + node.height
            }
        })

        let offset = bbox.tl.clone().multiplyScalar(-1)
        let scale_x = this.target_size.x / (bbox.br.x - bbox.tl.x)
        let scale_y = this.target_size.y / (bbox.br.y - bbox.tl.y)
        let scale = Math.min(scale_x, scale_y)
        console.log(bbox, offset, this.target_size, scale)
        offset.multiplyScalar(scale)
        bbox.tl.multiplyScalar(scale)
        bbox.br.multiplyScalar(scale)
        let size = bbox.br.clone().sub(bbox.tl)
        return { mapped_nodes, offset, scale, size }
    }


}