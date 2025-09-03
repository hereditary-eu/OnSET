

import * as d3 from 'd3'
import * as THREE from 'three';
import { Api, type Property, type Subject, type Topic } from '@/api/client.ts/Api';
import { registerClass } from '../parsing';
import { buildColours, evalChildren, TopicInCircle } from '../three-man/HierarchicalCircleMan3D';
export enum EdgeMode {
    CURVED,
    BUNDLED
}
export class SubjectInRadial implements Subject {
    kind: string = 'subject';
    subject_id: string;
    label: string;
    spos: Record<string, Property> = {};
    subject_type?: string = 'split';
    refcount?: number = 0;
    descendants?: Record<string, Subject[]> = {};
    total_descendants?: number = 0;
    expanded: boolean = false
    children?: SubjectInRadial[]
    n_id: number = 0


    incoming: [d3.HierarchyNode<SubjectInRadial>, d3.HierarchyNode<SubjectInRadial>][]
    outgoing: [d3.HierarchyNode<SubjectInRadial>, d3.HierarchyNode<SubjectInRadial>][]

    get id() {
        return `subject-${this.subject_id}`
    }

    remove(id: string) {
        this.children = this.children.filter(st => st.id !== id);
    }

}

@registerClass
export class TopicInEdges implements Topic {
    kind: string = 'topic';
    subjects_ids: string[];
    property_ids: string[];
    topic_id: number;
    sub_topics: TopicInEdges[];
    subjects: SubjectInRadial[] = [];
    parent_topic_id: number;
    topic: string;
    count: number;
    // links?: TopicTreeLink[]
    to_position?: THREE.Vector3
    color_position?: THREE.Vector2
    color_angle?: number
    n_children?: number
    parent?: TopicInEdges | null
    depth: number = 0

    incoming: [d3.HierarchyNode<TopicInEdges>, d3.HierarchyNode<TopicInEdges>][]
    outgoing: [d3.HierarchyNode<TopicInEdges>, d3.HierarchyNode<TopicInEdges>][]

    get id() {
        return `topic-${this.topic_id}`
    }
    get position() {
        // console.warn('TopicInCircle.position is deprecated, use to_position instead')
        return this.to_position || new THREE.Vector3(0, 0, 0)
    }
    get children(): (TopicInEdges | SubjectInRadial)[] {
        return [...this.sub_topics, ...this.subjects]
    }
    get label() {
        return `${this.topic}`
    }
    remove(id: string) {
        this.sub_topics = this.sub_topics.filter(st => st.id !== id);
        this.subjects = this.subjects.filter(s => s.id !== id);
    }
}
export type EdgeDatum = SubjectInRadial | TopicInEdges;
export function topicPoints<DatumEdge extends EdgeDatum, DatumCircle extends SubjectInRadial>(edge_root: d3.HierarchyNode<DatumEdge>, radial_root: d3.HierarchyRectangularNode<DatumCircle>, radius_steps: number, radius: number): d3.HierarchyNode<DatumEdge> {
    const radial_map = new Map(radial_root.descendants().map(d => [d.data.id, d]));
    const edge_map = new Map(edge_root.descendants().map(d => [d.data.id, d]));
    let na_nodes = radial_root.descendants().filter(d => isNaN(d.x0))
    console.warn('NaN nodes in radial root', na_nodes)
    console.log('radial_map', radial_map)

    edge_root.each(d => {
        if (d.data.kind === 'subject') {
            const radial_node = radial_map.get((d.data as SubjectInRadial).id);
            if (radial_node) {
                d.x = radial_node.x0 + (radial_node.x1 - radial_node.x0) / 2;
                d.y = radial_node.y1;

            }
        }
    })

    console.warn('NaN nodes in radial root', na_nodes)
    //eachAfter to visit leaf nodes first, then parents, etc - can aggregate data from children
    edge_root.eachAfter(d => {
        let x = 0;
        let y = 0;
        let radius_max = 0;
        let count = 0;
        if (d.children) {
            for (const child of d.children) {
                if (!child.x || !child.y) {
                    continue;
                }
                let x_c = child.x;
                let y_c = child.y;
                radius_max = Math.max(radius_max, y_c);
                // project to cartesian coordinates
                let x_cart = Math.cos(x_c) * y_c;
                let y_cart = Math.sin(x_c) * y_c;
                x += x_cart;
                y += y_cart;
                count++;
            }

            if (count > 0) {
                let d_x = x / count;
                let d_y = y / count;
                // convert back to polar coordinates
                d.x = Math.atan2(d_y, d_x); // angle
                let r = Math.sqrt(d_x * d_x + d_y * d_y);
                d.y = Math.max(r, radius_max); // radius
                d.y = Math.min(d.y, radius - radius_steps); // limit radius to avoid overlap
            } else {
                d.x = 0;
                d.y = 0;
            }

            d.y = d.y + radius_steps; // spread out vertically by depth
            // d.children.forEach(c => {
            //     c.y = Math.max(c.y, d.y); 
            // })
        } else {
            d.x = d.x || 0;
            d.y = d.y || 0;
            count = 1; // if no children, we take the node's position as is
        }
        // for (const child of d.data.children) {
        //     if (child.kind === 'subject') {
        //         const radial_node = radial_map.get(child.id);
        //         if (radial_node) {
        //             x += radial_node.x0 + (radial_node.x1 - radial_node.x0) / 2;
        //             y += radial_node.y0 + (radial_node.y1 - radial_node.y0) / 2;
        //             count++;
        //         } else {
        //             console.warn('No radial node found for subject id', child.id, 'in edge', d.data);
        //         }
        //     } else if (child.kind === 'topic') {
        //         const topic = child as TopicInEdges;
        //         const topic_node = edge_map.get(topic.id);
        //         x += topic_node.x || 0; // if it's a topic, we take its position as is
        //         y += topic_node.y || 0; // if it's a topic, we take its position as is;
        //         // y -= topic_node.y || 0;; // spread out vertically by depth
        //         count++; // if it's a topic, we take its position as is
        //     }

        // }
    })
    edge_root.each(nd => {
        if (!nd.x && !nd.y) {
            console.warn('No position found for edge node', nd.data.id, nd);
        }
    })
    return edge_root;

}
export class SunburstEdgeBundling {
    topics_root: EdgeDatum = null
    nodes: SubjectInRadial[] = []

