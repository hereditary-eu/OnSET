import { Api } from "@/api/client.ts/Api";
import { Link, SubjectNode as NodeRepr } from "./representation";
import { BACKEND_URL } from "../config";
import { Vector2, type Vector2Like } from "three";
import { parseJSON, registerClass, stringifyJSON } from "../parsing";
import type { NodeLinkRepository as NodeLinkRepository } from "./store";
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
export class InstanceNode extends NodeRepr {
    instance_label: string = null
    instance_id: string = null
    interactive_clone: InstanceNode | null = null
    expanded: boolean = false
    instance_data: Record<string, string> = null
    constructor(base_node?: NodeRepr | InstanceNode, instance_data?: Record<string, string>) {
        super(base_node)
        this.instance_data = instance_data || (base_node as InstanceNode).instance_data || {}
        this.instance_id = this.instance_data[this.output_id().replace('?', '')]
        this.instance_label = this.instance_data[this.label_id().replace('?', '')]
        this.instance_label = readableName(this.instance_id, this.instance_label)
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
export type InstanceNodeLinkRepository = NodeLinkRepository<InstanceNode, InstanceLink>
export class QueryMapper {
    api: Api<unknown> = null;
    constructor(public store: NodeLinkRepository, public target_size: Vector2Like) {
        this.api = new Api(
            {
                baseURL: BACKEND_URL
            }
        )

    }
    async runAndMap(query: string, skip: number = 0, limit: number = 20) {
        if (!this.store) {
            return { mapped_nodes: [], offset: new Vector2(0, 0), scale: 1 }
        }
        const response = await this.api.sparql.sparqlQuerySparqlPost({
            query: this.store.generateQuery(limit, skip),
        })
        // console.log("Copied node", copied_store, stringifyJSON(this.store))
        let mapped_stores = response.data.map((instance_data) => {
            let copied_store: InstanceNodeLinkRepository = parseJSON<InstanceNodeLinkRepository>(stringifyJSON(this.store))
            let mapped_nodes = copied_store.nodes.map((node) => {
                return new InstanceNode(node, instance_data as Record<string, string>)
            })
            let mapped_links = copied_store.links.map((link) => {
                return new InstanceLink(link, instance_data as Record<string, string>)
            })
            copied_store.nodes = mapped_nodes
            copied_store.links = mapped_links

            return copied_store
        })

        mapped_stores.forEach((store) => {
            store.nodes.forEach((node) => {
                node.interactive_clone = new InstanceNode(node)
            })
        })
        let querySet = this.store.querySet()

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
        let size = bbox.br.clone().sub(bbox.tl)
        let scale_vec=new Vector2(this.target_size.x / size.x, this.target_size.y / size.y)
        let scale = Math.max(scale_vec.x, scale_vec.y)
        console.log(bbox, offset, this.target_size, scale)
        offset.multiplyScalar(scale)
        bbox.tl.multiplyScalar(scale)
        bbox.br.multiplyScalar(scale)
        size = bbox.br.clone().sub(bbox.tl)
        return { mapped_stores, offset, scale, size }
    }


}