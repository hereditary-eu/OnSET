import type { Property, Subject } from "@/api/client.ts/Api"
import type { SubjectInRadial } from "./d3-man/SunburstEdgeBundling";

export class GSubjectInRadial<T extends Subject = Subject> implements Subject {
    subject_id: string;
    label: string;
    spos?: Record<string, Property>;
    subject_type?: string;
    refcount?: number;
    descendants?: Record<string, Subject[]>;
    total_descendants?: number;
    properties?: Record<string, Subject[]>;
    instance_count?: number;

    expanded: boolean = false;
    children: T[] = [];
    n_id: number = 0;

}

export class BaseTopicMap {
    node_counter = 0;
    mapNodesToChildren<T extends GSubjectInRadial<T>>(add_named_instances = true, cls: new () => T, node: T): T {
        // console.log("args", add_named_instances, cls, node)
        let new_node = new cls();
        for (let key in node) {
            new_node[key] = node[key]
        }
        let children: T[] = []
        if (add_named_instances) {
            for (let key in new_node.descendants) {
                let child = new cls()
                child.subject_id = `${node.subject_id}_${key}`
                child.label = `${node.label}`
                child.expanded = true
                if (node.descendants[key].length > 0) {
                    child.children = node.descendants[key].map(this.mapNodesToChildren.bind(this, add_named_instances, cls)).filter(c => c) as T[]
                    child.children.forEach(child => child.n_id = this.node_counter++)
                    child.total_descendants = child.children.reduce((acc, child) => acc + child.refcount, 0)
                    child.n_id = this.node_counter++
                    children.push(child)
                }
            }
        } else {
            let subclasses = new_node.descendants['subClass']
            children = subclasses.map(this.mapNodesToChildren.bind(this,add_named_instances,cls)).filter(c => c) as T[]
            children.forEach(child => child.n_id = this.node_counter++)
            new_node.total_descendants = children.reduce((acc, child) => acc + child.refcount, 0)
            new_node.n_id = this.node_counter++
        }
        new_node.expanded = true
        new_node.children = children
        return new_node
    }
}