    node_d3: d3.Selection<any, SubjectInRadial, any, any> = null

    svg_d3: d3.Selection<SVGSVGElement, unknown, HTMLElement, any> = null

    color = d3.scaleLinear()
        .domain([0, 10])
        .range(["hsl(152,80%,80%)", "hsl(228,30%,40%)"] as any)
        .interpolate(d3.interpolateHcl as any);
    color_type = d3.scaleOrdinal(d3.schemePastel2);

    width = 1000
    height = 500
    clicked_node: (NodeType) => void = null


    edge_mode: EdgeMode = EdgeMode.CURVED;

    nodes_g_d3: d3.Selection<any, any, any, any> = null
    root: d3.HierarchyNode<SubjectInRadial> = null
    focus: d3.HierarchyCircularNode<SubjectInRadial> = null
    hierarchy: d3.HierarchyNode<SubjectInRadial> = null

    subject_map: Map<string, d3.HierarchyRectangularNode<SubjectInRadial>> = new Map<string, d3.HierarchyRectangularNode<SubjectInRadial>>();
    private node_counter = 0
    constructor(private selector: string) {

    }
    mapNodesToChildren(node: SubjectInRadial): SubjectInRadial {
        let new_node = new SubjectInRadial()
        for (let key in node) {
            new_node[key] = node[key]
        }
        let children: SubjectInRadial[] = []
        for (let key in new_node.descendants) {
            let child = new SubjectInRadial()
            child.subject_id = `${node.subject_id}_${key}`
            child.label = `${node.label}`
            child.expanded = true
            if (node.descendants[key].length > 0) {
                child.children = node.descendants[key].map(this.mapNodesToChildren.bind(this)).filter(c => c) as SubjectInRadial[]
                child.children.forEach(child => child.n_id = this.node_counter++)
                child.total_descendants = child.children.reduce((acc, child) => acc + child.refcount, 0)
                child.n_id = this.node_counter++
                children.push(child)
            }
        }
        new_node.expanded = true
        new_node.children = children
        return new_node
    }
    restartSunburst() {

        const mapped_nodes: SubjectInRadial[] = this.nodes.map(this.mapNodesToChildren.bind(this)).filter(c => c) as SubjectInRadial[]
        mapped_nodes.forEach(child => child.n_id = this.node_counter++)

        console.log('restarting graph', this.nodes, mapped_nodes)
        const data = new SubjectInRadial()
        data.subject_id = 'root'
        data.label = 'root'
        data.children = mapped_nodes
        data.refcount = mapped_nodes.reduce((acc, child) => acc + child.refcount, 0)
        data.total_descendants = mapped_nodes.reduce((acc, child) => acc + child.total_descendants, 0)
        data.n_id = this.node_counter++
        data.spos = {}
        data.expanded = true
        data.subject_type = 'root'
        this.hierarchy = d3.hierarchy(data, (d) => d.children)
            .sum(d => (d.children?.length || 10))
            .sort((a, b) => b.value - a.value)
        //https://observablehq.com/@d3/sunburst/2
        // const color = d3.scaleOrdinal(d3.quantize(d3.interpolateRainbow, data.children.length + 1));

        const radius = 1000.0 / 2;

        // Prepare the layout.
        const root = d3.partition<SubjectInRadial>()
            .size([2 * Math.PI, radius / 2])
            .padding(0)
            (this.hierarchy);

        this.subject_map = new Map<string, d3.HierarchyRectangularNode<SubjectInRadial>>(
            root.descendants().map(d => [d.data.subject_id, d])
        );
        console.log('root', root)
        let max_depth = 0
        root.each(d => {
            // console.log('depth', d.depth, d.data.label)
            if (d.depth > max_depth) {
                max_depth = d.depth
            }
        })
        this.color = d3.scaleLinear()
            .domain([0, max_depth])
            .range(["hsl(152,80%,80%)", "hsl(228,30%,40%)"] as any)
            .interpolate(d3.interpolateHcl as any);
        const arc = d3.arc<d3.HierarchyRectangularNode<SubjectInRadial>>()
            .startAngle(d => d.x0)
            .endAngle(d => d.x1)
            // .padAngle(d => Math.min((d.x1 - d.x0) / 2, 0.005))
            // .padRadius(radius / 2)
            .innerRadius(d => radius - d.y0)
            .outerRadius(d => radius - d.y1 - 1);


        // Create the SVG container.
        const svg = this.svg_d3;

        // Add an arc for each element, with a title for tooltips.
        const format = d3.format(",d");
        svg.append("g")
            .attr("fill-opacity", 0.6)
            .selectAll("path")
            .data(root.descendants().filter(d => d.depth))
            .join("path")
            .attr("fill", d => { return this.color(d.depth); })
            .attr("d", arc as any)
            .append("title")
            .text(d => `${d.ancestors().map(d => d.data.label).reverse().join("/")}\n${format(d.value)}`);

        // Add a label for each element.
        svg.append("g")
            .attr("pointer-events", "none")
            .attr("text-anchor", "middle")
            .attr("font-size", 10)
            .attr("font-family", "sans-serif")
            .selectAll("text")
            .data(root.descendants().filter(d => d.depth && (d.y0 + d.y1) / 2 * (d.x1 - d.x0) > 10))
            .join("text")
            .attr("transform", function (d) {
                const x = (d.x0 + d.x1) / 2 * 180 / Math.PI;
                const normalizedX = (x + 360) % 360; // Normalize to [0, 360)
                const y = radius - (d.y0 + d.y1) / 2;
                return `rotate(${normalizedX - 90}) translate(${y},0) 
                rotate(${(normalizedX < 90) || (normalizedX > 270) ? 90 : 270})
                `;
            })
            .attr("dy", "0.35em")
            .text(d => d.data.label);
        // this.color = d3.scaleLinear()
        //     .domain([0, max_depth])
        //     .range(["hsl(152,80%,80%)", "hsl(228,30%,40%)"] as any)
        //     .interpolate(d3.interpolateHcl as any);

        // add hierachical topic links


        const revive_topic = (topic: Topic, parent?: TopicInEdges): TopicInEdges => {
            let topic_in_circle = new TopicInEdges()
            for (let key in topic) {
                topic_in_circle[key] = topic[key]
            }
            topic_in_circle.parent = parent
            topic_in_circle.sub_topics = topic.sub_topics.map((st) => revive_topic(st, topic_in_circle))
            topic_in_circle.subjects = topic.subjects_ids.map((sid) => {
                return this.subject_map.get(sid)?.data || null
            }).filter(s => s !== null)
            for (let child of topic_in_circle.children) {
                if (child.kind === 'topic' && child.children.length === 0) {
                    topic_in_circle.remove(child.id);
                }
            }
            return topic_in_circle
        }
        this.topics_root = revive_topic(this.topics_root as TopicInEdges, null) as EdgeDatum;
        evalChildren(this.topics_root as TopicInCircle)
        buildColours(this.topics_root as TopicInCircle)

        // const tree = d3.cluster<TopicInEdges>()
        //     .size([2 * Math.PI, radius - 100]);
        const hierarchy_topics = d3.hierarchy(this.topics_root, (d) => d.children)
            .sort((a, b) => d3.ascending(a.height, b.height) || d3.ascending(a.data.children.length, b.data.children.length))


        const root_edges = topicPoints(hierarchy_topics, root, radius / (max_depth), radius);
        console.log('root_edges', root_edges)
        console.log('this.subject_map', this.subject_map)
        console.log('root_edges.links()', root_edges.links())//.filter(d => (d.data as TopicInEdges).subjects_ids?.length > 0))
        console.log('hierarchy_topics', hierarchy_topics)
        switch (this.edge_mode) {
            default:
            case EdgeMode.CURVED:
                {
                    const line = d3.linkRadial<d3.HierarchyLink<EdgeDatum>, d3.HierarchyNode<EdgeDatum>>()
                        // .curve(d3.curveBundle.beta(0.3))
                        .radius(d => radius - d.y)
                        .angle(d => d.x);

                    let colornone = "#ccc"
                    const link = svg.append("g")
                        .attr("fill", "none")
                        .selectAll()
                        .data(root_edges.links())
                        .join("path")
                        .style("mix-blend-mode", "multiply")

                        .attr("stroke", d => {
                            if (d.source.data.kind === 'topic') {
                                let topic = d.source.data as TopicInEdges;
                                if (topic.color_angle) {
                                    console.log('topic.color_angle', topic.color_angle)
                                    return `hsl(${topic.color_angle * 180 / Math.PI}deg, 50%, 90%)`;
                                }
                            }
                            return colornone;
                        })
                        .attr("d", d => line(d)
                        )
                }
                break;
            case EdgeMode.BUNDLED:
                {
                    let bilinked = this.bilink(hierarchy_topics);
                    const line = d3.lineRadial<d3.HierarchyNode<EdgeDatum>>()
                        .curve(d3.curveBundle.beta(0))
                        .radius(d => radius - d.y)
                        .angle(d => d.x);

                    let colornone = "#ccc"
                    const link = svg.append("g")
                        .attr("fill", "none")
                        .selectAll()
                        .data(bilinked.leaves().map(d => {
                            // get all parents of d
                            return d
                        })
                            // .filter(d => d.source.x !== d.target.x
                            //     && d.source.y !== d.target.y
                            //     && d.source.x !== 0 && d.source.y !== 0)
                        )
                        .join("path")
                        .style("mix-blend-mode", "multiply")
                        .attr("stroke", d => {
                            if (d.data.kind === 'topic') {
                                let topic = d.data as TopicInEdges;
                                if (topic.color_angle) {
                                    console.log('topic.color_angle', topic.color_angle)
                                    return `hsl(${topic.color_angle * 180 / Math.PI}deg, 50%, 90%)`;
                                }
                            }
                            return colornone;
                        })
                        .attr("d", d => line(d.data.outgoing.map(o => o[1])))
                }
                break;
        }
        // .each(function (d) { d.path = this; });
    }
    bilink(root: d3.HierarchyNode<EdgeDatum>, depth: number = 5) {

        const map = new Map(root.leaves().map(d => [d.data.id, d]));
        for (const d of root.leaves()) {
            d.data.incoming = [];
            d.data.outgoing = d.ancestors().slice(0, depth).flatMap(a => a.children).filter(c=>c!==undefined).map(c => [d, map.get(c.data.id)]).filter(o => o[1] !== undefined) as [d3.HierarchyNode<TopicInEdges>, d3.HierarchyNode<TopicInEdges>][];
        }
        for (const d of root.leaves()) {
            for (const o of d.data.outgoing) {
                o[1].data.incoming.push(o as any);
            }
        }
        return root;
    }

    init() {

        // Create a simulation with several forces.


        // Create the SVG container.
        d3.select(this.selector).selectAll("*").remove()
        this.svg_d3 = d3.select(this.selector)
            .append('svg')
            .attr('width', '100%')
            .attr('height', '100%')
            .attr("viewBox", [-this.width, -this.height, this.width * 2, this.height * 2])


        this.nodes_g_d3 = this.svg_d3.append("g")
        this.restartSunburst()
    }
}