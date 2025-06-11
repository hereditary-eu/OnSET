

import * as d3 from 'd3'
import * as THREE from 'three';
import { Api, type Property, type Subject, type Topic } from '@/api/client.ts/Api';
import { registerClass } from '../parsing';

export class SubjectInRadial implements Subject {
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
    x0: number = 0
    x1: number = 0
    y0: number = 0
    y1: number = 0
}

@registerClass
export class TopicInEdges implements Topic {
    subjects_ids: string[];
    property_ids: string[];
    topic_id: number;
    sub_topics: TopicInEdges[];
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

    x: number = 0
    y: number = 0

    get id() {
        return `topic-${this.topic_id}`
    }
    get position() {
        // console.warn('TopicInCircle.position is deprecated, use to_position instead')
        return this.to_position || new THREE.Vector3(0, 0, 0)
    }
    get children() {
        return this.sub_topics || []
    }
    get label() {
        return `${this.topic}`
    }

}
export class SunburstEdgeBundling {
    topics_root: TopicInEdges = null
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

    nodes_g_d3: d3.Selection<any, any, any, any> = null
    root: d3.HierarchyNode<SubjectInRadial> = null
    focus: d3.HierarchyCircularNode<SubjectInRadial> = null
    hierarchy: d3.HierarchyNode<SubjectInRadial> = null
    private node_counter = 0
    constructor(private selector: string) {

    }
    mapNodesToChildren(node: SubjectInRadial): SubjectInRadial {
        let children: SubjectInRadial[] = []
        for (let key in node.descendants) {
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
        node.expanded = true
        return {
            ...node,
            children: children
        }
    }
    restartSunburst() {

        const mapped_nodes: SubjectInRadial[] = this.nodes.map(this.mapNodesToChildren.bind(this)).filter(c => c) as SubjectInRadial[]
        mapped_nodes.forEach(child => child.n_id = this.node_counter++)

        console.log('restarting graph', this.nodes, mapped_nodes)
        const data: SubjectInRadial = {
            subject_id: 'root',
            expanded: true,
            spos: {},
            label: 'root',
            refcount: 0,
            subject_type: 'root',
            total_descendants: mapped_nodes.reduce((acc, child) => acc + child.total_descendants, 0),
            children: mapped_nodes,
            n_id: this.node_counter++,
            x0: 0,
            x1: 0,
            y0: 0,
            y1: 0
        }
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
        const arc = d3.arc<SubjectInRadial>()
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
            return topic_in_circle
        }
        this.topics_root = revive_topic(this.topics_root, null)
        const tree = d3.cluster<TopicInEdges>()
            .size([2 * Math.PI, radius - 100]);
        const hierarchy_topics = d3.hierarchy(this.topics_root)
            .sort((a, b) => d3.ascending(a.height, b.height) || d3.ascending(a.data.children.length, b.data.children.length))

        const root_edges = tree(this.bilink(hierarchy_topics));
        console.log('root_edges', root_edges)
        console.log('root_edges.leaves()', root_edges.leaves().filter(d=>d.data.subjects_ids.length > 0))
        console.log('hierarchy_topics', hierarchy_topics)

        const line = d3.lineRadial<d3.HierarchyNode<TopicInEdges>>()
            .curve(d3.curveBundle.beta(0.85))
            .radius(d => d.y)
            .angle(d => d.x);

        let colornone = "#ccc"
        const link = svg.append("g")
            .attr("stroke", colornone)
            .attr("fill", "none")
            .selectAll()
            .data(root_edges.leaves().flatMap(leaf => leaf.data.outgoing))
            .join("path")
            .style("mix-blend-mode", "multiply")
            .attr("d", ([i, o]) => line(i.path(o)))
        // .each(function (d) { d.path = this; });
    }
    bilink(root: d3.HierarchyNode<TopicInEdges>) {
        const map = new Map(root.leaves().map(d => [d.data.id, d]));
        for (const d of root.leaves()) {
            d.data.incoming = [];
            d.data.outgoing = d.data.sub_topics.map(i => [d, map.get(i.id)])
        }
        for (const d of root.leaves()) {
            for (const o of d.data.outgoing) {
                o[1].data.incoming.push(o);
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