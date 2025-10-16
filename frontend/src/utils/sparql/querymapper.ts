import { Api } from "@/api/client.ts/Api";
import { InstanceLink, InstanceNode, Link, SubjectNode as NodeRepr, type QuerySetGenerator } from "./representation";
import { BACKEND_URL } from "../config";
import { Vector2, type Vector2Like } from "three";
import { parseJSON, registerClass, stringifyJSON } from "../parsing";
import { NodeLinkRepository as NodeLinkRepository } from "./store";
import { DiffList, InstanceDiff, NodeLinkRepositoryDiff, type Diffable } from "./diff";
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
export class PropertiesOpenEvent {
    node: InstanceNode;
}
@registerClass
export class InstanceNodeLinkRepository extends NodeLinkRepository<InstanceNode, InstanceLink> {

    constructor(links?: InstanceLink[], nodes?: InstanceNode[]) {
        super();
        this.links = links || []
        this.nodes = nodes || []
    }
    get id() {
        let node_ids = this.nodes.map(n => n.instance_id).reduce((p, c) => `${p}-${c}`, '')
        // console.log("ID", node_ids)
        return node_ids as string | number
    }

}
export class ResultList implements Diffable {
    id: number = 0;
    private static id_cntr = 0
    constructor(public instances: InstanceNodeLinkRepository[] = []) {
        this.id = ResultList.id_cntr
    }
    changed(other: this): boolean {
        return other.id != this.id
    }
}
export function scalingFactors(store: QuerySetGenerator, target_size: Vector2Like): { offset: Vector2Like, scale: number, size: Vector2Like } {
    console.log("Scaling factors for", store, target_size)
    let querySet = store.querySet()

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
    let scale_vec = new Vector2(target_size.x / size.x, target_size.y / size.y)
    let scale = Math.min(scale_vec.x, scale_vec.y)
    console.log(bbox, offset, target_size, scale)
    offset.multiplyScalar(scale)
    bbox.tl.multiplyScalar(scale)
    bbox.br.multiplyScalar(scale)
    size = bbox.br.clone().sub(bbox.tl)
    return { offset, scale, size }
}
export class QueryMapper {
    api: Api<unknown> = null;
    constructor(public store: NodeLinkRepository, public target_size: Vector2Like) {
        this.api = new Api(
            {
                baseURL: BACKEND_URL
            }
        )

    }
    scalingFactors() {
        return scalingFactors(this.store, this.target_size)
    }
    async runAndMap(query: string, skip: number = 0, limit: number = 50) {
        if (!this.store) {
            return new ResultList([])
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
            copied_store = new InstanceNodeLinkRepository(mapped_links, mapped_nodes)
            return copied_store
        })

        mapped_stores.forEach((store) => {
            store.nodes.forEach((node) => {
                node.interactive_clone = new InstanceNode(node)
            })
        })

        return new ResultList(mapped_stores)
    }


}

export { InstanceLink };
